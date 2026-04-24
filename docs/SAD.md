# Software Architecture Document (SAD): AlphaVision Equity Terminal

## 1. Executive Summary
**AlphaVision**, S&P 500 ve Nasdaq-100 evreninde maksimum kâr potansiyeline sahip ilk 20 hisseyi belirlemek için tasarlanmış hibrit bir yatırım terminalidir. Sistem, sadece düşüş yaşamış "Value" fırsatlarını değil, yükseliş trendindeki "Momentum" hisselerini de kapsayan **Dual-Track (Çift Kanallı)** bir seçim mimarisi kullanır.

## 2. Technical Stack
| Katman | Teknoloji | Notlar |
| :--- | :--- | :--- |
| **Interface** | **Streamlit** | Lokal dashboard ve görselleştirme için. |
| **Database** | **SQLite** | Haftalık raporlar ve liderlik takibi için. |
| **Data Engine** | **yfinance / Pandas** | Veri çekme ve puanlama motoru. |
| **Cloud Sync** | **Azure Blob Storage** | <$1/ay maliyetle haftalık DB yedekleme. |
| **Analysis** | **Claude Pro (UI)** | Üretilen raporların derinlemesine kalitatif analizi. |

## 3. High-Level Architecture
1. **Universe Builder:** S&P 500 ve Nasdaq-100 birleşiminden ~520 benzersiz ticker oluşturulur.
2. **Filtering Engine:** [METHODOLOGY.md](METHODOLOGY.md) içerisinde detaylandırılan "Dual-Track" filtreleme uygulanır.
3. **Scoring Engine:** Dört ana finansal metrik üzerinden "Conviction Score" hesaplanır.
4. **Historical Persistence:** Haftalık Top 20 sonuçları SQLite'a işlenerek "Leadership Rank" oluşturulur.
5. **UI Layer:** Streamlit üzerinden haftalık raporlar ve liderlik tablosu sunulur.

## 4. Database Schema
- `Stocks`: Ticker, Sector, Company Info.
- `Weekly_Reports`: Report_Date, Ticker, Score, Rank, Upside.
- `Leadership_Board`: Ticker, Streak, Total_Score, Avg_Rank.

## 5. Security & Backup
Azure Connection String `.env` dosyasında saklanır. `backup_to_azure()` fonksiyonu her hafta SQLite `.db` dosyasını Azure Blob Storage'a sürümleyerek yükler.