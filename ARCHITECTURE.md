# LogFlow — Mimari Notları (Artım 3: Bileşim)

Bu belge Artım 3'ün tasarım kararlarını ve **sıralama deneyinin** (görev 4) ölçülmüş sonuçlarını içerir.

```
FileLineSource ─str─▶ ParserStage ─LogRecord─▶ PredicateFilterStage* ─LogRecord─▶ ProjectionStage? ─ProjectedRecord─▶ FileSink
  (dosya okur)      (CLF ayrıştırır)          (kaydı eler; 0..n tane)            (alanları azaltır; 0..1)         (JSON Lines yazar)
```

`*` herhangi bir sayıda, `?` isteğe bağlı. Komut satırı (`main.py`) yalnızca verilen argümanlara karşılık gelen aşamaları hatta takar.

## 1. Sorumluluk dağılımı (aşama ayrıntı düzeyinde tek sorumluluk)

| Bileşim | Tek sorumluluğu | Bilmediği şey | Boyut |
|---|---|---|---|
| `PredicateFilterStage` | Koşulu sağlayan kaydı **olduğu gibi** iletmek | Koşulun ne olduğunu, kaydın nereden geldiğini | 17 satır |
| `ProjectionStage` | Kaydı seçilen alanlara indirgemek | Neden indirgendiğini, hangi kayıtların elendiğini | 19 satır |
| `FileSink` | Gelen öğeyi dosyaya yazmak, dosyayı açıp kapatmak | Öğenin nasıl üretildiğini | 21 satır |
| `PipelineBuilder` | Bileşenleri doğru sırada bir `Pipeline`'a bağlamak | Bileşenlerin ne yaptığını | 35 satır |
| `Pipeline` | Yaşam döngüsünü ve veri akışını yürütmek | Hiçbir somut aşamayı | — |

Koşullar (`min_status`, `path_prefix`, `time_between`) filtreden **ayrı** küçük fabrika fonksiyonlarıdır: "ne zaman ilet" kararı ile "iletme mekanizması" ayrı değişebilir. Yeni bir koşul yeni bir aşama gerektirmez.

## 2. Filtre ve dönüşüm aynı mimari öğedir

`Stage[I, O]` sözleşmesi tek bir metottur: `process(girdi, emitter)`. Aşama, girdi başına `emit` çağrısını **0, 1 ya da çok kez** yapabilir:

- **Filtre:** girdi başına 0 ya da 1 kez, aynı nesneyi, aynı türde.
- **Projeksiyon:** girdi başına 1 kez, yeni bir türde (`LogRecord → ProjectedRecord`).
- **Ayrıştırıcı:** girdi başına 0 ya da 1 kez, yeni bir türde (`str → LogRecord`).

Hat bu farkı bilmez; yalnızca "bir şey alır, yayar" der. Bu yüzden üçü de aynı `via(...)` ile eklenir ve birbirinin yerine konabilir. Kanıt olarak `experiment.py` içindeki `CountingStage`, **herhangi bir aşamayı sarmalayan** bir aşamadır ve hatta hiçbir değişiklik gerektirmeden takılır.

## 3. PipelineBuilder

```python
pipeline = (PipelineBuilder.from_(FileLineSource(girdi))
            .via(ParserStage())
            .via(PredicateFilterStage(min_status(400)))
            .via(ProjectionStage("timestamp", "clientIp", "status", "path"))
            .to(FileSink(cikti)))
pipeline.run()
```

- **`from_`:** Python'da `from` ayrılmış sözcük olduğu için başlangıç metodu `from_`.
- **Tür denetimi çalışma zamanındadır:** `via` bir `Stage`, `to` bir `Sink` olmayan nesneyi `TypeError` ile reddeder. Java'daki gibi derleme zamanında "bu aşamanın çıktı türü şu aşamanın girdi türüne uymuyor" denemez (bkz. §6).
- **Tek kullanımlık:** `to()` çağrıldıktan sonra aynı builder'a `via/to` çağrısı `RuntimeError` verir. Aşamalar durumludur (sayaçlar); aynı örneğin iki hatta paylaşılması sessiz hata kaynağı olurdu.
- **4. hafta:** Hattın hangi aşamalardan oluşacağı bugün `main.py:build_pipeline` içinde argümanlardan çıkarılıyor. 4. haftada bu bilgi yapılandırma dosyasından gelecek; builder aynen kalır, yalnızca onu çağıran kod değişir.

