# tests/test_projection.py
"""ProjectionStage ve ProjectedRecord birim testleri (dosyasız)."""
import dataclasses
import unittest
from datetime import datetime, timezone

from models import LOG_RECORD_FIELDS, ProjectedRecord
from projection import ProjectionStage
from tests.helpers import CollectingEmitter, make_record


def project(fields, record=None):
    stage = ProjectionStage(*fields)
    emitter = CollectingEmitter()
    stage.process(record or make_record(status=404, path="/api/x"), emitter)
    return emitter.emitted_items


class TestProjectionStage(unittest.TestCase):

    def test_keeps_only_selected_fields_in_requested_order(self):
        (projected,) = project(["status", "path", "clientIp"])
        self.assertIsInstance(projected, ProjectedRecord)
        self.assertEqual(list(projected.as_dict()), ["status", "path", "clientIp"])
        self.assertEqual(projected.as_dict(), {"status": 404, "path": "/api/x", "clientIp": "10.0.0.1"})

    def test_dropped_fields_are_absent_not_none(self):
        (projected,) = project(["status"])
        with self.assertRaises(AttributeError) as ctx:
            projected.clientIp
        self.assertIn("projeksiyonda yok", str(ctx.exception))
        self.assertFalse(hasattr(projected, "raw"))

    def test_privacy_raw_line_is_not_carried_unless_selected(self):
        # `raw` ham satırın tamamını (IP dahil) içerir; seçilmediyse sızmamalı
        (projected,) = project(["status", "path"])
        self.assertNotIn("raw", projected.as_dict())
        self.assertNotIn("10.0.0.1", str(projected.as_dict()))

    def test_selected_fields_are_accessible_like_logrecord(self):
        (projected,) = project(["status", "timestamp"])
        self.assertEqual(projected.status, 404)
        self.assertEqual(projected.timestamp, datetime(2000, 10, 10, 20, 55, 36, tzinfo=timezone.utc))

    def test_field_names_are_case_insensitive_and_trimmed(self):
        stage = ProjectionStage("CLIENTIP", " Status ")
        self.assertEqual(stage.fields, ("clientIp", "status"))

    def test_duplicate_fields_are_removed_keeping_first_position(self):
        self.assertEqual(ProjectionStage("status", "path", "status").fields, ("status", "path"))

    def test_unknown_field_is_rejected_with_helpful_message(self):
        with self.assertRaises(ValueError) as ctx:
            ProjectionStage("status", "foo")
        self.assertIn("foo", str(ctx.exception))
        self.assertIn("clientIp", str(ctx.exception))  # geçerli alanları listeler

    def test_requires_at_least_one_field(self):
        with self.assertRaises(ValueError):
            ProjectionStage()

    def test_all_logrecord_fields_can_be_projected(self):
        (projected,) = project(LOG_RECORD_FIELDS)
        self.assertEqual(tuple(projected.as_dict()), LOG_RECORD_FIELDS)

    def test_does_not_modify_the_input_record(self):
        record = make_record()
        before = record.as_dict()
        project(["status"], record)
        self.assertEqual(record.as_dict(), before)


class TestProjectedRecord(unittest.TestCase):

    def test_is_immutable(self):
        projected = ProjectedRecord({"status": 200})
        with self.assertRaises(dataclasses.FrozenInstanceError):
            projected.values = {}
        with self.assertRaises(TypeError):
            projected.values["status"] = 500

    def test_copies_input_mapping(self):
        source = {"status": 200}
        projected = ProjectedRecord(source)
        source["status"] = 500
        self.assertEqual(projected.status, 200)

    def test_equality_and_hash(self):
        a, b = ProjectedRecord({"status": 200}), ProjectedRecord({"status": 200})
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))

    def test_private_and_unset_attribute_lookups_raise_attribute_error(self):
        projected = ProjectedRecord({"status": 200})
        with self.assertRaises(AttributeError):
            projected._secret
        # copy() gibi işlemler __getattr__'de sonsuz döngüye girmemeli
        import copy
        self.assertEqual(copy.copy(projected), projected)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
