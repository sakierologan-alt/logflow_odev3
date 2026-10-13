# filters.py
"""PredicateFilterStage ve hazır koşul (predicate) fabrikaları.

Filtre, kaydı DEĞİŞTİRMEZ; yalnızca iletir ya da atar. Bu yüzden komşu
aşamalar onun varlığından habersizdir (modülerlik).
"""
from datetime import datetime, timezone
from typing import Callable, Optional

from interfaces import Emitter, Stage
from models import LogRecord

Predicate = Callable[[LogRecord], bool]


class PredicateFilterStage(Stage[LogRecord, LogRecord]):
    """Bir kaydı yalnızca `predicate(kayıt)` doğruysa iletir."""

    def __init__(self, predicate: Predicate, name: Optional[str] = None):
        if not callable(predicate):
            raise TypeError("predicate çağrılabilir (callable) olmalı")
        self.predicate = predicate
        self.name = name or getattr(predicate, "__name__", "predicate")
        self.passed_count = 0
        self.rejected_count = 0

    def process(self, input_item: LogRecord, out: Emitter[LogRecord]) -> None:
        if self.predicate(input_item):
            self.passed_count += 1
            out.emit(input_item)  # aynı nesne, değiştirilmeden
        else:
            self.rejected_count += 1


# --- Hazır koşullar -------------------------------------------------------

def min_status(threshold: int) -> Predicate:
    """status >= threshold (ör. 400: tüm istemci/sunucu hataları)."""
    def status_at_least(record: LogRecord) -> bool:
        return record.status >= threshold
    return status_at_least


def path_prefix(prefix: str) -> Predicate:
    """path, `prefix` ile başlıyorsa (ör. '/api')."""
    def path_starts_with(record: LogRecord) -> bool:
        return record.path.startswith(prefix)
    return path_starts_with


def time_between(start: Optional[datetime] = None, end: Optional[datetime] = None) -> Predicate:
    """start <= timestamp < end (yarı açık aralık). Sınırlardan biri None olabilir.

    Saat dilimsiz (naive) sınırlar UTC kabul edilir.
    """
    def as_utc(moment: Optional[datetime]) -> Optional[datetime]:
        if moment is not None and moment.tzinfo is None:
            return moment.replace(tzinfo=timezone.utc)
        return moment

    lower, upper = as_utc(start), as_utc(end)

    def in_time_range(record: LogRecord) -> bool:
        return ((lower is None or record.timestamp >= lower)
                and (upper is None or record.timestamp < upper))
    return in_time_range
