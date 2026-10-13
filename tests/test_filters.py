# tests/test_filters.py
"""PredicateFilterStage ve hazır koşulların birim testleri (dosyasız)."""
import unittest
from datetime import datetime, timedelta, timezone

from filters import PredicateFilterStage, min_status, path_prefix, time_between
from tests.helpers import CollectingEmitter, make_record


def run_filter(predicate, *records):
    stage = PredicateFilterStage(predicate)
    emitter = CollectingEmitter()
    for record in records:
        stage.process(record, emitter)
    return stage, emitter


class TestPredicateFilterStage(unittest.TestCase):

    def test_forwards_matching_record_unchanged(self):
        record = make_record(status=500)
        _, emitter = run_filter(lambda r: r.status >= 400, record)
        self.assertEqual(len(emitter.emitted_items), 1)
        self.assertIs(emitter.emitted_items[0], record)  # aynı nesne, kopya değil

    def test_drops_non_matching_record(self):
        _, emitter = run_filter(lambda r: r.status >= 400, make_record(status=200))
        self.assertEqual(emitter.emitted_items, [])

    def test_counts_passed_and_rejected_and_keeps_order(self):
        records = [make_record(status=s) for s in (200, 404, 301, 500, 403)]
        stage, emitter = run_filter(min_status(400), *records)
        self.assertEqual([r.status for r in emitter.emitted_items], [404, 500, 403])
        self.assertEqual((stage.passed_count, stage.rejected_count), (3, 2))

    def test_name_defaults_to_predicate_name_and_can_be_overridden(self):
        self.assertEqual(PredicateFilterStage(min_status(400)).name, "status_at_least")
        self.assertEqual(PredicateFilterStage(min_status(400), "hatalar").name, "hatalar")

    def test_rejects_non_callable_predicate(self):
        with self.assertRaises(TypeError):
            PredicateFilterStage("status >= 400")


class TestMinStatus(unittest.TestCase):
    def test_boundary_is_inclusive(self):
        predicate = min_status(400)
        self.assertFalse(predicate(make_record(status=399)))
        self.assertTrue(predicate(make_record(status=400)))
        self.assertTrue(predicate(make_record(status=503)))


class TestPathPrefix(unittest.TestCase):
    def test_matches_only_prefix(self):
        predicate = path_prefix("/api")
        self.assertTrue(predicate(make_record(path="/api")))
        self.assertTrue(predicate(make_record(path="/api/users?id=1")))
        self.assertFalse(predicate(make_record(path="/static/api")))  # öneki değil, içinde geçer
        self.assertFalse(predicate(make_record(path="/API/users")))   # büyük/küçük harf duyarlı


class TestTimeBetween(unittest.TestCase):
    T0 = datetime(2000, 10, 10, 20, 0, 0, tzinfo=timezone.utc)

    def at(self, delta_minutes):
        return make_record(timestamp=self.T0 + timedelta(minutes=delta_minutes))

    def test_half_open_range_start_inclusive_end_exclusive(self):
        predicate = time_between(self.T0, self.T0 + timedelta(minutes=10))
        self.assertFalse(predicate(self.at(-1)))
        self.assertTrue(predicate(self.at(0)))     # başlangıç dahil
        self.assertTrue(predicate(self.at(9)))
        self.assertFalse(predicate(self.at(10)))   # bitiş hariç

    def test_open_ended_bounds(self):
        self.assertTrue(time_between(start=self.T0)(self.at(10_000)))
        self.assertFalse(time_between(start=self.T0)(self.at(-1)))
        self.assertTrue(time_between(end=self.T0)(self.at(-10_000)))
        self.assertTrue(time_between()(self.at(0)))  # sınırsız: hepsi geçer

    def test_naive_bounds_are_treated_as_utc(self):
        predicate = time_between(datetime(2000, 10, 10, 20, 0, 0))  # saat dilimsiz
        self.assertTrue(predicate(self.at(0)))
        self.assertFalse(predicate(self.at(-1)))

    def test_works_across_timezones(self):
        plus3 = timezone(timedelta(hours=3))
        record = make_record(timestamp=datetime(2000, 10, 10, 23, 0, 0, tzinfo=plus3))  # = 20:00 UTC
        self.assertTrue(time_between(self.T0, self.T0 + timedelta(minutes=1))(record))


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
