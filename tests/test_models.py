# tests/test_models.py
import dataclasses
import unittest
from datetime import datetime, timezone

from models import LogRecord


def make_record(**overrides):
    values = dict(
        timestamp=datetime(2000, 10, 10, 20, 55, 36, tzinfo=timezone.utc),
        clientIp="127.0.0.1",
        method="GET",
        path="/",
        status=200,
        bytes=1,
        userAgent="-",
        raw="satır",
    )
    values.update(overrides)
    return LogRecord(**values)


class TestLogRecord(unittest.TestCase):

    def test_fields_are_immutable(self):
        record = make_record()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            record.status = 500

    def test_attributes_default_to_empty(self):
        self.assertEqual(make_record().attributes, {})

    def test_attributes_are_read_only(self):
        record = make_record(attributes={"a": 1})
        with self.assertRaises(TypeError):
            record.attributes["b"] = 2

    def test_attributes_are_copied(self):
        source = {"a": 1}
        record = make_record(attributes=source)
        source["a"] = 99
        self.assertEqual(record.attributes["a"], 1)

    def test_later_stage_extends_record_with_replace(self):
        # 5-7. haftalardaki aşamalar kaydı değiştirmez, genişletilmiş kopyasını üretir
        record = make_record()
        enriched = dataclasses.replace(
            record, attributes={**record.attributes, "geo": "TR"}
        )
        self.assertEqual(record.attributes, {})
        self.assertEqual(enriched.attributes["geo"], "TR")
        self.assertEqual(enriched.path, record.path)

    def test_record_is_hashable(self):
        self.assertIsInstance(hash(make_record()), int)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
