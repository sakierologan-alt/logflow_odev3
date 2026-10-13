# tests/helpers.py
"""Tüm haftalarda yeniden kullanılacak test dublörleri (test doubles).

Bu sınıflar gerçek dosyaya, ağa ya da konsola dokunmaz; aşamaları
yalıtılmış biçimde test etmeyi sağlar.
"""
import os
from datetime import datetime, timezone
from typing import Any, List

from interfaces import Emitter, Sink, Source, Stage
from models import LogRecord

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def make_record(**overrides: Any) -> LogRecord:
    """Testler için geçerli bir LogRecord; istenen alanlar değiştirilebilir."""
    values = dict(
        timestamp=datetime(2000, 10, 10, 20, 55, 36, tzinfo=timezone.utc),
        clientIp="10.0.0.1", method="GET", path="/", status=200,
        bytes=100, userAgent="curl/8.0", raw="ham satır",
    )
    values.update(overrides)
    return LogRecord(**values)


class CollectingEmitter(Emitter[Any]):
    """Bir aşamanın yaydığı çıktıları bir listeye toplar.

    Test, aşamaya bir dizgi verir (`stage.process(line, emitter)`) ve
    ardından `emitter.emitted_items` listesini doğrular.
    """

    def __init__(self) -> None:
        self.emitted_items: List[Any] = []

    def emit(self, item: Any) -> None:
        self.emitted_items.append(item)


class CollectingSink(Sink[Any]):
    """Pipeline'ın sonuna takılan, gelen her öğeyi toplayan Sink."""

    def __init__(self) -> None:
        self.consumed_items: List[Any] = []

    def consume(self, item: Any) -> None:
        self.consumed_items.append(item)


class ListSource(Source[Any]):
    """Hazır bir listeden öğe üreten Source (dosya okumaz)."""

    def __init__(self, items: List[Any]) -> None:
        self.items = items

    def produce(self, out: Emitter[Any]) -> None:
        for item in self.items:
            out.emit(item)


# --- Yaşam döngüsü casusları (v3): open/close çağrılarını ortak bir günlüğe yazar ---

class SpySource(ListSource):
    def __init__(self, log: List[str], items: List[Any]) -> None:
        super().__init__(items)
        self.log = log

    def open(self) -> None:
        self.log.append("source.open")

    def close(self) -> None:
        self.log.append("source.close")


class SpyStage(Stage[Any, Any]):
    """Geçişli aşama; `fail=True` ise process() içinde hata fırlatır."""

    def __init__(self, log: List[str], name: str = "stage", fail: bool = False) -> None:
        self.log, self.name, self.fail = log, name, fail

    def process(self, input_item: Any, out: Emitter[Any]) -> None:
        if self.fail:
            raise RuntimeError("aşama bilerek hata verdi")
        out.emit(input_item)

    def open(self) -> None:
        self.log.append(f"{self.name}.open")

    def close(self) -> None:
        self.log.append(f"{self.name}.close")


class SpySink(CollectingSink):
    def __init__(self, log: List[str]) -> None:
        super().__init__()
        self.log = log

    def open(self) -> None:
        self.log.append("sink.open")

    def close(self) -> None:
        self.log.append("sink.close")
