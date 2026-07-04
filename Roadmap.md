# Crime Intelligence Dashboard Roadmap

## 1. Proje Amacı

Bu projenin amacı, NYPD Complaint Historic verisi üzerinden suç olaylarını zamansal ve coğrafi olarak analiz eden, kısa vadeli yoğunluk tahminleri üreten ve karar vericilere açıklanabilir içgörüler sunan bir crime intelligence dashboard geliştirmektir.

İlk ürün hedefi kişi odaklı tahmin yapmak değildir. Ürün, aşağıdaki operasyonel sorulara cevap vermelidir:

- Hangi bölgelerde suç yoğunluğu artıyor?
- Hangi suç tipleri hangi zamanlarda yükseliyor?
- Geçmiş trendlere göre gelecek hafta veya ay hangi bölgelerde yoğunluk bekleniyor?
- Normalden sapma gösteren bölge/suç tipi kombinasyonları neler?
- Harita üzerinde hotspot alanları nerede oluşuyor?

## 2. Mevcut Veri Durumu

Projede başlangıç veri kaynağı:

```text
data/raw/NYPD_Complaint_Data_Historic.csv
```

Veri yaklaşık 10 milyon satır ve 35 kolondan oluşmaktadır. Öne çıkan kolon grupları:

- Olay tarihi ve saati: `CMPLNT_FR_DT`, `CMPLNT_FR_TM`, `CMPLNT_TO_DT`, `CMPLNT_TO_TM`, `RPT_DT`
- Suç tipi ve kategori: `OFNS_DESC`, `PD_DESC`, `LAW_CAT_CD`, `KY_CD`, `PD_CD`
- Konum: `BORO_NM`, `ADDR_PCT_CD`, `Latitude`, `Longitude`, `X_COORD_CD`, `Y_COORD_CD`
- Mekan türü: `PREM_TYP_DESC`, `LOC_OF_OCCUR_DESC`, `JURIS_DESC`
- Mağdur ve şüpheli demografisi: `VIC_AGE_GROUP`, `VIC_RACE`, `VIC_SEX`, `SUSP_AGE_GROUP`, `SUSP_RACE`, `SUSP_SEX`

Demografik alanlar yüksek eksiklik ve etik risk içerdiği için ilk model girdisi olarak kullanılmamalıdır. Bu alanlar yalnızca veri kalite ve fairness incelemesi için değerlendirilmelidir.

## 3. Ürün İlkeleri

- Model birey, ırk, cinsiyet veya yaş grubu bazında suçluluk tahmini yapmayacaktır.
- Dashboard karar destek aracı olarak tasarlanacaktır; otomatik yaptırım veya devriye kararı üretmeyecektir.
- Model çıktıları her zaman geçmiş trend, güven aralığı ve veri kalitesi bağlamıyla birlikte gösterilecektir.
- Öncelik açıklanabilir, denetlenebilir ve operasyonel olarak anlaşılır metriklerdir.
- İlk sürümde mükemmel model yerine güvenilir veri pipeline'ı ve doğru problem tanımı hedeflenecektir.

## 4. MVP Kapsamı

İlk MVP şu yetenekleri içermelidir:

- Genel suç trendleri
- Borough ve precinct bazlı karşılaştırma
- Suç tipi dağılımı
- Gün, hafta, ay ve saat bazlı desenler
- Harita üzerinde suç yoğunluğu
- Hotspot görünümü
- Haftalık bölge/suç tipi bazlı olay sayısı tahmini
- Beklenmeyen artışları gösteren anomali listesi
- Modelin son eğitim tarihi, veri aralığı ve bilinen sınırlamaları

MVP dışı bırakılacak konular:

- Kişi veya şüpheli profilleme
- Gerçek zamanlı polis yönlendirme
- Otomatik risk skoru ile yaptırım önerisi
- Demografik gruplara göre suçluluk tahmini

## 5. Faz 1: Veri Keşfi ve Kalite Analizi

Amaç: Ham veriyi anlamak, riskli alanları tespit etmek ve modellemeye uygun veri sözlüğü çıkarmak.

Yapılacaklar:

