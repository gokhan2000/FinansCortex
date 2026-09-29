# Uzaktan erişim — programı internetten açmak

**Tarih:** 18 Eylül 2026
**Kod:** `UZAKTAN.bat`, `EPOSTA_AYARLA.bat`, `scripts/uzaktan.py`,
`scripts/eposta_ayarla.py`, `ui/auth.py`, `src/finans_cortex/erisim.py`,
`src/finans_cortex/bildirim.py`

İstek: *"gizli bilgileri paylaşmadan, kod paylaşmadan, internetten ücretsiz
çalıştırabileceğim bir yapı"*.

---

## 1. Kurulan yapı

```
  İş bilgisayarı / telefon                 Ev bilgisayarı (program burada)
  ┌────────────────────┐                   ┌─────────────────────────────┐
  │  sadece tarayıcı   │  https  ┌──────┐  │  cloudflared  →  Streamlit  │
  │  (kurulum YOK)     │ ──────► │ CF   │ ►│  127.0.0.1:8503             │
  │                    │         │ ağı  │  │  ↑ parola kapısı            │
  └────────────────────┘         └──────┘  │  data/market.duckdb         │
                                           │  kod, config, stratejiler   │
                                           └─────────────────────────────┘
```

- **Kod ve veri hiçbir yere gitmez.** Dosyalar ev bilgisayarında kalır;
  dışarıya açılan şey yalnızca çalışan arayüzün ekranı.
- **Hesap açmak, kart vermek, kod yüklemek yok.** Cloudflare'in ücretsiz
  "hızlı tünel"i kayıt istemez.
- **Arayüz yalnızca 127.0.0.1'i dinler.** Tünel dışından (aynı Wi-Fi'daki
  başka bir cihaz dahil) doğrudan erişilemez.
- **Önünde parola vardır** (`ui/auth.py`). Parola girilmeden tek bir veri
  sorgusu bile çalışmaz.

## 2. Kullanım

### Evden çıkmadan önce (1 kez, 10 saniye)

`UZAKTAN.bat` dosyasına çift tıklayın ve **pencereyi açık bırakın**.

- İlk çalıştırmada: bir **parola** sorar (en az 8 karakter) ve tünel aracını
  indirir (~50 MB, `araclar/cloudflared.exe`). Bir daha sormaz.
- Ekrana adresi yazar: `https://……….trycloudflare.com`
- **Adresi size e-postayla yollar** (bir kez `EPOSTA_AYARLA.bat` ile
  kurulduysa) ve **OneDrive + Google Drive** klasörlerine
  `DeepCortex-ADRES.txt` olarak yazar. Hangisi işte açıksa onu kullanırsınız.
- Program açık kaldığı sürece **bilgisayar uykuya geçmez** (uyuyan
  bilgisayarda adres de ölürdü). Bu kalıcı bir ayar değildir; pencere
  kapanınca eski davranış döner.
- Veri güncellemesini atlamak için: `UZAKTAN.bat /hizli`

### İşteyken (kurulum YOK, sadece tarayıcı)

Adres size üç ayrı yoldan gelir; hangisi iş yerinde açıksa onu kullanın:

1. **E-posta** (en sağlamı — bulut depolama kapalı olsa da posta kutusu
   genelde açıktır): gelen kutunuzda *"DeepCortex Finans - erişim adresi"*
   başlıklı posta. Adresi kopyalayıp tarayıcıya yapıştırın.
2. **Google Drive:** drive.google.com → `DeepCortex-ADRES.txt`
3. **OneDrive:** onedrive.com → `DeepCortex-ADRES.txt`

Hepsi kapalıysa: telefonunuzdaki posta/Drive uygulamasından okuyup iş
bilgisayarına elle yazarsınız — adres kısadır.

Sonra: adres → parola ekranı → parolanız → program karşınızda.

**Veriyi uzaktan güncelleyebilirsiniz:** ana menü → **Veri Merkezi** →
*Verileri guncelle*. Düğmeye işteki tarayıcıdan basarsınız ama indirme ev
bilgisayarında yapılır (program orada çalışıyor). Aynı ekranda son barın
yaşı, varlık bazında kapsam ve kalite denetimi de var.

İş bilgisayarına **hiçbir şey kurulmaz**: ne Python, ne tünel aracı, ne
uzantı. Orada yalnızca bir web sayfası açılır.

### Kapatmak

Evdeki pencereyi kapatın. Tünel de arayüz de kapanır, adres ölür ve
OneDrive'daki dosyaya "şu an kapalı" yazılır — işte ölü adrese
uğraşmazsınız.

### E-posta kurulumu (bir kez, ~5 dakika)

`EPOSTA_AYARLA.bat` dosyasına çift tıklayın. Soracakları:

1. **Gönderen e-posta** — postayı yollayacak hesap (ör. kendi Yahoo adresiniz).
2. **Uygulama parolası** — ana parolanız DEĞİL. Yahoo/Gmail programlara ana
   parolayı vermez; hesabınızdan yalnızca bu program için geçerli, istediğiniz
   an iptal edebileceğiniz bir parola üretirsiniz:
   - **Yahoo:** Hesap Bilgileri → **Hesap Güvenliği** → *Uygulama parolası
     oluştur* → adını "DeepCortex" koyun → çıkan parolayı kopyalayın.
   - **Gmail:** Google Hesabı → Güvenlik → 2 Adımlı Doğrulama (açık olmalı)
     → *Uygulama şifreleri*.
3. **Adres hangi kutuya gelsin** — varsayılan gönderenin kendisi
   (kendinize yollar).

