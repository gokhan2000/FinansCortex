# docs/ — bağlam haritası

> Hangi belge ne işe yarar ve ne zaman okunur. Hepsini her görevde okuma;
> yalnızca görevle ilgili olanı aç. Belge eklenir, silinir ya da adı değişirse
> bu harita güncellenir (`/guncelle` bunu denetler).

## Proje düzeyi

| Belge | İçerik | Ne zaman oku |
|---|---|---|
| `STRATEJI_GECMISI.md` | Denenen stratejiler, sonuçları, **sırada ne var**, açık kararlar | Strateji işi, "sırada ne var", yeni strateji fikri |
| `KURULUM_VE_TASIMA.md` | Kurulum, `/baslat`, veri güncelleme, uzaktan erişim kararları, başka makineye taşıma | Çalıştırma/kurulum sorunu, taşıma, uzaktan erişim |
| `../PROJE_ANAYASASI.md` | Asıl hedefler ve mimari kararlar (Gemini sohbetlerinden damıtılmış), Faz 1/Faz 2 | Faz planı, "anayasa ne diyordu", büyük mimari karar |

## Ölçüm raporları (tarihsel, değişmez)

| Belge | İçerik | Ne zaman oku |
|---|---|---|
| `VERI_KAYNAGI_BULGULARI.md` | Yahoo vs Dukascopy yoklaması — Yahoo neden elendi | Veri kaynağı değiştirme/ekleme |
| `CHANDELIER_BULGULARI.md` | Chandelier sinyal frekansı ölçümleri | Chandelier parametreleri |
| `BACKTEST_SONUCLARI.md` | Chandelier Exit'in elendiği backtest | Chandelier'ı yeniden denemeden önce |
| `EMA_IKI_KAPANIS_SONUCLARI.md` | Strateji 1 (EMA 10) sonuçları — elendi | Strateji 1 üzerinde çalışırken |
| `HEIKIN_ASHI_IKILI_SINYAL.md` | Strateji 2 (ve 2.1 varyantı) kuralları + koda uyarlama (sonuç yok) | Strateji 2 üzerinde çalışırken |
| `UZAKTAN_ERISIM.md` | İnternetten erişim: nasıl, neden, gizlilik sınırı (kullanıcıya yönelik) | Uzaktan erişim ayrıntısı |

## Klasör notları (kendiliğinden okunur)

Bunları elle açmaya gerek yok; Claude o klasördeki bir dosyaya dokunduğunda
otomatik yüklenir.

| Dosya | İçerik |
|---|---|
| `../src/finans_cortex/CLAUDE.md` | Veri, enstrümanlar, mimari sapmalar, strateji motoru yapısı, doğrulananlar, veri bozuklukları |
| `../ui/CLAUDE.md` | Ekran yapısı, backtest paneli, kural akışı, grafik kararları, veri tazeliği, modül önbelleği tuzağı |

## Kaynaklar (projeye verilen girdiler)

| Kaynak | Ne için kullanıldı |
|---|---|
| Gemini sohbetleri (4 adet, NotebookLM) | `PROJE_ANAYASASI.md`'nin kaynağı; ham hâlleri projede yok |
| YouTube `iNuqAD5ngro` — Sidar Demirgil, VİOP scalping | Strateji 1 kuralları |
| YouTube `dkX7PkoBzok` — Kripton Gezegeni, Heikin Ashi | Strateji 2 kuralları |
| YouTube `oEnVigmlHPA` — "Claude Code ve Codex'e Böyle Başla #2" | Bu bağlam yapısı (21 Eylül 2026) |
