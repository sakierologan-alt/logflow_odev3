# models.py
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Dict, Mapping, Tuple


def format_timestamp(ts: datetime) -> str:
    """Zaman damgasını UTC ve ISO-8601 ('...Z') olarak biçimlendirir."""
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class LogRecord:
    """Ayrıştırılmış tek bir günlük satırı (alan modeli, değişmez).

    * Alanlar `frozen=True` ile salt okunurdur.
    * `attributes` sözlüğü de değişmezdir: kurulumda kopyalanır ve
      `MappingProxyType` ile sarılır, böylece `record.attributes["x"] = 1`
      TypeError verir. Yeni bilgi eklemek isteyen bir aşama mevcut kaydı
      değiştirmez, `dataclasses.replace` ile yeni bir kayıt üretir.
    * `timestamp` saat dilimi bilgisi taşıyan (UTC) bir `datetime`'dır;
      Java'daki `Instant` karşılığıdır.
    """

    timestamp: datetime
    clientIp: str
    method: str
    path: str
    status: int
    bytes: int
    userAgent: str
    # Genişleme noktası (5-7. haftalar): bugünkü ayrıştırıcının bilmediği
    # verileri (coğrafi konum, oturum kimliği, etiketler...) sonraki aşamalar
    # buraya ekler. Alan şeması her yeni aşamada değişmek zorunda kalmaz.
    attributes: Mapping[str, Any] = field(default_factory=dict, hash=False)
    raw: str = ""

    def __post_init__(self) -> None:
        # Çağıranın elindeki sözlükte sonradan yapılacak değişiklik
        # kaydı etkilemesin: kopyala ve salt okunur hale getir.
        object.__setattr__(
            self, "attributes", MappingProxyType(dict(self.attributes))
        )

    def as_dict(self) -> Dict[str, Any]:
        """Tüm alanları (sıralı) sözlük olarak verir; serileştirme için."""
        data = {name: getattr(self, name) for name in LOG_RECORD_FIELDS}
        data["attributes"] = dict(self.attributes)
        return data


# Projeksiyonun seçebileceği alan adları (LogRecord'dan türetilir; tek doğruluk kaynağı).
LOG_RECORD_FIELDS: Tuple[str, ...] = tuple(f.name for f in dataclasses.fields(LogRecord))


@dataclass(frozen=True)
class ProjectedRecord:
    """LogRecord'un seçilen alanlardan oluşan alt kümesi (veri minimizasyonu).

    Seçilmeyen alanlar kayıtta YOKTUR (None ile doldurulmaz). Çıkarılmış bir
    alana erişmek `AttributeError` verir; böylece projeksiyondan SONRA konan
    bir filtre, çıkarılmış alanı sessizce yanlış değerlendirmek yerine
    gürültülü biçimde hata verir. Seçilen alanlara `record.status` gibi
    LogRecord'la aynı biçimde erişilir.
    """

    values: Mapping[str, Any] = field(hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    def __getattr__(self, name: str) -> Any:
        # Yalnızca normal arama başarısız olunca çağrılır.
        if name.startswith("_") or name == "values":
            raise AttributeError(name)
        try:
            return self.values[name]
        except KeyError:
            raise AttributeError(
                f"'{name}' alanı projeksiyonda yok; mevcut alanlar: {', '.join(self.values)}"
            ) from None

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.values)