## 4. Yaşam döngüsü (lifecycle) — v2'den devralınan bir eksik

`FileSink`, `open()` ve `close()` olmadan çalışamaz. Ancak v2'deki `Pipeline.run()` yalnızca **kaynağı ve aşamaları** açıp kapatıyordu, **sink'e dokunmuyordu**; `Sink`'in `open()/close()` metodu da yoktu. Bu hafta gereken en küçük değişiklikler:

1. `interfaces.py`: `Sink`'e varsayılanı boş `open()` ve `close()` eklendi (mevcut sink'ler etkilenmez).
2. `pipeline.py`: `run()` bileşenleri **kaynak → aşamalar → sink** sırasıyla açar ve `ExitStack` ile tam ters sırada (LIFO) kapatır.

`ExitStack` seçimi bilinçlidir: bir aşama hata verse bile, **açılmış olan her bileşenin** `close()` metodu çağrılır. Açılışı başarısız olan bileşen kapatılmaz. Girdi dosyası bulunamazsa çıktı dosyası hiç oluşturulmaz (kaynak sink'ten önce açılır); bu davranış `tests/test_cli.py` içinde sabitlenmiştir.

### `close()` unutulursa ne olur? (ölçüldü)

`FileSink` metni arabelleğe alır. `close()` çağrılmadığında (CPython 3.13):

| Durum | Dosyadaki satır |
|---|---|
| `close()` yok, nesne hâlâ canlı | **0** |
| `close()` yok, nesne silinince (çöp toplayıcı) | 1 |
| `close()` yok, süreç zorla sonlandı (`os._exit`, çökme) | **0** |

Yani veri **bazen** kendiliğinden kurtulur, çünkü CPython dosya nesnesini yok ederken boşaltır. Bu bir **garanti değildir** (referans döngüleri, başka yorumlayıcılar, çökme). Hata bu yüzden çoğu zaman görünmez, tehlikeli olan da budur. `tests/test_sinks.py::test_output_is_buffered_until_close` bunu sabitler: yazma sonrası, `close()` öncesi dosya boştur; `close()` sonrası dolu.

**Önemli ders:** Bu sessizlik testleri de kandırır. İlk yazdığım test, `close()` içindeki `self._file.close()` satırı silindiğinde bile geçiyordu, çünkü hemen ardından gelen `self._file = None` son referansı düşürüp CPython'un dosyayı kendiliğinden boşaltmasına yol açıyordu. Test, dosya tutamacını dışarıda tutacak (`handle = sink._file`) ve `handle.closed` değerini doğrulayacak şekilde sıkılaştırıldı; mutasyon (kapatma satırını `pass` yapmak) artık 2 testi kırıyor.

Öğrencilerin hatayı kendilerinin yaşaması için öneri: `FileSink.close()` içindeki `self._file.close()` satırını yorum satırı yapın.
- `python -m unittest tests.test_sinks` → 2 test kırılır (veri diske inmedi).
- `python main.py data/access-small.log --min-status 400 -o /tmp/o.jsonl; wc -l /tmp/o.jsonl` → dosya **doğru görünür** (4 satır), çünkü CPython süreç biterken boşaltır. Programın "çalışıyor gibi" görünmesi ve hatanın yalnızca test ya da zorla sonlanmada ortaya çıkması, bu hatayı tehlikeli kılan şeydir.

Sink'in açılıp kapanmasının hiç çağrılmaması (v2'deki durum) farklı bir hatadır: `FileSink` açık olmadığı için ilk `consume` çağrısında `RuntimeError` verir (gürültülü). Bu senaryo `pipeline.py`'daki sink'i açılış listesinden çıkarınca 12 testi kırar.

## 5. Bileşilebilirlik deneyi: sıralama

Komut: `python experiment.py 100000 5` (100.000 satırlık, sabit tohumlu sentetik günlük, 5 tekrar).
Ölçülen: **çıktı özeti (SHA-256)**, her aşamanın **aldığı kayıt sayısı** (iş miktarı; deterministik) ve **süre** (makineye bağlı; yalnızca göreli okunmalı).

