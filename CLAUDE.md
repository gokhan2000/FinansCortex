# DeepCortex Finans — Proje Anayasası (Claude için)

> Her oturumda otomatik okunur. **Kısa tutulur**: yalnızca her görevde gereken
> kurallar ve harita burada. Ayrıntı ilgili dosyada.
>
> **Son güncelleme:** 29 Eylül 2026

---

## Proje

Kişisel finansal analiz platformu: Dukascopy'den 9 global enstrümanın 15dk
verisi → DuckDB → Polars göstergeleri → Streamlit arayüzü + strateji backtest.
Faz 1 (veri + görüntüleme) bitti; Faz 2 (strateji/backtest) sürüyor.
Chandelier Exit ve Strateji 1 (EMA 10) **elendi**. Strateji 2 (Heikin Ashi)
ve varyantı 2.1 (%2 kâr al / %1 zarar kes / tek ters sinyalde çık) kuruldu,
ikisi de ölçülmedi — backtest'i kullanıcı çalıştıracak. Kural akışı ekranı
şema + mum grafiğini birlikte oynatıyor, adım adım (boşluk tuşu) modu var.
Sıradaki karar kullanıcıda → `docs/STRATEJI_GECMISI.md`.

## Kullanıcı hakkında

- Türkçe konuşuyor, **Türkçe yanıt** bekliyor.
- Komut satırıyla arası iyi değil — bir kez Python yorumlayıcısına (`>>>`)
  `streamlit run` yazmayı denedi. Bu yüzden her şey çift tıklanan `.bat` ya da
  `/baslat` ile. Komut satırı ayrıntısı anlatma.
- Proje 29 Eylül 2026'da GitHub'a taşındı (git kurulu, dal `main`):
  https://github.com/gokhan2000/FinansCortex . Kullanıcı git komutlarını
  bilmiyor → commit/push'u **yalnızca isterse** sen yap. `.gitignore` dışında
  tutulanlar: `data/`, `araclar/`, `yedek/`, `config/erisim.json`,
  `config/eposta.json`, `ADRES.txt` (gizli/büyük) — bunları asla ekleme.
  Büyük değişiklikten önce yine `yedek/`e kopya al (YEDEKLE.bat de sürüyor).
- Programı **işyerinde de** kullanıyor ("az veri taşıyarak"); iş bilgisayarına
  **hiçbir şey kurulamıyor**, orada yalnızca tarayıcı var.
- "Programı yavaşlatacak ve kararı engelleyecek yapılardan kaçınalım."
  Analiz felci istemiyor; **öneri sunup ilerle**.

## Değişmez çalışma kuralları

1. **Claude backtest çalıştırıp yorumlamaz; kullanıcı kendisi bakıyor.**
2. **Alarma inanmadan önce doğrula.** (Kalite ölçütü bir kez %14-19 "eksik gün"
   verdi, hepsi Pazar'dı.) Sonuç raporlamadan önce ölç.
3. Anayasadan sapmalar (DuckDB, 15dk, vektörel motor) **ölçüme dayalı bilinçli
   kararlar** — geri almadan önce `src/finans_cortex/CLAUDE.md`'deki gerekçeyi oku.
4. Her şey **UTC** saklanır; TR saati yalnızca ekranda.
5. `app.py` hiç SQL yazmaz; Dukascopy'ye özgü kod yalnızca `ingest.py`'de.
6. Arayüzü değiştirdiysen **sunucuyu yeniden başlat** — `ui/` ve `src/`
   modülleri Streamlit'in belleğinde kalır.

## Bağlam haritası — göreve göre ne okunur

| Görev | Oku |
|---|---|
| Veri, gösterge, strateji motoru kodu | `src/finans_cortex/CLAUDE.md` (dokununca kendiliğinden yüklenir) |
| Ekran, grafik, backtest paneli | `ui/CLAUDE.md` (dokununca kendiliğinden yüklenir) |
| Strateji fikri, "sırada ne var" | `docs/STRATEJI_GECMISI.md` |
| Çalıştırma, kurulum, uzaktan erişim, taşıma | `docs/KURULUM_VE_TASIMA.md` |
| Faz planı, asıl hedefler | `PROJE_ANAYASASI.md` |
| Diğer ölçüm raporları ve kaynak videolar | `docs/README.md` (harita) |

## Kök dizin

```
app.py              Giriş noktası + ekran yönlendirici (ince dosya)
ui/                 Arayüz ekranları
src/finans_cortex/  Veri katmanı + strateji motorları
scripts/            backfill.py (veri dolumu), clean_ghost_bars.py, *_report.py
                    (ölçüm raporları), uzaktan.py, eposta_ayarla.py, probe_*.py,
                    ac.py (ikon/yer imi başlatıcısı), kisayol.py (kısayol kurulumu)
config/             stratejiler.json (kayıtlı varyantlar), erisim.json, eposta.json
data/market.duckdb  ~200 MB, tüm veri
docs/               Proje belgeleri + ölçüm raporları (harita: docs/README.md)
BASLAT.bat          Çift tıkla → veri güncellenir, arayüz açılır (8503)
KISAYOL_OLUSTUR.bat Masaüstü/Başlat "DeepCortex" ikonu + Chrome yer imi kurar (1 kez)
.streamlit/         config.toml (toolbarMode = minimal: Deploy düğmesi yok)
UZAKTAN.bat         Çift tıkla → parola + Cloudflare tüneliyle internetten erişim
EPOSTA_AYARLA.bat   Adresin e-postayla gelmesini kurar (1 kez)
YEDEKLE.bat         Çift tıkla → proje (~450 KB) tarihli klasöre + data/ tek `veri-son` klasörüne, Google Drive'a
                    klasöre kopyalanır: G:\My Drive\DeepCortex-Yedek\
yedek/              Büyük değişiklik öncesi tek dosya kopyaları
```

## Hafızayı güncel tutma

- Bir md dosyası eklenir, silinir ya da adı değişirse **haritayı güncelle**
  (bu dosya + `docs/README.md`).
- Bir karar ya da bulgu çıktığında onu **ait olduğu dosyaya** yaz, buraya değil.
  Bu dosyaya yalnızca her görevde geçerli yeni bir kural eklenir.
- **Oturum sonu rutini:** kullanıcı `/guncelle` der (hafıza güncellenir, harita
  ve kaynaklar denetlenir), sonra `YEDEKLE.bat`'a çift tıklar.
- Bu yapı 21 Eylül 2026'da 600 satırlık tek dosyadan bölündü (eski hâli
  `yedek/`de). Kullanıcı yalnız Claude kullanıyor → `AGENTS.md` yok; Codex
  gelirse tek satırlık `AGENTS.md` ile buraya yönlendirilir.