Kurulum sonunda **deneme postası** gönderilir; gelmezse ayar kaydedilmez ve
sebebi ekrana yazılır. Geldiyse artık her `UZAKTAN.bat` açılışında adres
oraya düşer.

Parola nerede duruyor? `config/eposta.json` içinde, **Windows'un kendi
şifrelemesiyle** (DPAPI). Düz metin hiçbir yere yazılmaz; dosya başka bir
bilgisayara kopyalansa bile orada çözülemez. Vazgeçerseniz `config/eposta.json`
dosyasını silmeniz yeter (ve dilerseniz Yahoo'daki uygulama parolasını iptal
edin).

## 3. Bilinmesi gerekenler

| | |
|---|---|
| Ev bilgisayarı açık olmalı mı? | **Evet**, ve `UZAKTAN.bat` penceresi açık kalmalı. Program orada çalışır; kapalıysa adres de çalışmaz. Ücretsiz + kod paylaşmadan olmasının bedeli budur. |
| Bilgisayar uyursa? | Program açıkken uyku **engellenir**. Ama dizüstüyseniz *kapağı kapatmak* ya da elle uyutmak yine uyutur — bunu yapmayın. Ekranın kararması sorun değil. |
| Adresi işte nasıl bulacağım? | E-postayla gelir; ayrıca Google Drive ve OneDrive klasörlerine `DeepCortex-ADRES.txt` olarak yazılır. |
| E-posta adresi ele geçse? | Adres tek başına yetmez: karşısındaki parola ekranını geçemez. Asıl sır **erişim parolanız**, o postada geçmez. |
| Adres sabit mi? | **Hayır**, her açılışta yenisi üretilir; bu yüzden adres OneDrive'a yazılıyor. Sabit adres seçenekleri: bölüm 4.5. |
| Aynı anda iki kopya? | Hayır. `BASLAT.bat` ile program açıkken `UZAKTAN.bat` çalışmaz ve bunu söyler — açık olan kopyada parola kapısı YOKTUR, yanlışlıkla korumasız yayına engel. |
| Parolayı unuttum | `config/erisim.json` dosyasını silin; `UZAKTAN.bat` bir sonraki açılışta yenisini sorar. |
| Parola nerede duruyor? | Hiçbir yerde. Dosyada yalnızca rastgele tuz + PBKDF2-SHA256 özeti var (240.000 tur). Süreçlere de parola değil bu özet geçer. |
| Yanlış parola denemeleri | Her yanlışta 1 sn bekletme, 5 yanlıştan sonra o oturum 60 sn kilit. |

## 4. Gizlilik — dürüst sınır

Trafik **Cloudflare'in ağından geçer**; şifreleme orada çözülüp yeniden
kurulur (herhangi bir ücretsiz tünel hizmetinde durum aynıdır). Yani:

- Dosyalarınız, kodunuz, veritabanınız **gitmez**.
- Ama o an ekranda ne gördüğünüz, teknik olarak Cloudflare'in geçtiği yoldur.

Bu sizin için kabul edilemezse bölüm 5.

## 4.5. Adres her seferinde değişmesin isterseniz

Ücretsiz Cloudflare tünelinde adres her açılışta değişir; bu yüzden OneDrive
yöntemi var. Sabit adres isterseniz iki yol:

- **ngrok ücretsiz hesap:** bir adet sabit adres verir (`….ngrok-free.app`),
  iş bilgisayarında yer imine eklersiniz, bir daha değişmez. Gereken: e-posta
  ile ücretsiz hesap + bir jetonu bir kez programa yapıştırmak. Sınır: ayda
  **1 GB trafik** (günlük kullanımda genelde yeter; ağır grafiklerde zorlar).
  İstenirse eklenir — `scripts/uzaktan.py` sağlayıcı seçimini destekleyecek
  şekilde yazıldı.
- **Kendi alan adınız + Cloudflare adlı tüneli:** yılda ~10 $, sınır yok.

## 5. Daha gizli seçenek — Tailscale (ücretsiz, kurulum ister)

İki bilgisayara da Tailscale kurulur ve aynı hesapla giriş yapılır; aralarında
uçtan uca şifreli (WireGuard) özel bir ağ kurulur. Adres sabit kalır
(`http://ev-bilgisayari:8503`) ve trafik **hiçbir üçüncü tarafın okuyabileceği
yerden geçmez**.

Şartı: **iş bilgisayarına program kurabiliyor olmak**. Kurumsal makinelerde
çoğu zaman yasaktır; bu yüzden varsayılan olarak Cloudflare seçildi.
İstenirse eklenir (birkaç satırlık iş: Streamlit'i `--server.address 0.0.0.0`
yerine Tailscale arayüzüne bağlamak yeterli).

## 6. Tavsiyeler

- Adresi kimseyle paylaşmayın; adresi bilen parola ekranına ulaşır.
- Parolayı başka yerde kullandığınız bir parola yapmayın.
- İşiniz bitince pencereyi kapatın — açık kalan tünel gereksiz risk.
- İş bilgisayarında tarayıcıya parolayı kaydettirmeyin.
- `araclar/` klasörü (50 MB) başka makineye **taşınmaz**; gerekirse orada
  yeniden iner. "Hafif taşıma"da `config/` gider, `data/` ve `araclar/` kalır.
- `config/eposta.json` taşınabilir ama **içindeki parola yeni bilgisayarda
  çözülemez** (Windows kullanıcısına bağlı); orada `EPOSTA_AYARLA.bat`
  yeniden çalıştırılır.
- Uygulama parolasını istediğiniz an sağlayıcının hesap ayarlarından iptal
  edebilirsiniz; ana parolanız etkilenmez.
