# tests/test_integration.py
"""ConsoleSink, Pipeline ve main için uçtan uca testler.

ParserStage testlerinden FARKLI olarak bu dosyadaki testlerden biri
(FileLineSource) geçici bir dosya kullanır.
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

import main as main_module
from components import ConsoleSink, FileLineSource, ParserStage
from models import LogRecord
from pipeline import Pipeline
from tests.helpers import CollectingSink, ListSource

GOOD = '127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326'
GOOD_COMBINED = ('10.0.0.7 - - [11/Oct/2000:09:00:00 +0300] "POST /login HTTP/1.1" 302 0 '
                 '"-" "Mozilla/5.0 (X11; Linux)"')


class TestConsoleSink(unittest.TestCase):

    def test_prints_one_readable_line(self):
        record = LogRecord(
            timestamp=datetime(2000, 10, 10, 20, 55, 36, tzinfo=timezone.utc),
            clientIp="127.0.0.1", method="GET", path="/a?b=1", status=200,
            bytes=2326, userAgent="Mozilla/5.0 (X11; Linux)", raw="",
        )
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            ConsoleSink().consume(record)

        output = buffer.getvalue()
        self.assertEqual(output.count("\n"), 1)
        for expected in ("2000-10-10T20:55:36Z", "127.0.0.1", "GET", "/a?b=1",
                         "200", "2326", "Mozilla/5.0 (X11; Linux)"):
            self.assertIn(expected, output)


class TestPipelineWithParser(unittest.TestCase):

    def test_parser_inserted_between_source_and_sink(self):
        sink = CollectingSink()
        parser = ParserStage()
        pipeline = Pipeline(ListSource([GOOD, "çöp", GOOD_COMBINED]), sink)
        pipeline.add_stage(parser)

        pipeline.run()

        self.assertEqual(len(sink.consumed_items), 2)
        self.assertIsInstance(sink.consumed_items[0], LogRecord)
        self.assertEqual(parser.malformed_count, 1)

    def test_file_source_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "access.log")
            with open(path, "w", encoding="utf-8") as f:
                f.write(GOOD + "\n\nçöp satır\n" + GOOD_COMBINED + "\n")

            sink = CollectingSink()
            parser = ParserStage()
            Pipeline(FileLineSource(path), sink).add_stage(parser).run()

        self.assertEqual([r.status for r in sink.consumed_items], [200, 302])
        self.assertEqual(parser.malformed_count, 2)  # boş satır + çöp satır


class TestMain(unittest.TestCase):

    def test_main_prints_records_and_malformed_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "access.log")
            with open(path, "w", encoding="utf-8") as f:
                f.write(GOOD + "\nçöp\n" + GOOD_COMBINED + "\n")

            buffer = io.StringIO()
            with mock.patch.object(sys, "argv", ["main.py", path]), \
                    contextlib.redirect_stdout(buffer):
                main_module.main()

        output = buffer.getvalue()
        self.assertIn("2000-10-10T20:55:36Z 127.0.0.1 GET /apache_pb.gif", output)
        self.assertIn("Toplam Hatalı/Atlanan Satır Sayısı: 1", output)

    def test_main_without_arguments_exits_with_usage(self):
        # v3: argümanları argparse işler; eksik argümanda çıkış kodu 2 ve usage (stderr)
        buffer = io.StringIO()
        with mock.patch.object(sys, "argv", ["main.py"]), \
                contextlib.redirect_stderr(buffer):
            with self.assertRaises(SystemExit) as ctx:
                main_module.main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("usage:", buffer.getvalue())


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
