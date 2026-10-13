# tests/test_sinks.py
"""FileSink testleri: yaşam döngüsü (open/close) ve çıktı biçimi."""
import json
import os
import tempfile
import unittest

from models import ProjectedRecord
from sinks import FileSink
from tests.helpers import make_record


def read_lines(path):
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


class TestFileSink(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = os.path.join(self._tmp.name, "out.jsonl")

    def write(self, *items):
        sink = FileSink(self.path)
        sink.open()
        for item in items:
            sink.consume(item)
        sink.close()
        return sink

    def test_writes_one_json_object_per_line(self):
        sink = self.write(make_record(status=200), make_record(status=404, path="/x"))
        rows = [json.loads(line) for line in read_lines(self.path)]
        self.assertEqual([r["status"] for r in rows], [200, 404])
        self.assertEqual(rows[1]["path"], "/x")
        self.assertEqual(sink.written_count, 2)

    def test_timestamp_is_iso_utc_and_attributes_are_plain_json(self):
        self.write(make_record(attributes={"geo": "TR"}))
        (row,) = [json.loads(line) for line in read_lines(self.path)]
        self.assertEqual(row["timestamp"], "2000-10-10T20:55:36Z")
        self.assertEqual(row["attributes"], {"geo": "TR"})

    def test_projected_record_writes_only_selected_fields(self):
        self.write(ProjectedRecord({"status": 404, "path": "/ü"}))
        (line,) = read_lines(self.path)
        self.assertEqual(json.loads(line), {"status": 404, "path": "/ü"})
        self.assertIn("/ü", line)  # ensure_ascii=False: Türkçe karakter korunur

    def test_projected_attributes_mapping_is_written_as_json_object(self):
        # `--fields attributes`: salt okunur eşlem (MappingProxyType) düz JSON nesnesi olmalı
        from projection import ProjectionStage
        from tests.helpers import CollectingEmitter
        emitter = CollectingEmitter()
        ProjectionStage("attributes", "status").process(make_record(attributes={"geo": "TR"}), emitter)
        self.write(*emitter.emitted_items)
        (row,) = [json.loads(line) for line in read_lines(self.path)]
        self.assertEqual(row, {"attributes": {"geo": "TR"}, "status": 200})

    def test_non_record_items_are_written_as_text(self):
        self.write("düz metin")
        self.assertEqual(json.loads(read_lines(self.path)[0]), "düz metin")

    def test_unserializable_value_raises(self):
        sink = FileSink(self.path)
        sink.open()
        self.addCleanup(sink.close)
        with self.assertRaises(TypeError):
            sink.consume(ProjectedRecord({"x": object()}))

    def test_open_truncates_an_existing_file(self):
        self.write(make_record(), make_record())
        self.write(make_record())
        self.assertEqual(len(read_lines(self.path)), 1)

    def test_consume_before_open_raises_clear_error(self):
        with self.assertRaises(RuntimeError) as ctx:
            FileSink(self.path).consume(make_record())
        self.assertIn("open()", str(ctx.exception))
        self.assertFalse(os.path.exists(self.path))

    def test_close_is_idempotent_and_safe_without_open(self):
        sink = FileSink(self.path)
        sink.close()  # hiç açılmadı: hata vermemeli
        sink.open()
        sink.close()
        sink.close()

    def test_output_is_buffered_until_close(self):
        """Neden close() süs değil: yazılan veri kapatılana kadar diskte olmayabilir."""
        sink = FileSink(self.path)
        sink.open()
        # Tutamacı dışarıda tutuyoruz: aksi halde CPython, son referans düşünce
        # dosyayı kendiliğinden boşaltır ve close() yazılmamış olsa bile test geçerdi.
        handle = sink._file
        sink.consume(make_record())
        self.assertEqual(read_lines(self.path), [])   # arabellekte; dosya hâlâ boş
        sink.close()
        self.assertEqual(len(read_lines(self.path)), 1)  # close() boşalttı
        self.assertTrue(handle.closed)

    def test_close_really_closes_the_underlying_file(self):
        sink = FileSink(self.path)
        sink.open()
        handle = sink._file
        self.assertFalse(handle.closed)
        sink.close()
        self.assertTrue(handle.closed)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