- CSV kolonlarının veri tiplerini çıkarmak
- Tarih aralığını belirlemek
- Satır sayısı, eksik değer oranları ve benzersiz değer sayılarını hesaplamak
- `BORO_NM`, `ADDR_PCT_CD`, `OFNS_DESC`, `LAW_CAT_CD` dağılımlarını analiz etmek
- Koordinatların geçerli NYC sınırları içinde olup olmadığını kontrol etmek
- Hatalı tarih, saat, yaş grubu ve kategori değerlerini işaretlemek
- Yıllara göre veri tutarlılığını incelemek
- Veri kalite raporu üretmek

Beklenen çıktı:

```text
reports/data_quality_report.md
data/processed/schema_profile.json
```

## 6. Faz 2: Temiz Veri ve Agregasyon Pipeline'ı

Amaç: Ham olay verisini model ve dashboard için kullanılabilir hale getirmek.

Yapılacaklar:

- `CMPLNT_FR_DT` ve `CMPLNT_FR_TM` alanlarından standart olay zamanı üretmek
- Boş, `(null)` ve geçersiz değerleri normalize etmek
- Suç tipi kategorilerini sadeleştirmek
- Borough, precinct ve koordinat alanlarını temizlemek
- Olayları haftalık ve aylık zaman kovalarına gruplamak
- Olay seviyesinden agregat model tablosu üretmek

Önerilen ana model tablosu:

```text
week_start | borough | precinct | offense_type | law_category | crime_count
```

Beklenen çıktı:

```text
data/processed/complaints_clean.parquet
data/processed/crime_weekly_area.parquet
data/processed/crime_monthly_area.parquet
```

## 7. Faz 3: Analitik Baseline

Amaç: Modelden önce dashboard'un temel analitik değerini oluşturmak.

Yapılacaklar:

- Yıllık, aylık ve haftalık suç trendlerini çıkarmak
- Borough ve precinct bazlı sıralamalar oluşturmak
- Suç tipi bazlı trendleri analiz etmek
- Saat ve haftanın günü desenlerini çıkarmak
- İlk heatmap ve yoğunluk analizini üretmek
- En hızlı artan ve azalan suç tipi/bölge kombinasyonlarını belirlemek

Beklenen çıktı:

```text
reports/exploratory_analysis.md
data/processed/dashboard_summary.json
```

## 8. Faz 4: Baseline Tahmin Modeli

Amaç: ML modelinden önce karşılaştırma yapılabilecek basit ve güçlü tahmin temelleri kurmak.

İlk hedef değişken:

```text
Belirli bir precinct veya borough içinde, belirli bir suç tipi için gelecek haftanın olay sayısı.
```

Baseline yaklaşımlar:

- Geçen haftanın değerini tahmin olarak kullanmak
- Son 4 haftanın ortalamasını kullanmak
- Son 8 haftanın ağırlıklı ortalamasını kullanmak
- Önceki yılın aynı haftasını referans almak

Değerlendirme metrikleri:

- MAE
- RMSE
- Weighted MAE
- Top-K yoğunluk yakalama oranı
- Zaman bazlı backtesting sonucu

Beklenen çıktı:

```text
models/baseline_forecast/
reports/baseline_model_report.md
data/processed/baseline_predictions.parquet
```

## 9. Faz 5: Makine Öğrenmesi Modeli

Amaç: Baseline modelleri aşan, açıklanabilir ve operasyonel olarak kullanılabilir bir tahmin modeli geliştirmek.

Önerilen ilk model:

- LightGBM veya XGBoost tabanlı regresyon modeli

Önerilen feature grupları:

- Zaman: hafta, ay, yıl, haftanın günü, sezon
- Coğrafya: borough, precinct, patrol boro
- Suç tipi: `OFNS_DESC`, `LAW_CAT_CD`
- Gecikmeli değerler: son 1, 2, 4, 8 hafta olay sayıları
- Rolling istatistikler: hareketli ortalama, standart sapma, minimum, maksimum
- Trend sinyalleri: son 4 hafta değişim oranı, son 8 hafta değişim oranı

Kullanılmaması önerilen ilk alanlar:

- `SUSP_RACE`
- `SUSP_SEX`
- `SUSP_AGE_GROUP`
- `VIC_RACE`
- `VIC_SEX`
- `VIC_AGE_GROUP`

Bu alanlar ilk modelde hem eksiklik hem de etik risk nedeniyle dışarıda tutulmalıdır.

Beklenen çıktı:

```text
models/weekly_forecast/
reports/ml_model_report.md
data/processed/ml_predictions.parquet
```

## 10. Faz 6: Hotspot ve Anomali Katmanı

