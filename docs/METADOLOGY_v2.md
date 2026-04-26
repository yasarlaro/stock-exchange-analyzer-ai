# AlphaVision Investment Methodology v2.0: Multi-Factor Quality & Momentum

Bu doküman, AlphaVision sisteminin S&P 500 ve Nasdaq-100 evreninde en yüksek potansiyele sahip liderleri seçmek için kullandığı matematiksel filtreleri ve hibrit puanlama mantığını açıklar.

## 1. Dual-Track Filtreleme (Giriş Kapısı)
Hisselerin aday havuzuna girebilmesi için aşağıdaki iki kanaldan **en az birini** sağlaması gerekir:

### Kanal A: Turnaround (Dönüş Fırsatları)
- **Şart:** Son 6 ayda zirveden en az %25 düşüş (Drawdown).
- **Amaç:** Analistlerin güveninin sürdüğü ancak piyasanın aşırı sattığı "Deep Value" fırsatlarını yakalamak.

### Kanal B: Momentum (Güçlü Büyüme)
- **Şart:** Fiyat > 200 Günlük Hareketli Ortalama (SMA200) VE Son 6 aylık getiri > %0.
- **Amaç:** Yükseliş trendindeki lider şirketleri elenmekten kurtarmak.

### [YENİ] Kalite Kapısı: Rule of 40 (Opsiyonel Filtre)
- **Şart:** (Yıllık Gelir Büyümesi + Serbest Nakit Akışı Marjı) > %20.
- **Amaç:** Sadece büyüyen değil, kâr üretebilen veya nakit yakımını kontrol eden "Kaliteli Büyüme" şirketlerini seçmek.

---

## 2. Conviction Score Algoritması (100 Puan Üzerinden)
Aday havuzuna giren tüm hisseler aşağıdaki yeni ağırlıklarla puanlanır:

1. **Upside Gap (%35):** (Analist Ortalama Hedef Fiyat / Mevcut Fiyat) - 1. 
   - *Kâr potansiyelini ölçer.*
2. **Rating Drift (%25):** Son 30 gündeki analist notu değişim hızı.
   - *Kurumsal güven artışını ölçer.*
3. **Relative Strength (%15):** Hissenin son 3-6 aydaki performansının S&P 500 endeksine oranı.
   - *Piyasadan pozitif ayrışan liderleri ödüllendirir.*
4. **Consensus Strength (%15):** "Strong Buy" ve "Buy" diyen analistlerin yüzdesi.
   - *Fikir birliğini ölçer.*
5. **EPS Momentum (%10):** Gelecek kâr tahminlerindeki yukarı yönlü revizyonlar.
   - *Temel kârlılık iyileşmesini doğrular.*

---

## 3. Leadership Rank (İstikrar Faktörü)
Haftalık listemizde **kalıcı** olan hisseler en güvenli olanlardır.
- **Puanlama:** `Points = (21 - Rank)`.
- **Liderlik Skoru:** `Toplam Haftalık Puanlar x Listede Kalınan Toplam Hafta`.
- **Çıktı:** Analistlerin ve piyasanın haftalarca arkasında durduğu "şampiyonları" listeler.

---

## 4. Elenen Yöntemler ve Gerekçeleri
- **RSI/MACD:** Çok fazla sinyal gürültüsü ürettiği ve stratejik (haftalık) bakış açısına uymadığı için elendi.
- **Sosyal Medya Duyarlılığı:** Manipülasyona açık ve spekülatif olduğu için kurumsal analiz dışı bırakıldı.
- **P/E Oranı (Fiyat/Kazanç):** Teknoloji ve büyüme şirketlerini (ADBE, NOW vb.) haksız yere elediği için yerine "Upside Gap" ve "Rule of 40" getirildi.