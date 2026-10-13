# experiment.py
"""Bileşilebilirlik deneyi (Artım 3, görev 4).

Aynı veriyi, aşamalar farklı sıralarda olacak şekilde hattan geçirir ve
(1) çıktıların bayt bayt aynı olduğunu, (2) işin miktarının ve süresinin
farklı olduğunu ölçer. Çalıştırma:  python experiment.py [satır_sayısı] [tekrar]

İş miktarı = her aşamanın aldığı kayıt sayısı (deterministik, makineden bağımsız).
Süre = en iyi / ortanca duvar saati (makineye bağlı; yalnızca göreli okunmalı).
"""
import hashlib
import os
import random
import re
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Tuple

from builder import PipelineBuilder
from components import FileLineSource, ParserStage
from filters import PredicateFilterStage, min_status, path_prefix
from interfaces import Emitter, Stage
from projection import ProjectionStage
from sinks import FileSink

FIELDS = ("timestamp", "clientIp", "status", "path")
AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/118.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/118.0",
    "curl/8.0", "Googlebot/2.1 (+http://www.google.com/bot.html)",
]
# Kasıtlı olarak PAHALI bir koşul: ham satırın tamamında düzenli ifade araması.
MODERN_BROWSER = re.compile(r"(Chrome|Firefox)/\d+(\.\d+)*.*(Safari|Gecko)")


def costly_browser_check(record) -> bool:
    return MODERN_BROWSER.search(record.raw) is not None


def generate_log(path: str, n_lines: int, seed: int = 42) -> None:
    """Deterministik sentetik günlük: ~%2 /api/admin, ~%28 /api/v1, ~%70 diğer;
    durum kodlarının ~%20'si >= 400 (yol ve durum birbirinden bağımsız)."""
    rng = random.Random(seed)
    statuses = rng.choices([200, 304, 404, 500, 403], weights=[70, 10, 10, 5, 5], k=n_lines)
    start = datetime(2000, 10, 10, 13, 0, 0, tzinfo=timezone(timedelta(hours=-7)))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for i, status in enumerate(statuses):
            roll = rng.random()
            if roll < 0.02:
                target = "/api/admin/users"
            elif roll < 0.30:
                target = f"/api/v1/items/{rng.randrange(10_000)}"
            else:
                target = rng.choice(["/index.html", "/static/app.js", "/img/logo.png", "/about.html"])
            stamp = (start + timedelta(seconds=i)).strftime("%d/%b/%Y:%H:%M:%S %z")
            f.write(f'10.0.{rng.randrange(256)}.{rng.randrange(256)} - - [{stamp}] '
                    f'"GET {target} HTTP/1.1" {status} {rng.randrange(1, 9999)} "-" "{rng.choice(AGENTS)}"\n')


class CountingStage(Stage[Any, Any]):
    """Sarmalayıcı aşama: içindekine devreder, aldığı kayıt sayısını tutar.
    (Aşamaların birbirine takılabilmesinin bir örneği: sarmalamak da bir aşamadır.)"""

    def __init__(self, inner: Stage, label: str):
        self.inner, self.label, self.received = inner, label, 0

    def process(self, input_item: Any, out: Emitter[Any]) -> None:
        self.received += 1
        self.inner.process(input_item, out)

    def open(self) -> None:
        self.inner.open()

    def close(self) -> None:
        self.inner.close()


def filt(predicate: Callable, label: str) -> Callable[[], CountingStage]:
    return lambda: CountingStage(PredicateFilterStage(predicate, label), label)


def proj() -> CountingStage:
    return CountingStage(ProjectionStage(*FIELDS), "projeksiyon")


def run_once(stages: List[CountingStage], in_path: str, out_path: str) -> Tuple[float, str, Dict[str, int]]:
    builder = PipelineBuilder.from_(FileLineSource(in_path)).via(ParserStage())
    for stage in stages:
        builder.via(stage)
    pipeline = builder.to(FileSink(out_path))
    started = time.perf_counter()
    pipeline.run()
    elapsed = time.perf_counter() - started
    with open(out_path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()[:12]
    return elapsed, digest, {s.label: s.received for s in stages}


# (başlık, [(varyant adı, aşama üreticileri), ...])
def experiments() -> List[Tuple[str, List[Tuple[str, List[Callable[[], CountingStage]]]]]]:
    admin, status, costly = filt(path_prefix("/api/admin"), "path-prefix /api/admin"), \
        filt(min_status(400), "status>=400"), filt(costly_browser_check, "tarayıcı-regex (pahalı)")
    return [
        ("0. Taban çizgisi: yalnızca oku + ayrıştır (her kaydı eleyen tek filtre, yazılacak çıktı yok)", [
            ("oku + ayrıştır", [filt(lambda record: False, "hiçbirini geçirme")]),
        ]),
        ("1. İki ucuz filtre: seçici olan önce mi, sonra mı?  (/api/admin ~%2, status>=400 ~%20)", [
            ("path-prefix -> status", [admin, status]),
            ("status -> path-prefix", [status, admin]),
        ]),
        ("2. Pahalı filtre (regex) ile ucuz-seçici filtre", [
            ("ucuz-seçici -> pahalı", [admin, costly]),
            ("pahalı -> ucuz-seçici", [costly, admin]),
        ]),
        ("3. Filtre projeksiyondan ÖNCE mi, SONRA mı?  (status projeksiyonda tutuluyor)", [
            ("filtre -> projeksiyon", [status, proj]),
            ("projeksiyon -> filtre", [proj, status]),
        ]),
    ]


def run_experiment(n_lines: int = 100_000, repeats: int = 5, report: bool = True) -> List[Dict[str, Any]]:
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        in_path, out_path = os.path.join(tmp, "in.log"), os.path.join(tmp, "out.jsonl")
        generate_log(in_path, n_lines)
        for title, variants in experiments():
            rows = []
            for name, factories in variants:
                times, digest, counts = [], None, None
                for _ in range(repeats):
                    stages = [make() for make in factories]  # aşamalar durumludur: her tekrarda yenisi
                    elapsed, digest, counts = run_once(stages, in_path, out_path)
                    times.append(elapsed)
                rows.append({"variant": name, "best": min(times), "median": statistics.median(times),
                             "digest": digest, "counts": counts})
            same = len({r["digest"] for r in rows}) == 1
            results.append({"title": title, "rows": rows, "identical": same})
            if report:
                _print_block(title, rows, same, n_lines)
    return results


def _print_block(title: str, rows: List[Dict[str, Any]], same: bool, n_lines: int) -> None:
    print(f"\n{title}")
    for r in rows:
        work = ", ".join(f"{k}={v}" for k, v in r["counts"].items())
        print(f"  {r['variant']:<24} en iyi {r['best']:.3f}s  ortanca {r['median']:.3f}s  "
              f"çıktı#{r['digest']}  alınan kayıt: {work}")
    if len(rows) > 1:
        print(f"  -> çıktılar bayt bayt aynı mı: {'EVET' if same else 'HAYIR'}")


if __name__ == "__main__":  # pragma: no cover
    lines = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    print(f"Deney: {lines} satır, {reps} tekrar, Python {sys.version.split()[0]}")
    run_experiment(lines, reps)