Amaç: Dashboard'a tahmin dışında intelligence değeri sağlayan iki ayrı analitik katman eklemek.

Hotspot yaklaşımı:

- Precinct bazlı yoğunluk skoru
- Grid veya H3 bazlı yoğunluk skoru
- Son 7, 30 ve 90 güne göre ağırlıklı yoğunluk
- Suç tipi filtresiyle harita katmanı

Anomali yaklaşımı:

- Bölge/suç tipi bazlı tarihsel ortalamadan sapma
- Rolling mean ve rolling standard deviation
- Z-score veya robust z-score
- Mevsimsel beklenen değerden sapma

Beklenen çıktı:

```text
data/processed/hotspots.parquet
data/processed/anomalies.parquet
reports/anomaly_methodology.md
```

## 11. Faz 7: Dashboard Tasarımı

Amaç: Model ve analitik çıktılarını operasyonel olarak anlaşılır bir ürüne dönüştürmek.

Önerilen ekranlar:

### Overview

- Toplam olay sayısı
- Seçili tarih aralığına göre trend
- En çok görülen suç tipleri
- Borough karşılaştırması
- Haftalık değişim göstergeleri

### Map

- Heatmap
- Precinct veya grid katmanı
- Suç tipi filtresi
- Tarih aralığı filtresi
- Hotspot overlay

### Trends

- Zaman serisi grafikleri
- Suç tipi kırılımı
- Borough/precinct karşılaştırması
- Saat ve gün desenleri

### Forecast

- Gelecek hafta veya ay tahmini
- Gerçekleşen vs tahmin grafiği
- Güven aralığı
- En yüksek artış beklenen bölgeler

### Anomalies

- Normalden yüksek artışlar
- Bölge, suç tipi ve tarih bilgisi
- Tarihsel ortalamayla karşılaştırma
- Öncelik seviyesi

### Governance

- Veri aralığı
- Model versiyonu
- Son eğitim zamanı
- Eksik veri uyarıları
- Kullanım sınırları

## 12. Önerilen Teknik Mimari

Başlangıç için pratik mimari:

```text
Raw CSV
  -> Data cleaning pipeline
  -> Processed Parquet files
  -> Feature pipeline
  -> Forecast, hotspot, anomaly outputs
  -> API
  -> Dashboard
```

Önerilen araçlar:

- Veri işleme: DuckDB, Polars veya PySpark
- Modelleme: scikit-learn, LightGBM, XGBoost
- API: FastAPI
- Dashboard: React veya Next.js
- Harita: Mapbox GL, Deck.gl veya Leaflet
- Depolama: Parquet ile başlangıç, ileride Postgres/PostGIS
- Deney takibi: MLflow veya basit model registry dosya yapısı

## 13. Önerilen Repo Yapısı

```text
data/
  raw/
  processed/
notebooks/
src/
  data/
  features/
  models/
  evaluation/
  api/
dashboard/
models/
reports/
```

## 14. Sprint Planı

### Sprint 1: Veri Profiling

- Veri sözlüğü çıkar
- Eksik değer analizi yap
- Tarih ve lokasyon kalite kontrollerini çalıştır
- İlk veri kalite raporunu üret

Başarı kriteri:

- Hangi kolonların güvenilir, eksik veya riskli olduğu netleşmiş olmalı.

### Sprint 2: Temizleme ve Agregasyon

- Temiz olay tablosu üret
- Haftalık bölge/suç tipi agregasyonunu oluştur
- Dashboard için özet metrikleri hazırla

Başarı kriteri:

- Model ve dashboard aynı temizlenmiş tablodan beslenebilir hale gelmeli.

### Sprint 3: İlk Analitik Dashboard Prototipi

- Trend grafikleri
- Borough/precinct karşılaştırmaları
- Suç tipi dağılımları
- İlk harita görünümü

Başarı kriteri:

- Model olmadan bile veri keşfi yapılabilecek bir dashboard prototipi olmalı.

### Sprint 4: Baseline Forecast

- Baseline tahmin yöntemlerini kur
- Backtesting yap
- Metrikleri raporla
- Tahmin çıktılarını dashboard formatına getir

Başarı kriteri:

- Gelecek hafta suç sayısı için karşılaştırılabilir baseline metrikleri oluşmalı.

### Sprint 5: ML Forecast Model

- Feature pipeline kur
- İlk LightGBM/XGBoost modelini eğit
- Baseline ile karşılaştır
- Tahmin sonuçlarını kaydet