Veri: yolların ~%2'si `/api/admin`, ~%28'i `/api/v1`, geri kalanı statik; durum kodlarının ~%20'si ≥ 400 (yol ve durum bağımsız). Çalışma ortamı: Python 3.13.16.

### Sonuçlar

**0. Taban çizgisi (yalnızca oku + ayrıştır):** en iyi 2,071 s, ortanca 2,209 s.
Aşağıdaki koşuların süresinin büyük kısmı bu tabandır (Deney 1'de ~%94–95, Deney 2'de ~%85–95, çıktı yazmanın da eklendiği Deney 3'te ~%74–81); yani **ayrıştırma darboğazdır**.

**1. İki ucuz filtre: seçici olan önce mi, sonra mı?**

| Sıra | En iyi | Ortanca | Alınan kayıt (filtre1 + filtre2) | Çıktı özeti |
|---|---|---|---|---|
| `path-prefix(/api/admin)` → `status>=400` | 2,209 s | 2,245 s | 100.000 + 1.995 = **101.995** | `703f84e17402` |
| `status>=400` → `path-prefix(/api/admin)` | 2,173 s | 2,235 s | 100.000 + 20.003 = **120.003** | `703f84e17402` |

**2. Pahalı (regex) filtre ile ucuz-seçici filtre**

| Sıra | En iyi | Ortanca | Pahalı filtreye giren kayıt | Çıktı özeti |
|---|---|---|---|---|
| ucuz-seçici → pahalı | 2,174 s | 2,214 s | **1.995** | `211d9466020f` |
| pahalı → ucuz-seçici | 2,428 s | 2,481 s | **100.000** | `211d9466020f` |

**3. Filtre projeksiyondan önce mi, sonra mı?** (`status` projeksiyonda tutulduğu için iki sıra da geçerli)

| Sıra | En iyi | Ortanca | Projeksiyonun işlediği kayıt | Çıktı özeti |
|---|---|---|---|---|
| filtre → projeksiyon | 2,553 s | 2,780 s | **20.003** | `cf7c6e346536` |
| projeksiyon → filtre | 2,782 s | 2,935 s | **100.000** | `cf7c6e346536` |

### Okuma

**Sonuçlar aynı.** Üç karşılaştırmanın hepsinde çıktı dosyası bayt bayt aynıdır. Neden: filtreler kaydı değiştirmeyen, durumsuz koşullardır (VE işlemi değişmelidir) ve girdi sırasını korurlar. Aynı şey projeksiyon+filtre için de geçerlidir, **ancak yalnızca filtrenin ihtiyaç duyduğu alan projeksiyonda tutulduysa** (aşağıya bakın).

**Performans farklı, ama farkın büyüklüğü koşula bağlı:**

- **Deney 1 (iki ucuz koşul): süre farkı ölçülemez.** İş miktarı %15 azalır (101.995 ↔ 120.003 değerlendirme) ama süre farkı gürültü düzeyindedir (en iyi: %1,6; ortanca: %0,4) ve yönü, iş miktarının öngördüğünün **tersidir** (daha çok iş yapan sıra biraz daha hızlı çıktı). Bu, farkın gürültü olduğunun işaretidir. Koşullar o kadar ucuzdur ki toplam sürenin ~%94'ü ayrıştırmaya gider. Bu deneyin asıl dersi: **iş miktarı azalması ≠ süre azalması; ölç, tahmin etme.**
- **Deney 2 (pahalı koşul): fark gerçek.** Pahalı regex'e 100.000 yerine 1.995 kayıt girince 50 kat az regex çalışır. Pahalı filtre öne alınınca süre ~%12 **uzar** (2,174 s → 2,428 s; ortanca 2,214 s → 2,481 s). Genel kural: iki filtre için maliyet `c1 + s1·c2` ile `c2 + s2·c1` karşılaştırılır (c: kayıt başına maliyet, s: geçen oran); `c / (1 − s)` değeri **küçük olan önce** gelmelidir. Yani "ucuz **ve** seçici olan önce".
- **Deney 3 (projeksiyon):** Projeksiyon önce çalışınca 5 kat daha fazla nesne üretir (100.000 ↔ 20.003) ve süre ~%9 (en iyi: 2,553 s → 2,782 s) / ~%6 (ortanca: 2,780 s → 2,935 s) **uzar**.

### Ödünleşim (trade-off)

| | Filtre → projeksiyon (varsayılan) | Projeksiyon → filtre |
|---|---|---|
| İş miktarı | Daha az (elenen kayıt için projeksiyon yapılmaz) | Daha fazla |
| Filtre hangi alanları kullanabilir? | **Tümünü** (tam `LogRecord` görür) | Yalnızca projeksiyonda **tutulanları** |
| Çıkarılmış alanı kullanan filtre | — | `AttributeError` (sessiz yanlış sonuç değil) |
| Gizlilik | Kişisel alanlar filtre aşamasına kadar akar | Kişisel alanlar daha erken atılabilir |

Projeksiyonu öne almak performans açısından kaybettirir; geçerli nedeni **gizliliktir**: istenmeyen alan (ör. `clientIp`, `raw`) sonraki aşamalara, günlüklere ya da başka sink'lere hiç ulaşmaz. Bu durumda filtrenin ihtiyaç duyduğu alanlar tutulmalı, gerekirse sonda ikinci bir projeksiyon eklenmelidir. Bu, `tests/test_three_stage_pipeline.py::test_filter_after_projection_works_only_if_field_was_kept` ile gösterilmiştir. Komut satırı sırayı **filtre → projeksiyon** olarak sabitler.

### Ayrıştırmadan önce filtrelemek mümkün değil (ve neden)

`PredicateFilterStage` bir `LogRecord` bekler (`record.status`); ayrıştırıcıdan önce hat `str` taşır. Filtreyi ayrıştırıcıdan önce takınca çalışma zamanında `AttributeError: 'str' object has no attribute 'status'` alınır (`test_filter_placed_before_parser_cannot_work`). Java'da bu bir **derleme hatası** olurdu; Python'da hata ancak çalışırken ortaya çıkar. Ayrıştırma darboğaz olduğundan (~%75–95), kayıt düzeyinde bir koşulu ayrıştırmadan önce uygulamak cazip görünür, ama bunun için koşulun **ham satır** üzerinde çalışan farklı bir aşama (`Stage[str, str]`) olması gerekir (bu hafta yapılmadı).

### Bu ölçümün sınırları

- Tek makine, tek çalıştırma seti, Python 3.13; **sentetik** veri. Mutlak süreler değil, **yön ve oran** anlamlıdır.
- ~%2 altındaki farklar gürültüdür (Deney 1).
- İş miktarı sayıları deterministiktir ve her çalıştırmada aynı çıkar; süreler her çalıştırmada biraz değişir.
- Pahalı koşul (Deney 2) bilerek pahalı seçilmiş bir regex'tir; gerçek bir sistemde etki koşulun gerçek maliyetine bağlıdır.

## 6. Veri minimizasyonu (ProjectionStage)

- **İzin listesi (allow-list):** yalnızca adı geçen alanlar kalır; yeni bir alan eklendiğinde (5–7. haftalar) kendiliğinden **çıktıya girmez**.
- **`raw` alanı:** ham satırın tamamını (IP, user agent dahil) taşır. Projeksiyonda açıkça seçilmedikçe çıktıya girmez; aksi halde `--fields status` çalıştırıp IP'yi `raw` üzerinden sızdırmak mümkün olurdu (`test_privacy_raw_line_is_not_carried_unless_selected`).
- **`None` ile doldurmak yerine alanın yokluğu:** çıkarılmış alan `None` olarak dolaşsaydı, sonraki bir aşama "bilinmiyor" ile "atıldı" arasındaki farkı göremezdi; yokluk `AttributeError` ile hemen görünür.
- Çıktı da küçülür: satır başına yazılan bayt, seçilen alan sayısıyla azalır.

## 7. Bilinen sınırlar

- Aşama zincirinin tür uyumu (§3) yalnızca çalışma zamanında denetlenir.
- Hatalı satırlar hâlâ yalnızca sayılıyor (5. hafta).
- `PredicateFilterStage` koşulu hata fırlatırsa hat durur; hata yönetimi sonraki artımlarda.
