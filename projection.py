# projection.py
"""ProjectionStage: kaydı seçilen alanların alt kümesine indirger.

Veri minimizasyonu: bir sonraki aşamanın / çıktının ihtiyacı olmayan alan
hiç taşınmaz. Çıktı küçülür ve kişisel veri (clientIp, userAgent...) ile
ham satır (`raw`, tüm bilgiyi içerir) yanlışlıkla sızmaz. Seçim bir
İZİN LİSTESİDİR (allow-list): yalnızca adı geçen alanlar kalır.
"""
from interfaces import Emitter, Stage
from models import LOG_RECORD_FIELDS, LogRecord, ProjectedRecord


class ProjectionStage(Stage[LogRecord, ProjectedRecord]):

    def __init__(self, *fields: str):
        if not fields:
            raise ValueError("ProjectionStage en az bir alan istemeli")
        canonical = {name.lower(): name for name in LOG_RECORD_FIELDS}
        chosen = []
        for requested in fields:
            name = canonical.get(requested.strip().lower())
            if name is None:
                raise ValueError(
                    f"Bilinmeyen alan '{requested}'. Geçerli alanlar: {', '.join(LOG_RECORD_FIELDS)}"
                )
            if name not in chosen:  # tekrarları at, sırayı koru
                chosen.append(name)
        self.fields = tuple(chosen)

    def process(self, input_item: LogRecord, out: Emitter[ProjectedRecord]) -> None:
        out.emit(ProjectedRecord({name: getattr(input_item, name) for name in self.fields}))