Başarı kriteri:

- ML modeli baseline'dan anlamlı şekilde iyi veya en azından açıklanabilir şekilde karşılaştırılmış olmalı.

### Sprint 6: Hotspot ve Anomaly

- Hotspot skorlarını üret
- Anomali kurallarını tanımla
- Harita ve anomali ekranlarına veri sağla

Başarı kriteri:

- Dashboard yalnızca geçmişi göstermemeli, dikkat edilmesi gereken değişimleri de öne çıkarmalı.

### Sprint 7: Ürün Sertleştirme

- API katmanını oluştur
- Dashboard filtrelerini iyileştir
- Model versiyonlama ekle
- Veri ve model sınırlamalarını görünür yap

Başarı kriteri:

- Proje demo edilebilir, tekrarlanabilir ve geliştirilebilir bir MVP seviyesine gelmeli.

## 15. İlk Yapılacaklar

Başlamak için en doğru ilk işler:

1. `reports/` ve `src/` klasör yapısını oluşturmak
2. Veri kalite/profiling script'i yazmak
3. Ham CSV'den örneklem ve tam veri profili çıkarmak
4. Temizlenmiş tarih, lokasyon ve suç tipi kolonlarını üretmek
5. Haftalık agregasyon tablosunu oluşturmak
6. İlk baseline tahminini çalıştırmak
7. Dashboard wireframe'ini çizmek

İlk teknik milestone:

```text
Ham NYPD verisinden haftalık precinct/suç tipi bazlı temiz agregasyon tablosu üretmek.
```

Bu milestone tamamlanmadan model veya dashboard geliştirmeyi büyütmek doğru değildir.

## 16. Başarı Metrikleri

Ürün başarısı:

- Kullanıcı seçtiği bölge ve tarih aralığında suç trendini hızlıca anlayabiliyor mu?
- Dashboard artışları ve anomalileri açık şekilde gösterebiliyor mu?
- Harita, tablo ve grafikler aynı veri tanımından besleniyor mu?
- Tahmin sonuçları baseline ile kıyaslanabiliyor mu?

Model başarısı:

- ML modeli naive baseline'dan daha iyi mi?
- Hata oranı düşük hacimli bölgelerde kontrol altında mı?
- En yüksek riskli görünen bölgeler geçmiş backtest'te anlamlı şekilde yakalanıyor mu?
- Model çıktıları açıklanabilir mi?

Veri başarısı:

- Temizleme pipeline'ı tekrarlanabilir mi?
- Eksik ve hatalı veri oranları raporlanıyor mu?
- Yeni veri geldiğinde aynı pipeline çalışabiliyor mu?

## 17. Riskler ve Önlemler

### Veri Kalitesi

Risk: Tarih, lokasyon ve kategori alanlarında hatalar olabilir.

Önlem: Veri kalite raporu ve temizleme kuralları ilk sprintte zorunlu olmalıdır.

### Etik ve Yanlılık

Risk: Demografik alanların yanlış kullanımı ayrımcı sonuçlara yol açabilir.

Önlem: İlk modelde demografik alanlar kullanılmamalı, ürün bölge ve zaman agregasyonuna odaklanmalıdır.

### Yanlış Güven

Risk: Kullanıcı model tahminini kesin gerçek gibi yorumlayabilir.

Önlem: Dashboard tahminleri güven aralığı, geçmiş hata ve açıklama ile göstermelidir.

### Performans

Risk: 10M+ satırlık CSV doğrudan dashboard veya notebook içinde yavaş çalışabilir.

Önlem: İşlenmiş Parquet tabloları ve agregasyon katmanı kullanılmalıdır.

### Model Karmaşıklığı

Risk: Erken aşamada karmaşık model geliştirmek ürün ilerlemesini yavaşlatır.

Önlem: Önce baseline, sonra ML modeli yaklaşımı izlenmelidir.

## 18. Nihai Hedef

Projenin hedef ürünü:

```text
NYC Crime Intelligence Dashboard
```

Bu ürün, geçmiş suç verisini temizleyip analiz eden, bölgesel ve zamansal trendleri gösteren, hotspot ve anomali alanlarını işaretleyen, kısa vadeli suç yoğunluğu tahmini yapan ve tüm çıktıları açıklanabilir şekilde sunan bir karar destek dashboard'u olmalıdır.
