# components.py
import re
from datetime import datetime, timezone
from typing import Any, Union
from interfaces import Source, Sink, Stage, Emitter
from models import LogRecord, ProjectedRecord, format_timestamp


class FileLineSource(Source[str]):
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.file_obj = None

    def open(self) -> None:
        self.file_obj = open(self.filepath, 'r', encoding='utf-8')

    def produce(self, out: Emitter[str]) -> None:
        if self.file_obj:
            for line in self.file_obj:
                out.emit(line.rstrip('\n'))

    def close(self) -> None:
        if self.file_obj:
            self.file_obj.close()


class ParserStage(Stage[str, LogRecord]):
    """Common Log Format (CLF) ve Combined Log Format satırlarını LogRecord'a çevirir.

    Hatalı satırlar (regex'e uymayan, boş, geçersiz zaman damgası ya da durum
    kodu) bu hafta yalnızca ATLANIR ve SAYILIR (`malformed_count`).
    Hatalı satırların doğru biçimde ele alınması 5. haftada gelecektir.
    """

    # CLF:      ip ident user [zaman] "METHOD path HTTP/x" status bytes
    # Combined: CLF + "referer" "user-agent"
    LOG_PATTERN = re.compile(
        r'^(?P<ip>\S+)\s+'
        r'(?P<ident>\S+)\s+'
        r'(?P<user>\S+)\s+'
        r'\[(?P<time>[^\]]+)\]\s+'
        r'"(?P<method>[A-Z]+)\s+(?P<path>[^\s"]+)(?:\s+HTTP/[0-9.]+)?"\s+'
        r'(?P<status>\d{3})\s+'
        r'(?P<bytes>\d+|-)'
        r'(?:\s+"(?P<referer>[^"]*)"\s+"(?P<agent>[^"]*)")?'
        r'\s*$'
    )

    # CLF zaman damgası: 10/Oct/2000:13:55:36 -0700
    TIME_FORMAT = "%d/%b/%Y:%H:%M:%S %z"

    def __init__(self):
        self.malformed_count = 0

    def process(self, input_item: str, out: Emitter[LogRecord]) -> None:
        # Boş satır: hatalı sayılır ve atlanır
        if not input_item or not input_item.strip():
            self.malformed_count += 1
            return

        match = self.LOG_PATTERN.match(input_item.strip())
        if not match:
            self.malformed_count += 1
            return

        data = match.groupdict()

        try:
            status = int(data['status'])
            if not 100 <= status <= 599:
                raise ValueError(f"geçersiz durum kodu: {status}")

            raw_bytes = data['bytes']
            bytes_val = 0 if raw_bytes == '-' else int(raw_bytes)

            # Saat dilimi korunur, sonra UTC'ye çevrilir (Instant karşılığı)
            timestamp = datetime.strptime(data['time'], self.TIME_FORMAT)
            timestamp = timestamp.astimezone(timezone.utc)
        except ValueError:
            self.malformed_count += 1
            return

        record = LogRecord(
            timestamp=timestamp,
            clientIp=data['ip'],
            method=data['method'],
            path=data['path'],
            status=status,
            bytes=bytes_val,
            userAgent=data['agent'] if data['agent'] is not None else "-",
            attributes={},
            raw=input_item
        )
        out.emit(record)


class ConsoleSink(Sink[Union[LogRecord, ProjectedRecord]]):
    def consume(self, item: Union[LogRecord, ProjectedRecord]) -> None:
        if isinstance(item, ProjectedRecord):
            # Projeksiyon sonrası: yalnızca seçilen alanlar, alan=değer biçiminde
            print(" ".join(f"{k}={self._text(v)}" for k, v in item.values.items()))
            return
        print(
            f"{format_timestamp(item.timestamp)} {item.clientIp} {item.method} {item.path} "
            f"-> {item.status} ({item.bytes} B) ua=\"{item.userAgent}\""
        )

    @staticmethod
    def _text(value: Any) -> str:
        return format_timestamp(value) if isinstance(value, datetime) else str(value)
