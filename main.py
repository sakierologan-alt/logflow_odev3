# main.py
"""LogFlow komut satırı: oku -> ayrıştır -> filtrele -> projeksiyon -> yaz.

Örnekler:
    python main.py data/access-small.log
    python main.py data/access-small.log --min-status 400 --path-prefix /api \\
        --fields timestamp,clientIp,status -o out.jsonl
"""
import argparse
import os
import sys
from datetime import datetime, timezone
from typing import List, Optional

from builder import PipelineBuilder
from components import ConsoleSink, FileLineSource, ParserStage
from filters import PredicateFilterStage, min_status, path_prefix, time_between
from projection import ProjectionStage
from sinks import FileSink


def _parse_time(text: str) -> datetime:
    """ISO-8601 (ör. 2000-10-10T20:00:00Z). Saat dilimi yoksa UTC kabul edilir."""
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"geçersiz zaman '{text}' (beklenen biçim: 2000-10-10T20:00:00Z)")
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="logflow", description="Yapılandırılabilir komut satırı log filtresi")
    ap.add_argument("input", help="girdi günlük dosyası (CLF / Combined)")
    ap.add_argument("-o", "--output", help="çıktı dosyası (JSON Lines); verilmezse konsola yazar")
    ap.add_argument("--min-status", type=int, metavar="N", help="yalnızca status >= N olanlar")
    ap.add_argument("--path-prefix", metavar="PREFIX", help="yalnızca bu önekle başlayan yollar")
    ap.add_argument("--since", type=_parse_time, metavar="ZAMAN", help="timestamp >= ZAMAN (ISO-8601)")
    ap.add_argument("--until", type=_parse_time, metavar="ZAMAN", help="timestamp < ZAMAN (ISO-8601)")
    ap.add_argument("--fields", metavar="A,B,C",
                    help="yalnızca bu alanlar çıktıya girer (veri minimizasyonu)")
    return ap


def build_pipeline(args: argparse.Namespace):
    """Argümanlardan hattı kurar; (pipeline, parser, filtreler, sink) döndürür."""
    parser = ParserStage()
    filters: List[PredicateFilterStage] = []
    if args.min_status is not None:
        filters.append(PredicateFilterStage(min_status(args.min_status), f"min-status>={args.min_status}"))
    if args.path_prefix is not None:
        filters.append(PredicateFilterStage(path_prefix(args.path_prefix), f"path-prefix={args.path_prefix}"))
    if args.since is not None or args.until is not None:
        filters.append(PredicateFilterStage(time_between(args.since, args.until), "time-range"))

    sink = FileSink(args.output) if args.output else ConsoleSink()
    builder = PipelineBuilder.from_(FileLineSource(args.input)).via(parser)
    for stage in filters:
        builder.via(stage)
    if args.fields:
        builder.via(ProjectionStage(*args.fields.split(",")))
    return builder.to(sink), parser, filters, sink


def main(argv: Optional[List[str]] = None) -> int:
    ap = build_arg_parser()
    args = ap.parse_args(argv)

    if args.output and os.path.realpath(args.output) == os.path.realpath(args.input):
        ap.error("çıktı dosyası girdi dosyasıyla aynı olamaz (girdi silinirdi)")
    try:
        pipeline, parser, filters, sink = build_pipeline(args)
    except ValueError as error:  # ör. bilinmeyen --fields alanı
        ap.error(str(error))

    try:
        pipeline.run()
    except OSError as error:
        print(f"Hata: {error}", file=sys.stderr)
        return 1

    print(f"\n[Rapor] Toplam Hatalı/Atlanan Satır Sayısı: {parser.malformed_count}")
    for stage in filters:
        print(f"[Rapor] Filtre {stage.name}: geçen={stage.passed_count}, elenen={stage.rejected_count}")
    if args.output:
        print(f"[Rapor] {sink.written_count} kayıt yazıldı: {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
