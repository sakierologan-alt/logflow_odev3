# tests/test_three_stage_pipeline.py
"""Entegrasyon: fixture dosyası üzerinde 3 aşamalı hat (ayrıştır -> filtrele -> projeksiyon),
çıktı dosyasının içeriği doğrulanır."""
import json
import os
import tempfile
import unittest

from builder import PipelineBuilder
from components import FileLineSource, ParserStage
from filters import PredicateFilterStage, min_status, path_prefix
from projection import ProjectionStage
from sinks import FileSink
from tests.helpers import FIXTURES_DIR

FIXTURE = os.path.join(FIXTURES_DIR, "small.log")  # 7 geçerli + 1 bozuk satır


class TestThreeStagePipeline(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.output = os.path.join(self._tmp.name, "out.jsonl")

    def run_pipeline(self, *middle_stages):
        parser = ParserStage()
        builder = PipelineBuilder.from_(FileLineSource(FIXTURE)).via(parser)
        for stage in middle_stages:
            builder.via(stage)
        sink = FileSink(self.output)
        builder.to(sink).run()
        with open(self.output, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f.read().splitlines()]
        return rows, parser, sink

    def test_parse_filter_project_writes_expected_file(self):
        rows, parser, sink = self.run_pipeline(
            PredicateFilterStage(min_status(400)),
            ProjectionStage("timestamp", "clientIp", "status", "path"),
        )
        self.assertEqual(rows, [
            {"timestamp": "2000-10-10T20:56:01Z", "clientIp": "10.0.0.2", "status": 404, "path": "/api/users/42"},
            {"timestamp": "2000-10-10T20:57:12Z", "clientIp": "10.0.0.3", "status": 500, "path": "/api/orders"},
            {"timestamp": "2000-10-10T20:58:40Z", "clientIp": "10.0.0.4", "status": 404, "path": "/index.html"},
            {"timestamp": "2000-10-10T21:00:00Z", "clientIp": "10.0.0.6", "status": 403, "path": "/api/orders/7"},
        ])
        self.assertEqual([list(r) for r in rows], [["timestamp", "clientIp", "status", "path"]] * 4)
        self.assertEqual(parser.malformed_count, 1)
        self.assertEqual(sink.written_count, 4)

    def test_two_filters_and_projection(self):
        rows, _, _ = self.run_pipeline(
            PredicateFilterStage(min_status(400)),
            PredicateFilterStage(path_prefix("/api")),
            ProjectionStage("clientIp", "status"),
        )
        self.assertEqual(rows, [
            {"clientIp": "10.0.0.2", "status": 404},
            {"clientIp": "10.0.0.3", "status": 500},
            {"clientIp": "10.0.0.6", "status": 403},
        ])

    def test_without_middle_stages_writes_every_valid_record_in_full(self):
        rows, _, _ = self.run_pipeline()
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0]["raw"].split()[0], "10.0.0.1")
        self.assertEqual(rows[6]["bytes"], 0)  # '-' -> 0

    def test_output_is_complete_after_run_because_sink_was_closed(self):
        rows, _, sink = self.run_pipeline(PredicateFilterStage(min_status(0)))
        self.assertEqual(len(rows), sink.written_count)  # hiçbir satır arabellekte kalmadı

    def test_filter_placed_before_parser_cannot_work(self):
        # Ayrıştırmadan önce filtrelemek mümkün değil: filtre LogRecord bekler, hat dizgi taşır.
        builder = (PipelineBuilder.from_(FileLineSource(FIXTURE))
                   .via(PredicateFilterStage(min_status(400)))
                   .via(ParserStage()))
        with self.assertRaises(AttributeError):
            builder.to(FileSink(self.output)).run()

    def test_filter_after_projection_works_only_if_field_was_kept(self):
        kept, _, _ = self.run_pipeline(
            ProjectionStage("status", "path"), PredicateFilterStage(min_status(500)))
        self.assertEqual(kept, [{"status": 500, "path": "/api/orders"}])

        with self.assertRaises(AttributeError) as ctx:  # status projeksiyonla atıldı
            self.run_pipeline(ProjectionStage("path"), PredicateFilterStage(min_status(500)))
        self.assertIn("status", str(ctx.exception))

    def test_filter_order_does_not_change_output(self):
        status_first, _, _ = self.run_pipeline(
            PredicateFilterStage(min_status(400)), PredicateFilterStage(path_prefix("/api")))
        prefix_first, _, _ = self.run_pipeline(
            PredicateFilterStage(path_prefix("/api")), PredicateFilterStage(min_status(400)))
        self.assertEqual(status_first, prefix_first)

    def test_filter_before_or_after_projection_gives_same_output(self):
        fields = ("timestamp", "status", "path")
        before, _, _ = self.run_pipeline(PredicateFilterStage(min_status(400)), ProjectionStage(*fields))
        after, _, _ = self.run_pipeline(ProjectionStage(*fields), PredicateFilterStage(min_status(400)))
        self.assertEqual(before, after)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
