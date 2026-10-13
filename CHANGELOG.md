# Değişiklik Günlüğü (Change Log)

## v3 — Artım 3: Bileşim (filtreleme, projeksiyon, builder)

### Eklenen dosyalar
- `filters.py` — `PredicateFilterStage` (17 satır) ve koşul fabrikaları `min_status`, `path_prefix`, `time_between`.
- `projection.py` — `ProjectionStage` (19 satır): izin listesi ile alan alt kümesi.
- `sinks.py` — `FileSink` (21 satır): JSON Lines yazar; `open()/close()` uygular.
- `builder.py` — akıcı `PipelineBuilder` (`from_ → via → to`).
- `experiment.py` — sıralama deneyi (bileşilebilirlik, görev 4).
- `ARCHITECTURE.md` — tasarım kararları ve ölçülmüş deney sonuçları.
- `tests/test_filters.py`, `tests/test_projection.py`, `tests/test_sinks.py`, `tests/test_builder.py`,
  `tests/test_three_stage_pipeline.py`, `tests/test_cli.py`, `tests/test_experiment.py`.
- `tests/fixtures/small.log` — entegrasyon testinin küçük veri dosyası (7 geçerli, 1 bozuk satır).

### Değiştirilen dosyalar
- `models.py` — `ProjectedRecord`, `LOG_RECORD_FIELDS`, `format_timestamp` ve `LogRecord.as_dict()` eklendi. `LogRecord`'un alanları ve davranışı değişmedi.
- `components.py` — `ConsoleSink` artık `ProjectedRecord`'u da yazdırır (`alan=değer`). `LogRecord` çıktısı aynı. `ParserStage` ve `FileLineSource` değişmedi.
- `main.py` — `argparse` ile komut satırı: `--min-status`, `--path-prefix`, `--since`, `--until`, `--fields`, `-o/--output`. Aşamalar `PipelineBuilder` ile kurulur. Argümansız çağrının çıkış kodu 1'den **2**'ye değişti (argparse standardı), kullanım iletisi stdout yerine stderr'e yazılır.
- `interfaces.py` — **zorunlu küçük değişiklik:** `Sink`'e varsayılanı boş `open()` ve `close()` eklendi. (v2'de Sink'in yaşam döngüsü yoktu.)
- `pipeline.py` — **zorunlu küçük değişiklik:** `run()` artık sink'i de açar/kapatır ve `ExitStack` ile LIFO sırasıyla kapatır; bir aşama hata verse bile açılmış her bileşen kapatılır. Kapanış sırası: sink → aşamalar (ters) → kaynak.
- `data/access-small.log` — 6 adet `/api` satırı eklendi (filtre demosu için). Hatalı satır sayısı hâlâ 4.
- `tests/helpers.py` — `make_record`, `FIXTURES_DIR` ve yaşam döngüsü casusları (`SpySource`, `SpyStage`, `SpySink`) eklendi; `CollectingEmitter`, `CollectingSink`, `ListSource` aynen duruyor.
- `tests/test_integration.py` — argümansız çağrı testi argparse davranışına göre güncellendi (çıkış kodu 2, `usage:` stderr'de).
- `README.md` — v3 için yeniden yazıldı.

### Değişmeyen dosyalar
- `tests/test_parser.py`, `tests/test_models.py`.
- `ParserStage`, `FileLineSource` (v2 davranışı aynen).

### Notlar
- Bu hafta "mevcut aşamalara dokunmadan yeni aşama ekleme" büyük ölçüde sağlandı: üç yeni aşama ve builder yeni dosyalarda. **İstisna:** `interfaces.py` ve `pipeline.py`'daki sink yaşam döngüsü değişikliği, v2'deki bir eksikti (`FileSink`'in `open()/close()` metotları hiç çağrılmayacaktı).
- Hatalı satırlar hâlâ yalnızca sayılır (5. hafta).
- Satır kapsama: %100 (92 test). Ölçüm `coverage.py` yerine standart kütüphane izleyicisiyle yapıldı; kendi ortamınızda `coverage report` ile doğrulayın.

---

## v2 — Artım 2: Tipli Kayıtlar ve İlk Gerçek Filtre

### Eklenen dosyalar
- `models.py` — değişmez `LogRecord` alan kaydı (`attributes` genişleme noktasıyla).
- `tests/__init__.py`, `tests/helpers.py` (`CollectingEmitter`, `CollectingSink`, `ListSource`),
  `tests/test_parser.py` (11 test), `tests/test_models.py`, `tests/test_integration.py`.
- `.coveragerc`, `data/access-small.log`, `README.md`, `CHANGELOG.md`.

### Değiştirilen dosyalar
- `components.py` — `ParserStage` eklendi; `ConsoleSink` `LogRecord` gösterecek şekilde güncellendi.
- `main.py` — `ParserStage` hatta takıldı; sonda hatalı satır sayısı yazdırılır.

### Değişmeyen dosyalar
- `interfaces.py`, `pipeline.py`, `FileLineSource`.
