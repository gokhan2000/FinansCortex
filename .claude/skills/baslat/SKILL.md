---
name: baslat
description: DeepCortex Finans arayüzünü başlatır — önce verileri günceller, sonra Streamlit'i 8503 portunda açar. Kullanıcı "/baslat", "sistemi çalıştır", "programı aç", "uygulamayı başlat" dediğinde kullan. "/baslat hizli" veri güncellemesini atlar.
---

# DeepCortex Finans'ı başlat

`BASLAT.bat` ile aynı işi yapar, ama Claude uygulaması içinden (uzaktan da) çalışır.
Kullanıcıya Türkçe ve kısa yanıt ver; komut satırı ayrıntısı anlatma.

## Adımlar

1. **Zaten açık mı?** `http://localhost:8503/_stcore/health` 200 dönüyorsa uygulama
   çalışıyordur.
   - Argüman `hizli` ise: bir şey başlatma, doğrudan 4. adıma geç.
   - Değilse: önce sunucuyu durdur. Sebep: DuckDB tek yazıcıya izin verir; arayüz
     dosyayı tutarken veri güncellemesi yazamaz.
     - `preview_list`'te `finans-cortex` varsa `preview_stop` ile durdur.
     - Yoksa (başka bir sohbette ya da `BASLAT.bat` ile açılmış olabilir): 8503'ü
       dinleyen süreci bul (`Get-NetTCPConnection -LocalPort 8503 -State Listen`),
       python/streamlit olduğunu doğrula ve durdur. Başka bir programsa DURDURMA,
       kullanıcıya sor.

2. **Veri güncelleme** (argüman `hizli` DEĞİLSE): proje kökünde
   `python scripts/backfill.py` çalıştır (zaman aşımı 10 dk; normalde ~16 sn).
   Hata verirse kullanıcıya bildir ama yine de arayüzü eski veriyle aç.

3. **Arayüzü aç:** `preview_start` ile `finans-cortex` yapılandırmasını başlat
   (`.claude/launch.json`). İlk açılışta sayfa birkaç saniye boş görünür — bekle.

4. **Doğrula:** tarayıcı panelinde ekran görüntüsü al, konsol hatalarına bak. Ana
   ekranda DEEPCORTEX başlığı ve fiyat şeridi görünmeli.

5. **Kullanıcıya bildir:**
   - Çalıştığını ve adresi: `http://localhost:8503`
   - Aynı Wi-Fi'daki cihazlar için yerel ağ adresi (`ipconfig` çıktısındaki IPv4,
     ör. `http://192.168.1.6:8503`)
   - Veri güncellemesinin sonucu (kaç yeni satır / atlandı / hata)
   - Hatırlatma: uygulama bu Claude oturumu açık kaldıkça çalışır.
