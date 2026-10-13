# LogFlow — Artım 3: Bileşim (v3)

Okuyan, ayrıştıran, filtreleyen, projeksiyon uygulayan ve yazan, yapılandırılabilir bir komut satırı log filtresi.

```
FileLineSource ─str─▶ ParserStage ─LogRecord─▶ PredicateFilterStage* ─▶ ProjectionStage? ─▶ FileSink (veya ConsoleSink)
```

Tasarım kararları ve **sıralama deneyinin sonuçları**: [ARCHITECTURE.md](ARCHITECTURE.md).
Değişen dosyalar: [CHANGELOG.md](CHANGELOG.md).

## Çalıştırma

Gereksinim: Python 3.10+, dış bağımlılık yok.

```bash
# Hiç filtre yok: tüm geçerli kayıtlar konsola
python main.py data/access-small.log

# Yalnızca hatalar (>= 400), yalnızca /api yolları, yalnızca 3 alan, dosyaya
python main.py data/access-small.log --min-status 400 --path-prefix /api \
    --fields timestamp,clientIp,status -o out.jsonl

# Zaman aralığı (başlangıç dahil, bitiş hariç; ISO-8601, saat dilimi yoksa UTC)
python main.py data/access-small.log --since 2000-10-11T06:00:00Z --until 2000-10-11T06:08:00Z
```

| Argüman | Anlamı |
|---|---|
| `input` | Girdi günlük dosyası (CLF / Combined) |
| `--min-status N` | Yalnızca `status >= N` |
| `--path-prefix P` | Yalnızca `path`, `P` ile başlayanlar |
| `--since Z` / `--until Z` | `Z1 <= timestamp < Z2` |
| `--fields a,b,c` | Yalnızca bu alanlar çıktıya girer (veri minimizasyonu). Geçerli alanlar: `timestamp, clientIp, method, path, status, bytes, userAgent, attributes, raw` |
| `-o, --output F` | JSON Lines dosyasına yaz; verilmezse konsola |

Filtreler verildikleri sıraya bakılmaksızın sabit sırada uygulanır: `min-status → path-prefix → zaman aralığı → projeksiyon`.
Sonda rapor yazılır: hatalı satır sayısı, her filtrenin geçen/elenen sayısı ve yazılan kayıt sayısı.
Bilinmeyen `--fields` alanı, hatalı zaman, girdi ile çıktının aynı dosya olması ya da girdi dosyasının bulunamaması anlaşılır bir hata verir (girdi dosyasına asla dokunulmaz).

Örnek çıktı dosyası satırı: `{"timestamp": "2000-10-11T06:05:30Z", "clientIp": "10.1.0.2", "status": 404}`

## Builder ile kullanım

```python
pipeline = (PipelineBuilder.from_(FileLineSource("data/access-small.log"))
            .via(ParserStage())
            .via(PredicateFilterStage(min_status(400)))
            .via(ProjectionStage("timestamp", "clientIp", "status", "path"))
            .to(FileSink("out.jsonl")))
pipeline.run()
```

(Python'da `from` ayrılmış sözcük olduğundan başlangıç metodu `from_`.)
Aşamalar herhangi bir sırada ve sayıda eklenebilir. Hazır koşullar: `min_status(n)`, `path_prefix(p)`, `time_between(başlangıç, bitiş)`; kendi koşulunuzu `lambda r: ...` ile de verebilirsiniz.

## Dosyalar

| Dosya | İçerik |
|---|---|
| `interfaces.py`, `pipeline.py` | Sözleşmeler ve hat (v3'te yalnızca sink yaşam döngüsü için küçük değişiklik, bkz. CHANGELOG) |
| `models.py` | `LogRecord`, `ProjectedRecord` |
| `components.py` | `FileLineSource`, `ParserStage`, `ConsoleSink` |
| `filters.py` | `PredicateFilterStage` + koşul fabrikaları |
| `projection.py` | `ProjectionStage` |
| `sinks.py` | `FileSink` |
| `builder.py` | `PipelineBuilder` |
| `main.py` | Komut satırı |
| `experiment.py` | Sıralama deneyi (`python experiment.py [satır] [tekrar]`) |

## Testler

```bash
python -m unittest -v
```

**92 test.** Her yeni aşamanın ayrı test dosyası var; hepsi dosya sistemine dokunmadan `CollectingEmitter` ile çalışır:

| Dosya | Test | Kapsadığı |
|---|---|---|
| `test_parser.py` | 11 | `ParserStage` (v2'deki 8 zorunlu durum dahil) |
| `test_filters.py` | 11 | `PredicateFilterStage`, `min_status`, `path_prefix`, `time_between` |
| `test_projection.py` | 14 | `ProjectionStage`, `ProjectedRecord` |
| `test_sinks.py` | 11 | `FileSink` (yaşam döngüsü, arabellek, biçim) |
| `test_builder.py` | 10 | `PipelineBuilder`, bileşilebilirlik, `Pipeline` yaşam döngüsü |
| `test_three_stage_pipeline.py` | 8 | **Entegrasyon:** `tests/fixtures/small.log` üzerinde ayrıştır → filtrele → projeksiyon → dosya; çıktı dosyasının içeriği doğrulanır |
| `test_cli.py` | 13 | Argüman işleme ve uçtan uca çalıştırma |
| `test_experiment.py` | 3 | Deney betiği (sonuçlar aynı, iş miktarı farklı) |
| `test_models.py`, `test_integration.py` | 6 + 5 | `LogRecord`, `ConsoleSink`, v2 hattı |

## Kapsama (line coverage)

```bash
pip install coverage
coverage run -m unittest
coverage report
```

**Satır kapsama: %100** (451 yürütülebilir satır, 0 kaçan). Bu sayıyı geliştirme ortamında `coverage` paketi kurulamadığı için Python standart kütüphanesindeki `sys.settrace` ile ölçtüm (`@abstractmethod` gövdeleri ve `# pragma: no cover` satırları hariç, `coverage.py` ile aynı kurallar). **Kendi bilgisayarınızda yukarıdaki üç komutu çalıştırıp çıkan yüzdeyi buraya yazın**; değer farklıysa bu satırı güncelleyin.

## Sıralama deneyi (özet)

Ayrıntılar ve tablolar `ARCHITECTURE.md` içinde. 100.000 satırlık sentetik veride:

- Aynı filtreleri iki farklı sırada çalıştırmak **bayt bayt aynı çıktıyı** verir.
- **İş miktarı** sıraya göre değişir (ör. pahalı regex 100.000 yerine 1.995 kayda uygulanır), **süre farkı** ise koşulun maliyetine bağlıdır: iki ucuz filtrede ölçülemez (~%1), pahalı filtrede ~%12, projeksiyon sırasında ~%9.
- Ayrıştırma sürenin çoğunu (~%75–95) oluşturur ve ayrıştırmadan önce kayıt düzeyinde filtre koymak mümkün değildir.

Yeniden üretmek için: `python experiment.py 100000 5` (süreler makineye göre değişir; iş miktarı sayıları değişmez).

## Teslim (v3)

```bash
git add -A
git commit -m "v3: PredicateFilterStage, ProjectionStage, FileSink, PipelineBuilder, CLI, ARCHITECTURE.md"
git tag -a v3 -m "Artım 3: Bileşim"
```
