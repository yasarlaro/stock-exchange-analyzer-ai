# AlphaVision Investment Methodology: Dual-Track & Multi-Factor Scoring

Bu doküman, AlphaVision sisteminin en kârlı 20 hisseyi seçerken kullandığı matematiksel filtreleri ve puanlama mantığını açıklar.

## 1. Dual-Track Filtreleme (Giriş Kapısı)
Hisselerin aday havuzuna girebilmesi için aşağıdaki iki kanaldan **en az birini** sağlaması gerekir:

### Kanal A: Turnaround (Dönüş Fırsatları)
- **Şart:** Son 6 ayda zirveden en az %25 düşüş (Drawdown).
- **Amaç:** Analistlerin hala güvendiği ancak piyasanın aşırı sattığı "Deep Value" fırsatlarını yakalamak.

### Kanal B: Momentum (Güçlü Büyüme)
- **Şart:** Fiyat > 200 Günlük Hareketli Ortalama (SMA200) VE Son 6 aylık getiri > %0.
- **Amaç:** Yükseliş trendindeki, rekor kıran ve önü açık olan lider teknoloji şirketlerini (Nvidia, Apple vb.) elenmekten kurtarmak.

---

## 2. Conviction Score Algoritması (100 Puan Üzerinden)
Aday havuzuna giren tüm hisseler aşağıdaki ağırlıklarla puanlanır:

1. **Upside Gap (%40):** (Analist Ortalama Hedef Fiyat / Mevcut Fiyat) - 1. 
   - *En yüksek kâr potansiyelini doğrudan ölçer.*
2. **Rating Drift (%30):** Son 30 gündeki analist notu değişim hızı.
   - *Analistlerin hisseye olan güveninin artıp artmadığını ölçer.*
3. **Consensus Strength (%20):** "Strong Buy" ve "Buy" diyen analistlerin yüzdesi.
   - *Sinyalin kurumsal bankalar arasındaki fikir birliğini ölçer.*
4. **EPS Momentum (%10):** Gelecek 12-24 aylık kâr tahminlerindeki yukarı yönlü revizyonlar.
   - *Hissenin temel kârlılığındaki iyileşmeyi doğrular.*

---

## 3. Leadership Rank (İstikrar Faktörü)
Sadece o hafta yükselen değil, listemizde **kalıcı** olan hisseler en güvenli olanlardır.
- **Puanlama:** Bir hisse haftalık listedeki her bir derecesi için puan toplar: `Points = (21 - Rank)`.
- **Liderlik Skoru:** `Toplam Haftalık Puanlar x Listede Kalınan Toplam Hafta`.
- **Çıktı:** Bu skor, analistlerin haftalarca arkasında durduğu ve "yanılma payı düşük" olan şampiyonları listeler.

---

## 4. Elenen Yöntemler ve Gerekçeler
- **Social Sentiment:** Manipülasyona açık olduğu için elendi; sadece kurumsal banka verisine (smart money) odaklanıldı.
- **Pure Technicals:** Sadece RSI/MACD gibi veriler "neden" sorusuna cevap vermediği için ana skorlamadan çıkarıldı, sadece ikincil onay olarak bırakıldı.
- **Fixed %25 Drawdown:** Sadece bu kriterin kullanılması "kazanan" hisseleri elediği için "Dual-Track" mimarisine geçilerek bu kısıt aşılmıştır.