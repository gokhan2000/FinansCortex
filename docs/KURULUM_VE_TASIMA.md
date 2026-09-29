# Kurulum, çalıştırma, uzaktan erişim ve taşıma

> Programın nasıl kurulup çalıştırıldığı ve başka makineye nasıl taşındığı.
> Uzaktan erişimin tam belgesi: `docs/UZAKTAN_ERISIM.md`.

---

## Kurulum ve çalıştırma

```
pip install -r requirements.txt
```

**Arayüz:** `BASLAT.bat` dosyasına çift tıklayın. (Veya terminalde —
Python yorumlayıcısında değil — `streamlit run app.py`)

**Claude uygulaması içinden (uzaktan da):** sohbete `/baslat` yazın
(`.claude/skills/baslat/SKILL.md`). Önce veriyi günceller, sonra
`.claude/launch.json` içindeki `finans-cortex` ayarıyla 8503'te açar.
`/baslat hizli` güncellemeyi atlar. Aynı Wi-Fi'dan: `http://192.168.1.6:8503`.

**Veri güncelleme:** `BASLAT.bat` bunu zaten açılışta yapar. Elle çalıştırmak
için `python scripts/backfill.py`. Kaldığı yerden devam eder, istenildiği kadar
tekrar çalıştırılabilir. Sıfırdan tam dolum ~23 dakika; günlük artımlı
güncelleme ~16 saniye.

**Kalite kontrolü:** `python scripts/clean_ghost_bars.py` (rapor)
veya `--apply` (siler).

**`/baslat` tuzağı — "No .claude/launch.json found":** oturum başka bir
klasörde açılıp sonradan projeye taşındıysa tarayıcı paneli `launch.json`'u
hâlâ eski klasörde arar. Çözüm: o klasörün `.claude/launch.json`'una
`cmd /c "cd /d C:\gs\finans-cortex && python -m streamlit run app.py ..."`
yazan bir kayıt koymak, ya da sohbeti doğrudan proje klasöründe açmak.

---

## Tek tıkla başlatma: ikon ve Chrome yer imi (21 Eylül 2026)

Kullanıcı: *"Chrome'a bir kısayol ikonu ekle, oraya basıp başlatayım"* →
seçimi "ikisi de". Chrome güvenlik gereği yerel programı kendisi başlatamaz;
ikon da yer imi de aynı küçük başlatıcıyı çalıştırır: `scripts/ac.py`
(`pythonw` ile, siyah pencere açmaz).

- **Kurulum:** `KISAYOL_OLUSTUR.bat` (bir kez; başka makinede yeniden).
  Masaüstü + Başlat menüsü "DeepCortex" kısayolu (ikon:
  `ui/assets/deepcortex.ico`, Pillow ile çizilir), `deepcortex:` bağlantı
  türü (HKCU, yalnız bu kullanıcı) ve Chrome'da yer imi sayfası
  (`ui/assets/yer_imi.html` — düğme yer imleri çubuğuna sürüklenir; Chrome'un
  yer imi dosyasına DOKUNULMAZ). Kaldırma: `KISAYOL_OLUSTUR.bat /kaldir`.
  Görev çubuğuna sabitlemeyi Windows 11 programlara yaptırmıyor; kullanıcı
  masaüstü ikonuna sağ tıklayıp sabitler.
- **Davranış:** program açıksa ikinci kopya AÇMAZ, Chrome'da uygulama
  penceresini (`--app`, sekmesiz) açar. Kapalıysa `BASLAT.bat /uygulama`'yı
  küçültülmüş konsolda başlatır (o pencere kapanınca program kapanır) ve
  Chrome'u `ui/assets/acilis.html` ile açar; sayfa `favicon.png`'yi
  `<img>` ile yoklar, program hazır olunca kendiliğinden geçer (4 dk sınır).
