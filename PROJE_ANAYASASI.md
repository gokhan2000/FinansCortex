# DeepCortex Finans Modülü — Proje Anayasası

> Bu doküman, 1 yıllık Gemini sohbetlerinin (NotebookLM üzerinden 4 kaynaktan) analiz edilip damıtılması ve sonrasında Claude ile yapılan derinleştirme görüşmesi sonucunda ortaya çıkan mimari kararların özetidir. VS Code / Claude Code'da kodlamaya başlarken bu dosya bağlam (context) olarak kullanılmalıdır.

**Son güncelleme:** 10 Ağustos 2026
**Durum:** Faz 1 (Altyapı) kararları netleşti. Faz 2 (Strateji/Backtest) ana hatlarıyla belirlendi, detaylandırma sürüyor.

---

## 1. Genel Felsefe ve Kaynak Değerlendirmesi

Proje, 4 farklı Gemini sohbetinden (Hızlı Mimari / HFT odaklı, Analiz Platformu Rehberi, Kendi Kendini Geliştiren Sistem, Global Macro Platform) gelen fikirlerin sentezidir. Bu kaynaklar zaman içinde çelişen öneriler içeriyordu (örn. C++/Rust vs. saf Python, Streamlit vs. Delphi). Aşağıdaki kararlar, bu çelişkiler değerlendirilerek **"önce sağlam ve basit altyapı, sonra karmaşıklık"** ilkesiyle netleştirilmiştir.

**Reddedilen / Ertelenen Fikirler ve Gerekçeleri:**
- **C++/Rust/Cython/ZeroMQ/Shared Memory (Kaynak 1):** Reddedildi. Bu, borsa kolokasyonlu kurumsal HFT firmalarının problemi. Aracı kurum API'si üzerinden emir gönderen bireysel bir sistemde ağ gecikmesi (50-200ms) zaten darboğaz; kod seviyesinde mikrosaniye optimizasyonu bu darboğazı aşamaz. Gereksiz karmaşıklık.
- **Delphi mimarisi (Kaynak 4):** Reddedildi. Geri kalan her şey Python/Streamlit üzerine kurulu; ayrı bir dil/ekosistem eklemek mimari tutarsızlık yaratır, gerekçesi net değil.
- **Agentic Reasoning / Multi-Agent Debate / Recursive Self-Improvement (Kaynak 3):** Faz 2'nin sonuna ertelendi. Önce tek, anlaşılır stratejilerle (Chandelier Exit) güvenilir backtest sonucu alınmalı; ajan tartışması ancak birden fazla strateji karşılaştırılacağı zaman anlamlı olur.
- **Qlib:** Faz 1'in zorunlu bileşeni DEĞİL. BIST verisi Qlib'in beklediği formatta değil (esas olarak ABD/Çin piyasaları için tasarlanmış), production-ready trading altyapısı değil, araştırma platformu. **Rolü:** Faz 2'de, el yapımı stratejiler (Chandelier Exit vb.) kanıtlandıktan sonra otomatik alfa/örüntü taraması (AlphaGen) için paralel bir araştırma kolu olarak değerlendirilecek.

---

## 2. FAZ 1 — Altyapı (Veri Çekme ve Görüntüleme)

**Hedef:** Verileri güvenilir şekilde çekip, doğru granülaritede saklayıp, görüntülemek. Faz 2'nin (analiz, backtest, strateji) ihtiyaçlarını karşılayacak sağlamlıkta bir temel olmalı.

### 2.1 Veri Kaynakları (katmanlı, tek noktaya bağımlı olmayan strateji)

| Katman | Kaynak | Kullanım Amacı | Bilinen Riskler |
|---|---|---|---|
| Ana/geliştirme (global) | `yfinance` | Faz 1 prototip, backtest, global varlıklar | Resmi olmayan API, 15-20dk gecikme, rate limit (429 hatası), stabilite garantisi yok |
| BIST canlı + geçmiş | **Algolab (Deniz Yatırım)** | Faz 2: gerçek zamanlı analiz, ileride emir iletimi | Hesap açma + API key gerekli |
| Kurumsal yedek (BIST) | BISTECH VERDA | Algolab kesintiye uğrarsa | Kurumsal başvuru süreci var, bireysel kullanım için ağır |
| Global yedek | Alpha Vantage / Polygon.io | yfinance kesilirse ikinci kaynak | Ücretli planlar gerekebilir |

