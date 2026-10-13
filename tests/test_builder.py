# tests/test_builder.py
"""PipelineBuilder, bileşilebilirlik ve Pipeline yaşam döngüsü testleri."""
import unittest

from builder import PipelineBuilder
from filters import PredicateFilterStage, min_status, path_prefix
from pipeline import Pipeline
from projection import ProjectionStage
from tests.helpers import CollectingSink, ListSource, SpySink, SpySource, SpyStage, make_record


class TestPipelineBuilder(unittest.TestCase):

    def test_fluent_chain_returns_runnable_pipeline(self):
        sink = CollectingSink()
        pipeline = (PipelineBuilder.from_(ListSource([make_record(status=200), make_record(status=500)]))
                    .via(PredicateFilterStage(min_status(400)))
                    .via(ProjectionStage("status"))
                    .to(sink))
        self.assertIsInstance(pipeline, Pipeline)
        pipeline.run()
        self.assertEqual([r.as_dict() for r in sink.consumed_items], [{"status": 500}])

    def test_stages_run_in_the_order_they_were_added(self):
        a, b, c = (PredicateFilterStage(min_status(1), n) for n in "abc")
        pipeline = PipelineBuilder.from_(ListSource([])).via(a).via(b).via(c).to(CollectingSink())
        self.assertEqual([s.name for s in pipeline.stages], ["a", "b", "c"])

    def test_zero_stages_is_valid(self):
        sink = CollectingSink()
        PipelineBuilder.from_(ListSource([1, 2, 3])).to(sink).run()
        self.assertEqual(sink.consumed_items, [1, 2, 3])

    def test_any_number_of_stages_compose(self):
        sink = CollectingSink()
        builder = PipelineBuilder.from_(ListSource([make_record(status=500)]))
        for _ in range(25):  # aynı türden 25 aşama, hiçbirini değiştirmeden
            builder.via(PredicateFilterStage(min_status(400)))
        builder.to(sink).run()
        self.assertEqual(len(sink.consumed_items), 1)

    def test_filters_commute_same_result_in_either_order(self):
        records = [make_record(status=s, path=p) for s in (200, 404, 500)
                   for p in ("/api/a", "/web/b")]

        def run(first, second):
            sink = CollectingSink()
            PipelineBuilder.from_(ListSource(records)).via(first()).via(second()).to(sink).run()
            return sink.consumed_items

        by_status = lambda: PredicateFilterStage(min_status(400))
        by_prefix = lambda: PredicateFilterStage(path_prefix("/api"))
        self.assertEqual(run(by_status, by_prefix), run(by_prefix, by_status))

    def test_rejects_wrong_component_types(self):
        with self.assertRaises(TypeError):
            PipelineBuilder.from_("dosya.log")
        builder = PipelineBuilder.from_(ListSource([]))
        with self.assertRaises(TypeError):
            builder.via(lambda r: r)
        with self.assertRaises(TypeError):
            builder.to(print)

    def test_builder_cannot_be_reused_after_to(self):
        builder = PipelineBuilder.from_(ListSource([]))
        builder.to(CollectingSink())
        with self.assertRaises(RuntimeError):
            builder.via(ProjectionStage("status"))
        with self.assertRaises(RuntimeError):
            builder.to(CollectingSink())


class TestPipelineLifecycle(unittest.TestCase):

    def test_components_open_in_order_and_close_in_reverse(self):
        log = []
        (PipelineBuilder.from_(SpySource(log, [1]))
         .via(SpyStage(log, "s1")).via(SpyStage(log, "s2"))
         .to(SpySink(log)).run())
        self.assertEqual(log, ["source.open", "s1.open", "s2.open", "sink.open",
                               "sink.close", "s2.close", "s1.close", "source.close"])

    def test_everything_is_closed_even_when_a_stage_fails(self):
        log = []
        pipeline = (PipelineBuilder.from_(SpySource(log, [1]))
                    .via(SpyStage(log, "s1", fail=True))
                    .to(SpySink(log)))
        with self.assertRaises(RuntimeError):
            pipeline.run()
        # hata olsa da açılan her bileşen, ters sırada kapatıldı
        self.assertEqual(log[-3:], ["sink.close", "s1.close", "source.close"])

    def test_component_that_failed_to_open_is_not_closed_but_earlier_ones_are(self):
        log = []

        class BrokenSink(SpySink):
            def open(self):
                raise OSError("çıktı dosyası açılamadı")

        with self.assertRaises(OSError):
            PipelineBuilder.from_(SpySource(log, [1])).via(SpyStage(log)).to(BrokenSink(log)).run()
        self.assertEqual(log, ["source.open", "stage.open", "stage.close", "source.close"])


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
