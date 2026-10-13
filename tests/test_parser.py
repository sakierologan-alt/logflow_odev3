# tests/test_parser.py
"""ParserStage birim testleri.

Bu testler dosya sistemine DOKUNMAZ: aşama oluşturulur, ona bir dizgi verilir
ve yaydığı çıktılar CollectingEmitter ile yakalanır.
"""
import unittest
from datetime import datetime, timezone

from components import ParserStage
from tests.helpers import CollectingEmitter

VALID_CLF = '127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326'


def run_stage(*lines):
    """Yardımcı: aşamaya satırları verir, (aşama, emitter) döner."""
    stage = ParserStage()
    emitter = CollectingEmitter()
    for line in lines:
        stage.process(line, emitter)
    return stage, emitter


class TestParserStage(unittest.TestCase):

    # 1. Geçerli satır
    def test_valid_line(self):
        stage, emitter = run_stage(VALID_CLF)

        self.assertEqual(len(emitter.emitted_items), 1)
        self.assertEqual(stage.malformed_count, 0)
        record = emitter.emitted_items[0]
        self.assertEqual(record.clientIp, "127.0.0.1")
        self.assertEqual(record.method, "GET")
        self.assertEqual(record.path, "/apache_pb.gif")
        self.assertEqual(record.status, 200)
        self.assertEqual(record.bytes, 2326)
        self.assertEqual(record.userAgent, "-")  # düz CLF'de user agent yok
        self.assertEqual(record.attributes, {})
        self.assertEqual(record.raw, VALID_CLF)
        # -0700 -> UTC'ye çevrilmiş olmalı (13:55:36 -0700 == 20:55:36 UTC)
        self.assertEqual(
            record.timestamp,
            datetime(2000, 10, 10, 20, 55, 36, tzinfo=timezone.utc),
        )

    # 2. Eksik alan
    def test_missing_field(self):
        lines = [
            # bayt alanı yok
            '127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "GET /x HTTP/1.0" 200',
            # istek satırı yok
            '127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] 200 2326',
            # IP / ident / user / zaman yok
            '"GET /x HTTP/1.0" 200 2326',
            # method yok
            '127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "/x HTTP/1.0" 200 2326',
        ]
        for line in lines:
            with self.subTest(line=line):
                stage, emitter = run_stage(line)
                self.assertEqual(emitter.emitted_items, [])
                self.assertEqual(stage.malformed_count, 1)

    # 3. Hatalı zaman damgası
    def test_invalid_timestamp(self):
        lines = [
            '127.0.0.1 - - [32/Oct/2000:13:55:36 -0700] "GET /x HTTP/1.0" 200 10',  # 32. gün
            '127.0.0.1 - - [10/Foo/2000:13:55:36 -0700] "GET /x HTTP/1.0" 200 10',  # ay yok
            '127.0.0.1 - - [10/Oct/2000:25:61:61 -0700] "GET /x HTTP/1.0" 200 10',  # saat yok
            '127.0.0.1 - - [10/Oct/2000:13:55:36] "GET /x HTTP/1.0" 200 10',        # saat dilimi yok
        ]
        for line in lines:
            with self.subTest(line=line):
                stage, emitter = run_stage(line)
                self.assertEqual(emitter.emitted_items, [])
                self.assertEqual(stage.malformed_count, 1)

    # 4. Hatalı durum kodu (sayısal değil / üç haneli değil)
    def test_invalid_status_code(self):
        for status in ("abc", "20", "2000", "2x0"):
            line = f'127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "GET /x HTTP/1.0" {status} 10'
            with self.subTest(status=status):
                stage, emitter = run_stage(line)
                self.assertEqual(emitter.emitted_items, [])
                self.assertEqual(stage.malformed_count, 1)

    # 4b. Üç haneli ama HTTP aralığı dışındaki durum kodu
    def test_status_code_out_of_range(self):
        for status in ("099", "600", "999"):
            line = f'127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "GET /x HTTP/1.0" {status} 10'
            with self.subTest(status=status):
                stage, emitter = run_stage(line)
                self.assertEqual(emitter.emitted_items, [])
                self.assertEqual(stage.malformed_count, 1)

    # 5. Boş satır
    def test_empty_line(self):
        stage, emitter = run_stage("", "   ", "\t")

        self.assertEqual(emitter.emitted_items, [])
        self.assertEqual(stage.malformed_count, 3)

    # 6. Fazladan boşluk
    def test_extra_whitespace(self):
        line = '   10.0.0.9   -   -   [10/Oct/2000:13:59:03 -0700]   "GET   /about.html   HTTP/1.1"   404   512   '
        stage, emitter = run_stage(line)

        self.assertEqual(stage.malformed_count, 0)
        self.assertEqual(len(emitter.emitted_items), 1)
        record = emitter.emitted_items[0]
        self.assertEqual(record.clientIp, "10.0.0.9")
        self.assertEqual(record.method, "GET")
        self.assertEqual(record.path, "/about.html")
        self.assertEqual(record.status, 404)
        self.assertEqual(record.bytes, 512)

    # 7. Boşluk içeren tırnaklı user agent
    def test_quoted_user_agent_with_spaces(self):
        agent = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                 "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36")
        line = ('10.0.0.7 - - [11/Oct/2000:09:00:00 +0300] "GET /img/logo.png HTTP/1.1" 200 1024 '
                f'"https://example.com/home" "{agent}"')
        stage, emitter = run_stage(line)

        self.assertEqual(stage.malformed_count, 0)
        self.assertEqual(len(emitter.emitted_items), 1)
        record = emitter.emitted_items[0]
        self.assertEqual(record.userAgent, agent)
        self.assertEqual(record.status, 200)
        self.assertEqual(record.bytes, 1024)
        # +0300 -> UTC: 09:00:00 +0300 == 06:00:00 UTC
        self.assertEqual(
            record.timestamp,
            datetime(2000, 10, 11, 6, 0, 0, tzinfo=timezone.utc),
        )

    # 8. Sorgu dizesi (query string) içeren satır
    def test_query_string(self):
        line = '172.16.0.3 - - [12/Oct/2000:18:30:00 +0000] "GET /search?q=log+flow&page=2 HTTP/1.1" 200 4096'
        stage, emitter = run_stage(line)

        self.assertEqual(stage.malformed_count, 0)
        self.assertEqual(len(emitter.emitted_items), 1)
        self.assertEqual(emitter.emitted_items[0].path, "/search?q=log+flow&page=2")

    # Ek: '-' bayt değeri 0 olur
    def test_dash_bytes_becomes_zero(self):
        line = '10.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "GET /static/app.js HTTP/1.1" 304 -'
        stage, emitter = run_stage(line)

        self.assertEqual(stage.malformed_count, 0)
        self.assertEqual(emitter.emitted_items[0].bytes, 0)

    # Ek: hatalı satırlar akışı durdurmaz, yalnızca sayılır
    def test_malformed_lines_are_counted_and_stream_continues(self):
        stage, emitter = run_stage(
            VALID_CLF,
            "bu bir günlük satırı değil",
            "",
            VALID_CLF,
        )

        self.assertEqual(len(emitter.emitted_items), 2)
        self.assertEqual(stage.malformed_count, 2)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