**Mimari kural:** Veri sağlayıcı katmanı **pluggable (değiştirilebilir)** olmalı — sistemin geri kalanı "veri geldi" diye çalışmalı, hangi API'den geldiği detay kalmalı. Tek kaynağa mimari bağımlılık kurulmayacak.

### 2.2 Veri Depolama

- **TimescaleDB (PostgreSQL eklentisi)** — hem zaman serisi hem ilişkisel veri tek potada.
- **Tek gerçek kaynak (single source of truth):** En küçük granülarite (1 dakikalık bar) tek yerde saklanır. 5dk/15dk/1sa/günlük gibi üst zaman dilimleri **TimescaleDB'nin Continuous Aggregates** özelliğiyle otomatik türetilir — ayrı ayrı çekilip saklanmaz.
- **Etiketleme (Kaynak 4'ten alınan fikir):** `Unified_Ticker` benzeri bir tablo yapısıyla her varlık etiketlenir (örn. `BTC → [Crypto, High_Volatility, 24/7]`). Şu an aktif kullanılmasa da ileride korelasyon/analiz katmanı için maliyetsiz bir hazırlık.
- **Zaman dilimi:** Tüm veri UTC'de saklanır, görüntülemede TR saatine çevrilir.
- **Açık kalan detaylar (henüz netleşmedi, ileride ele alınacak):** BIST seans saatleri dışı boşlukların ele alınışı, eksik bar (missing data) politikası (forward-fill vb.).

### 2.3 İşlem / Hesaplama Katmanı

- **Polars** — Pandas yerine. Saf Python'da ekstra derlenmiş dil karmaşıklığı olmadan performans sağlar. Faz 1 indikatör hesaplamaları için yeterli.
- Numba/C++ gibi ağır optimizasyonlar **öngörülü olarak eklenmeyecek** — somut, ölçülmüş bir darboğaz ortaya çıkarsa o zaman değerlendirilecek.

### 2.4 Arayüz

- **Streamlit** — ama GeoCortex'te yaşanan yavaşlık deneyimi göz önünde bulundurularak **hibrit** kullanılacak:
  - Analiz/backtest/rapor ekranları → standart Streamlit rerun modeli yeterli.
  - Canlı fiyat/veri akışı → `st.fragment` ile izole edilip sadece o bileşen yenilenecek, tüm sayfa değil.
- Veri katmanı (TimescaleDB) ile arayüz katmanı **ayrık (decoupled)** tasarlanacak — ileride Streamlit'ten FastAPI+WebSocket tabanlı bir arayüze geçilirse veri katmanı etkilenmeyecek.
- Erken performans optimizasyonu yapılmayacak; somut bir tavan görülürse mimari o zaman revize edilecek.

### 2.5 Faz 1 Özet Akışı

```
[yfinance / Algolab] → normalize + UTC + etiketle (Unified_Ticker mantığı)
    → TimescaleDB (1dk ham veri + Continuous Aggregates ile üst zaman dilimleri)
    → Polars (indikatör hesaplama)
    → Streamlit + st.fragment (görüntüleme)
```

---

## 3. FAZ 2 — Strateji, Backtest, Analiz (ana hatlar)

**Hedef:** Piyasaların nabzını ölçmek, analiz yapmak, strateji geliştirip test etmek. Faz 1 altyapısı üzerine oturur.

### 3.1 Backtest Motoru

- **Backtrader** tercih edildi (Zipline yerine) — kendi veri kaynağınızı (TimescaleDB) esnek şekilde besleyebilme ve BIST'e daha kolay uyarlanabilirlik nedeniyle.
- TimescaleDB → Backtrader `PandasData` feed'ine (veya Polars → DataFrame dönüşümüyle) bağlanacak.

### 3.2 İlk Strateji: Chandelier Exit

- Chuck LeBeau'nun ATR tabanlı trailing-stop indikatörü, ilk strateji olarak belirlendi.
- Backtrader'ın hazır `bt.indicators.ATR` üzerine özel bir indikatör sınıfı olarak yazılacak (hazır gelmiyor, ATR üzerine kurulu basit bir eklenti).
- Long/short için ayrı üst/alt bant hesaplanacak (N-günlük tepe/dip ± ATR×katsayı). **Parametreler (ATR periyodu, çarpan) henüz netleşmedi.**

### 3.3 Maverick Mode (eğlenceli ama gerçek bir özellik)

Chandelier Exit stratejisine bir `mode` parametresi eklenecek:
- **Normal Mode (varsayılan):** Muhafazakâr ATR çarpanı, temkinli pozisyon boyutu, sıkı Sharpe/Drawdown kontrolü.
- **Maverick Mode:** Aynı strateji mantığı, daha dar stop mesafesi / daha agresif giriş eşiği ile çalışır. Kod tekrarı yok — tek strateji sınıfı, iki farklı parametre seti (`config_normal` / `config_maverick`).

Fikrin şaka olarak çıkmasına rağmen gerçek bir işlevi var: iki profili backtest'te yan yana koyup Sharpe/Drawdown'ı karşılaştırmak, ilerideki çoklu-strateji karşılaştırma altyapısının (bkz. 3.3 Strateji Geliştirme Sırası → adım 2) ilk somut örneği olabilir. Streamlit arayüzünde mod aktifken küçük bir görsel ipucu (rozet/tema rengi) eklenebilir.

### 3.4 Strateji Geliştirme Sırası

1. Tek strateji (Chandelier Exit), güvenilir backtest sonucu.
2. Birden fazla strateji karşılaştırması.
3. Ancak bu aşamadan sonra Multi-Agent Debate (Stratejist / Eleştirmen / Gemini Hakem) katmanı devreye girecek.

### 3.5 Gerçekçi Backtest Metrikleri

- **Sharpe Oranı** ve **Maximum Drawdown** zorunlu, merkezi metrikler.
- **Slippage & Tax Engine (Kaynak 4):** BIST'e özgü komisyon + BSMV + stopaj, Backtrader'ın `broker.setcommission` ile modellenecek. "Kağıt üstü getiri" ile "vergi/komisyon sonrası gerçek getiri" ayrımı zorunlu — canlıya alınacak hiçbir strateji bu adımdan geçmeden onaylanmayacak.

### 3.6 Qlib'in Konumu (netleştirildi)

Qlib, faz 1 altyapısının parçası değil. Faz 2'de, el yapımı stratejiler kanıtlandıktan sonra, TimescaleDB'deki temiz veri Qlib formatına çevrilerek **otomatik alfa/örüntü tarama (AlphaGen)** için paralel bir araştırma kolu olarak devreye alınacak.

---

## 4. Henüz Karara Bağlanmamış / Açık Konular

- BIST seans saatleri dışı veri boşluklarının ele alınış politikası.
- Eksik bar (missing data) doldurma stratejisi.
- Chandelier Exit için ATR periyodu ve çarpan parametreleri.
- Algolab hesabı açılıp açılmayacağı / ne zaman devreye alınacağı (şu an değerlendirme aşamasında).
- Faz 2'nin sonundaki Multi-Agent Debate sistem prompt tasarımı (Kaynak 3'te teklif edilmişti, henüz ele alınmadı).

---

## 5. Kaynak Notu

Bu doküman şu kaynakların sentezidir:
1. "Finans Projesi İçin Hızlı Mimari" (Gemini Chat)
2. "Finansal Analiz Platformu Kurulumu Rehberi" (Gemini Chat)
3. "Kendi Kendini Geliştiren Sistemin Başlangıç Pseudo Codeları" (Gemini Chat)
4. "Taslak Gemini" — Global Macro & Crypto-Financial Intelligence Platform (Yazı)

Ham sohbetler yerine bu damıtılmış karar dokümanının kullanılması, Kaynak 1'de bahsedilen "Hiyerarşik Bağlam Sıkıştırma" ilkesiyle uyumludur — token israfı yapılmadan, kod üretim aşamasında bu dosya doğrudan bağlam olarak verilebilir.
