# tests/test_experiment.py
"""experiment.py duman testi: küçük veriyle çalışır ve ARCHITECTURE.md'nin dayandığı
değişmezleri doğrular (sonuçlar aynı; iş miktarı sıraya göre değişir)."""
import contextlib
import io
import os
import tempfile
import unittest

import experiment
from components import FileLineSource, ParserStage
from tests.helpers import CollectingSink


class TestExperiment(unittest.TestCase):

    def test_generated_log_is_deterministic_and_fully_parseable(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = os.path.join(tmp, "a.log"), os.path.join(tmp, "b.log")
            experiment.generate_log(a, 500)
            experiment.generate_log(b, 500)
            with open(a, "rb") as fa, open(b, "rb") as fb:
                self.assertEqual(fa.read(), fb.read())  # aynı tohum, aynı veri

            from builder import PipelineBuilder
            parser, sink = ParserStage(), CollectingSink()
            PipelineBuilder.from_(FileLineSource(a)).via(parser).to(sink).run()
            self.assertEqual((len(sink.consumed_items), parser.malformed_count), (500, 0))

    def test_every_ordering_gives_identical_output_but_different_work(self):
        results = experiment.run_experiment(n_lines=3000, repeats=1, report=False)
        self.assertEqual(len(results), 4)  # taban + 3 deney
        for block in results:
            self.assertTrue(block["identical"], block["title"])

        _, cheap_cheap, costly, projection = results
        first, second = cheap_cheap["rows"]  # path-prefix(seçici) önce / status önce
        self.assertLess(sum(first["counts"].values()), sum(second["counts"].values()))
        selective_first, costly_first = costly["rows"]
        self.assertLess(selective_first["counts"]["tarayıcı-regex (pahalı)"],
                        costly_first["counts"]["tarayıcı-regex (pahalı)"])
        filter_first, project_first = projection["rows"]
        self.assertLess(filter_first["counts"]["projeksiyon"], project_first["counts"]["projeksiyon"])

    def test_report_is_printed(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            experiment.run_experiment(n_lines=300, repeats=1, report=True)
        text = out.getvalue()
        self.assertIn("Taban çizgisi", text)
        self.assertIn("bayt bayt aynı mı: EVET", text)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