- **Hata dersi (aynı gün):** ilk sürüm `cmd /c start DeepCortex /min ...`
  kullanıyordu. `start` tırnaklı ilk argümanı pencere başlığı sayar;
  subprocess "DeepCortex"i tırnaksız geçirince Windows onu program sandı →
  *"Windows cannot find 'DeepCortex'"*, BASLAT hiç başlamadı, açılış ekranı
  sonsuza kadar "Veriler güncelleniyor…" dedi. Kullanıcı bunu "verileri
  güncellemede kalıyor" diye bildirdi; Claude önce yanlış yere (veri
  kütüphanesi) baktı. Düzeltme: `start` yok, `CREATE_NEW_CONSOLE` +
  `SW_SHOWMINNOACTIVE`. **Başlatıcı denerken çocuk sürecin gerçekten
  başladığını işlem listesinden doğrula.** Doğrulandı: tetikleme → BASLAT +
  backfill + tek Streamlit (8 sn); ikinci tetikleme → ikinci kopya yok.

## Yedekleme (21 Eylül 2026)

Git olmadığı için kod ve belgelerin tek kopyası proje klasöründe.
**`YEDEKLE.bat`** (çift tık) projeyi `G:\My Drive\DeepCortex-Yedek\YYYY-MM-DD_SSDD\`
klasörüne kopyalar (Drive yoksa OneDrive'a, o da yoksa proje klasörünün bir
üstüne). `robocopy` ile; `data/` (Dukascopy'den yeniden iner), `araclar/`
(cloudflared kendiliğinden iner), `__pycache__`, `ADRES.txt`, `*.log`
kopyalanmaz. Doğrulandı: 61 dosya, ~450 KB, 1 saniye. `config/erisim.json`
Drive'a gider — yalnızca tuzlu PBKDF2 özeti, parola geri çıkarılamaz.
Geri yükleme: yedek klasörünün içeriğini proje klasörüne kopyalamak.

---

## Uzaktan erişim (18 Eylül 2026)

Kullanıcı: *"gizli bilgileri paylaşmadan, kod paylaşmadan, internetten
ücretsiz çalıştırabileceğim bir yapı"*. Kurulan: **`UZAKTAN.bat`** →
`scripts/uzaktan.py` → Cloudflare "hızlı tünel" (hesap istemez, ücretsiz)
+ arayüzün önünde parola kapısı. Tam belge: `docs/UZAKTAN_ERISIM.md`.

Kararlar ve gerekçeleri:
- **Kod hiçbir yere yüklenmez.** Streamlit Community Cloud / HF Spaces
  elendi: hepsi depoya kod ister. Tünel yalnızca çalışan ekranı dışarı açar.
- **Arayüz 127.0.0.1'i dinler** (`--server.address`), tünel dışından
  erişilemez. `BASLAT.bat` ise eskisi gibi tüm arayüzlerde dinler.
- **Parola kapısı** `ui/auth.py`, `app.py`'de yönlendiriciden ÖNCE çağrılır;
  parola girilene kadar veri katmanına sorgu gitmez. Yalnızca
  `FINANS_ERISIM` ortam değişkeni varsa (yani UZAKTAN.bat'la açıldıysa)
  devrede — kendi bilgisayarında her açılışta parola sormak gereksiz.
- Parola **saklanmaz**: `config/erisim.json` içinde tuz + PBKDF2-SHA256
  özeti (240k tur, ~0,17 sn). Süreçlere de parola değil "tuz:özet" jetonu
  geçer. 5 yanlışta 60 sn oturum kilidi, her yanlışta 1 sn bekletme.
- **8503 doluysa UZAKTAN.bat çalışmaz** ve sebebini yazar: açık olan kopya
  BASLAT.bat'la açılmıştır ve onda parola kapısı yoktur — yanlışlıkla
  korumasız yayını engeller.
- Ücretsiz tünelde **adres her açılışta değişir** (ADRES.txt'ye yazılır,
  kapanışta silinir). Sabit adres → alan adı (ücretli) ya da Tailscale.
- Dürüst sınır: trafik Cloudflare'in ağından geçer (TLS orada sonlanır).
  Dosyalar gitmez ama üçüncü taraf istenmiyorsa Tailscale seçeneği var;
  kullanıcı "iş bilgisayarına kurulum yapamam / bilmiyorum" dediği için
  varsayılan Cloudflare seçildi.
- `araclar/cloudflared.exe` (55 MB) ilk çalıştırmada GitHub'daki resmi
  sürümden iner. Taşınmaz; hedef makinede gerekirse yeniden iner.
- **"Uzaktan UZAKTAN.bat'ı nasıl çalıştıracağım?"** (kullanıcının haklı
  sorusu): çalıştırmıyor — evden çıkmadan önce bir kez çift tıklayıp
  pencereyi açık bırakıyor. Windows açılışına otomatik başlatma teklif
  edildi, **istemedi** ("elle başlatacağım"). Asıl sorun adresin işte
  öğrenilmesiydi: adres artık **OneDrive klasörüne** `DeepCortex-ADRES.txt`
  olarak da yazılıyor (bilgisayarda OneDrive kurulu ve çalışıyor); işte
  tarayıcıdan onedrive.com ya da telefondaki OneDrive uygulamasından
  okunuyor. Kapanışta aynı dosyaya "şu an kapalı" yazılır.
- **Adres iletimi (kullanıcı: "OneDrive'a girebileceğimden emin değilim,
  işyerinde orası da kapalı")**: adres artık üç yoldan gidiyor —
  **e-posta** (`bildirim.py`, SMTP+SSL; kurulumu `EPOSTA_AYARLA.bat`,
  deneme postası göndermeden ayarı kaydetmez), **Google Drive** ve
  **OneDrive** klasörleri (ikisi de bu makinede kurulu; Drive `G:\My Drive`
  olarak bağlı), artı proje kökündeki ADRES.txt. E-posta parolası
  ("uygulama parolası") `config/eposta.json` içinde **Windows DPAPI** ile
  şifreli; düz metin hiçbir yerde yok ve dosya başka makineye taşınırsa
  çözülemez. Yahoo SMTP'ye erişim bu ağdan doğrulandı (AUTH destekli).
- **Uyku engeli:** program açıkken `SetThreadExecutionState` ile uyku
  engellenir (kalıcı güç ayarı DEĞİŞTİRİLMEZ, süreç bitince geri döner).
  Dizüstü kapağını kapatmak yine uyutur — belgede yazıyor.
- Kullanıcının kesin şartı: **iş bilgisayarına hiçbir şey kurulamıyor.**
  Kurulan yapı bunu karşılıyor (orada yalnızca tarayıcı). Tailscale ve ngrok
  seçenekleri bu yüzden varsayılan DEĞİL.

Doğrulandı (18.09.2026): araç indi, tünel açıldı, dışarıdan HTTP 200 ve
Streamlit yüklendi (websocket tünelden sorunsuz geçiyor), dışarıdan gelen
ziyaretçi parola ekranını görüyor, doğru parola arayüzü açıyor, yanlış
parola sayacı çalışıyor. Test bitince tünel kapatıldı.

---

## Başka makineye taşıma

İki seçenek:
- **Hafif (~100 KB):** `data/` klasörü HARİÇ her şeyi kopyalayın, hedef
  makinede `pip install -r requirements.txt` + `python scripts/backfill.py`
  çalıştırın. İnternet gerekir, ~23 dakika sürer.
- **Tam (~185 MB):** klasörün tamamını kopyalayın. İnternet gerekmez, anında hazır.

Python 3.12 gerekiyor. `BASLAT.bat` sabit bir Python yolu aramıyor —
`python` veya `py` komutunu PATH üzerinden kendiliginden buluyor. Bu sayede
program hangi bilgisayara taşınırsa taşınsın (Python'un kurulu olduğu klasör
farklı olsa bile) çift tıklamayla çalışır. Tek şart: o makinede
`pip install -r requirements.txt` çalıştırılmış olması.

`config/eposta.json` başka makinede çözülemez (DPAPI); orada
`EPOSTA_AYARLA.bat` yeniden çalıştırılır. `config/erisim.json` (parola özeti)
taşınır ve çalışır.
