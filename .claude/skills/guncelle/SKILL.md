---
name: guncelle
description: DeepCortex Finans PROJE HAFIZASINI günceller (verileri DEĞİL — veri güncellemesi /baslat ve Veri Merkezi ekranıdır). Oturumda alınan kararları ve bulguları ilgili md dosyalarına yazar, bağlam haritasını ve kaynakları denetler, kısa rapor verir. Kullanıcı "/guncelle", "hafızayı güncelle", "bağlamı denetle", "oturumu kapatıyoruz", "kaydet de çıkalım" dediğinde kullan.
---

# Proje hafızasını güncelle

Amaç: bu sohbette öğrenilen **kalıcı ve doğrulanmış** bilgiyi doğru dosyaya
yazmak, geçici olanı dışarıda bırakmak. Bir sonraki oturum hiçbir şey
anlatılmadan kaldığı yerden devam edebilmeli. Kullanıcıya Türkçe ve kısa yanıt ver.

## 1. Hafızayı güncelle

Sohbeti gözden geçir ve şunları ayıkla:
- Alınan **kararlar** ve gerekçeleri (kullanıcının kendi sözüyle, kısa alıntı)
- **Ölçülmüş / doğrulanmış** bulgular (rakamıyla)
- Kurulan / değişen özellikler
- Kullanıcının yeni tercihleri ya da itirazları
- Açık kalan işler

Dışarıda bırak: denenip vazgeçilen ara adımlar, doğrulanmamış tahminler,
yalnız bu sohbete ait ayrıntılar.

Her bilgiyi **ait olduğu dosyaya** yaz (haritaya bak: kökteki `CLAUDE.md`):

| Bilgi | Dosya |
|---|---|
| Veri, enstrüman, gösterge, motor, doğrulama | `src/finans_cortex/CLAUDE.md` |
| Ekran, grafik, panel | `ui/CLAUDE.md` |
| Strateji sonucu, sırada ne var, açık kararlar | `docs/STRATEJI_GECMISI.md` |
| Kurulum, uzaktan erişim, taşıma | `docs/KURULUM_VE_TASIMA.md` |
| Her görevde geçerli yeni kural / kullanıcı tercihi | kök `CLAUDE.md` |

Kurallar:
- Kök `CLAUDE.md` kısa kalır (~100 satırı geçmesin). Ayrıntıyı oraya yazma.
- Eskiyen bilgiyi **düzelt ya da sil**; çelişen iki kayıt bırakma.
- Kökteki "Son güncelleme" tarihini ve "Proje" paragrafındaki durum özetini güncelle.
- Büyük bir dosyayı baştan yazacaksan önce `yedek/` klasörüne kopyala (git yok).

## 2. Bağlamı denetle

- `docs/`, `ui/`, `src/finans_cortex/` ve kökteki `.md` dosyalarını listele.
- Haritada (kök `CLAUDE.md` + `docs/README.md`) olmayan yeni dosya var mı?
  Haritada olup diskte olmayan var mı? Haritayı düzelt.
- Kod haritası yanlış mı? Yeni modül / ekran / betik eklendiyse ilgili
  klasörün `CLAUDE.md`'sindeki listeye ekle.
- Kod yorumlarında eski belge atfı var mı (`grep -rn "CLAUDE.md bol"` vb.)?

## 3. Kaynakları denetle

- Bu oturumda projeye yeni bir girdi verildi mi (YouTube videosu, PDF, Excel,
  bağlantı)? Varsa `docs/README.md` > "Kaynaklar" tablosuna ekle (ne için
  kullanıldığıyla).
- Kaynağa atıf yapan belge kaynağı doğru adlandırıyor mu?

## 4. Rapor

Kullanıcıya en fazla 8 satır:
- Hangi dosyalara ne yazıldı (dosya başına bir satır)
- Haritada düzeltilen şey (varsa)
- Eklenen kaynak (varsa)
- Açık kalan işler (varsa)

Değişiklik gerekmediyse "Hafıza güncel, değişiklik yok" de.
