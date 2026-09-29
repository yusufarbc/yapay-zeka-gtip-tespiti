# Benchmark sonuçları

22–29 Eylül 2026 arasında yapılan 22 ölçüm koşusunun özeti. Ham JSON raporları repodan kaldırıldı; `scripts/evaluate_gtip_benchmark.py` her koşuda yenisini `benchmark_results/` altına yazar (git'e girmez).

## Yöntem

- **Ground truth:** Ticaret Bakanlığı'nın gerçek BTB kararları. Her kayıt bir (eşya tanımı, resmî 12 haneli GTİP) çifti.
- **Numune:** 120 karar, fasıllara dengeli dağıtılmış, tohum 42.
- **Sızıntı önlemi:** Numunenin kendi kararı emsal havuzundan çıkarılır.
- **Uzman izi:** Sistem soru sorduğunda, uzman izi doğru dalı seçer. "+uzman" sütunu, müşavir soruları doğru cevaplasaydı ulaşılacak doğruluktur.
- **Metrikler:**
  - Fasıl: 2 hane. Pozisyon: 4 hane. GTİP: 12 hanenin tamamı.
  - Soru: kullanıcıya soru sorulan numune oranı.
  - p50: ortanca analiz süresi.

> **Karşılaştırılabilirlik uyarısı.** 29 Eylül 08:00'e kadar numuneler veritabanı satır sırasına bağlıydı ve aynı tohum farklı numuneler seçebiliyordu. 25 ve 29 Eylül koşuları 120 numunenin yalnız 60'ında örtüştü. Bu hata düzeltildi. Sonraki koşular (tablo 3 ve 4) birebir aynı numuneleri kullanır. Önceki koşular birbiriyle yaklaşık olarak karşılaştırılabilir.

## 1. Kanıt zinciri ve dolaşım düzeltmeleri (22–23 Eylül, gemini-2.5-flash)

| Koşu (UTC) | Değişiklik | Fasıl | Pozisyon | GTİP | GTİP +uzman | Soru |
|---|---|---|---|---|---|---|
| 22.09 11:33 | **Baseline:** model yalnız özet özellikleri görüyor; ham beyan, emsal ve fasıl notu kapalı | %13.3 | %12.5 | %5.0 | – | %40.0 |
| 22.09 12:03 | Ham beyan, BTB/EBTI emsalleri ve fasıl notları modele verildi | %38.3 | %36.7 | %22.5 | – | %10.8 |
| 22.09 14:29 | NO_MATCH çıkmazından kurtarma, yanlış faslı geri alma | %41.7 | %40.0 | %26.7 | %29.2 | %19.2 |
| 23.09 13:00 | Katalog açıklamaları hiyerarşisiyle yeniden çıkarıldı; seçenek kimlikleri koddan ayrıldı | %55.8 | %49.2 | %35.8 | %37.5 | %20.8 |
| 23.09 19:11 | Süre bütçesi, güven skoru kalibrasyonu | %53.3 | %47.5 | %35.0 | %35.8 | %18.3 |

23 Eylül düzeltmeleri sonrasında hiçbir koda bağlanamayan numune oranı ("ölü bölge") %35.8'den %1.7'ye indi.

## 2. Emsal yönlendirmesi ve seçim ilkeleri (25 Eylül, gemini-2.5-flash)

| Koşu (UTC) | Değişiklik | Fasıl | Pozisyon | GTİP | GTİP +uzman | Soru |
|---|---|---|---|---|---|---|
| 25.09 10:59 | Güçlü BTB emsalinde (benzerlik ≥ 0.80) fasıl seçimini atlayıp pozisyona yönlendirme **açık** | %59.2 | %55.0 | %43.3 | %45.0 | %11.7 |
| 25.09 11:30 | Aynı koşu, yönlendirme **kapalı** | %57.5 | %51.7 | %36.7 | %37.5 | %14.2 |
| 25.09 17:01 | Ürüne özel sabit kurallar ("cam balkon → Fasıl 76" gibi) kaldırıldı | %60.0 | %54.2 | %37.5 | %40.8 | %15.0 |
| 25.09 19:32 | Genel ilkeler: işlev malzemeden önce gelir; önce fasıl geri alma; tek ortak kelime emsal sayılmaz; numarasız talimatlar | %65.8 | %57.5 | %47.5 | %51.7 | %14.2 |

**Aday üretimi deneyi (25.09 10:10).** Fasıl seçimi yerine arama sonuçlarıyla aday pozisyon üretmek denendi. İlk üç adayda doğru pozisyonun bulunma oranı (recall@3):

| Aday yöntemi | recall@3 |
|---|---|
| Kelime eşleşmesi | %35.8 |
| Vektör araması | %46.7 |
| İkisinin birleşimi | %59.2 |

Birleşimin tek adayla doğruluğu (recall@1 %40.8), modelin fasıl fasıl dolaşımıyla o tarihte ulaştığı pozisyon doğruluğunun (23 Eylül: %47.5–49.2) altında kaldı. Bu yüzden arama yalnız güçlü BTB emsali olduğunda kısayol olarak kullanıldı; diğer durumlarda dolaşım korundu.

## 3. Ürün profili ve yeni adımların ablasyonu (29 Eylül, gemini-2.5-flash, aynı 120 numune)

Ürün profili, fasıl dışlama kontrolü ve fasıl uygunluk kontrolü eklendikten sonra doğruluk düştü. Adımlar tek tek kapatılarak sorumlu adım bulundu.

| Koşu (UTC) | Yapılandırma | Fasıl | Pozisyon | GTİP | GTİP +uzman | Soru | Profil sorusu | p50 |
|---|---|---|---|---|---|---|---|---|
| 29.09 08:19 | Hepsi açık | %54.2 | %46.7 | %34.2 | %40.8 | %20.0 | %13.3 | 14.9 sn |
| 29.09 08:10 | Üç yeni adım kapalı | %68.3 | %57.5 | %41.7 | %43.3 | %7.5 | – | 10.2 sn |
| 29.09 08:50 | Yalnız fasıl dışlama kapalı | %53.3 | %45.8 | %35.0 | %42.5 | %22.5 | %13.3 | 12.4 sn |
| 29.09 08:52 | Yalnız fasıl uygunluk kapalı | %52.5 | %46.7 | %33.3 | %39.2 | %22.5 | %13.3 | 16.1 sn |
| 29.09 08:52 | **Yalnız ürün profili kapalı** | %66.7 | %57.5 | %40.8 | %41.7 | %4.2 | – | 14.2 sn |
| 29.09 10:07 | Yalnız ürün profili kapalı (tekrar, gürültü ölçümü) | %67.5 | %57.5 | %40.8 | %41.7 | %5.0 | – | 14.2 sn |
| 29.09 10:10 | Profil açık; malzeme sorusu yalnız malzeme tarife pozisyonunu değiştiriyorsa | %62.5 | %53.3 | %37.5 | %40.8 | %10.0 | %0.8 | 15.7 sn |
| 29.09 11:09 | Profilin tahmini işlev/kullanım yeri satırları da çıkarıldı (**geri alındı**) | %55.8 | %49.2 | %34.2 | %39.2 | %14.2 | %0.8 | 16.6 sn |

- **Sorumlu adım ürün profiliydi.** Detaylı BTB tanımlarında gereksiz malzeme soruları soruluyordu (melodika, çocuk kitabı, mum). Fasıl dışlama ve uygunluk kontrolleri nötr çıktı.
- **Gürültü düşük.** Aynı yapılandırmanın iki koşusu arasındaki fark yaklaşık 1 puan.
- **Tahmini işlev satırı doğruluğa katkı veriyormuş.** Çıkarılınca fasıl doğruluğu 6.7 puan düştü (ör. airsoft bilyesi 9306 yerine 3926); geri eklendi.

29.09 07:25 koşusu (fasıl %50.8, GTİP %39.2) numune sırası hatası nedeniyle farklı numunelerle yapıldı ve karşılaştırmaya alınmadı.

## 4. Seçim modeli karşılaştırması (29 Eylül, aynı kod, aynı 120 numune)

| Model | Fasıl | Pozisyon | GTİP | GTİP +uzman | Soru | p50 |
|---|---|---|---|---|---|---|
| gemini-2.5-flash | %55.8 | %49.2 | %34.2 | %39.2 | %14.2 | 16.6 sn |
| **gemini-3.5-flash-lite** | %65.0 | %56.7 | %40.0 | %45.0 | %10.0 | 9.1 sn |
| gemini-3.5-flash | %70.8 | %64.2 | %52.5 | %55.0 | %5.0 | 16.2 sn |

- **3.5-flash:** En doğru model, ancak girdi/çıktı token maliyeti flash-lite'ın yaklaşık 5 katı.
- **3.5-flash-lite:** Maliyet/doğruluk dengesi için seçildi. 2.5-flash'tan hem daha doğru hem iki kat hızlı.
- **gemini-3.8-flash:** Ölçümü maliyet nedeniyle yarıda bırakıldı.

Bu koşular işlev satırının çıkarıldığı sürümle yapıldı. Satır geri eklendikten sonraki son sürüm (3.5-flash-lite) ayrıca ölçülmedi.
