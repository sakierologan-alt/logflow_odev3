# sinks.py
"""FileSink: kayıtları bir dosyaya JSON Lines (satır başına bir JSON) yazar.

Yaşam döngüsü burada süs değildir: yazma akışı (writer) arabelleğe alır.
`close()` çağrılmazsa son arabellek diske HİÇ yazılmayabilir ve hiçbir hata
görünmez. Pipeline, open()/close() çağrılarını garanti eder (bkz. pipeline.py).
"""
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Optional, TextIO

from interfaces import Sink
from models import format_timestamp


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return format_timestamp(value)
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"JSON'a çevrilemeyen tür: {type(value).__name__}")


class FileSink(Sink[Any]):

    def __init__(self, path: str):
        self.path = path
        self.written_count = 0
        self._file: Optional[TextIO] = None

    def open(self) -> None:
        self._file = open(self.path, "w", encoding="utf-8", newline="\n")

    def consume(self, item: Any) -> None:
        if self._file is None:
            raise RuntimeError("FileSink açık değil: önce open() çağrılmalı")
        data = item.as_dict() if hasattr(item, "as_dict") else str(item)
        self._file.write(json.dumps(data, default=_json_default, ensure_ascii=False) + "\n")
        self.written_count += 1

    def close(self) -> None:
        if self._file is not None:  # tekrar close() zararsızdır
            self._file.close()
            self._file = None
