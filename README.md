# resim-indir

TXT dosyasındaki model adlarına göre toplu ürün görseli indiren bir Python aracı. Başlangıçta Dahua güvenlik kameraları için geliştirildi, fakat herhangi bir model/ürün listesiyle çalışır.

Arama için **DuckDuckGo görsel** (asıl kaynak) ve yedek olarak satıcı sitelerini kullanır. Her model için en fazla 3 görsel indirir; başarısızlar `Resimler/failed_models.txt` dosyasına yazılır.

## Özellikler

- TXT dosyasından çoklu model okuma (yorum satırı `#` desteklenir)
- Script klasöründeki `.txt` dosyalarını listeleyen interaktif seçim menüsü
- Model adı zorunlu URL filtresi (banner / logo / sprite çöplüğünü eler)
- Aynı URL'i farklı modele tekrar kaydetmeyi engelleyen global URL takibi
- Çok küçük dosya / yanlış Content-Type dosyalarını otomatik atar
- Başarısız modeller için ayrı log

## Kurulum

```bash
git clone https://github.com/1000inci/resim-indir.git
cd resim-indir
pip install -r requirements.txt
```

## Kullanım

1. Aynı klasöre model listesi içeren bir `.txt` dosyası koy (örn. `models.txt`):
   ```
   # Yorum satırı
   IPC-HFW1230TC1-SA
   NVR2104HS-T
   ```
2. Script'i çalıştır:
   ```bash
   python resim.py
   ```
3. Açılan menüden TXT dosyasını seç. Görseller `Resimler/` klasörüne iner.

## Çıktı

```
Resimler/
├── IPC-HFW1230TC1-SA_74d169df.jpg
├── IPC-HFW1230TC1-SA_6f59a878.jpg
├── NVR2104HS-T_b50bbdf4.jpg
└── failed_models.txt   # (varsa) indirilemeyen modeller
```

Dosya adı formatı: `{ModelAdı}_{URLHash}.{uzantı}`

## Gereksinimler

- Python 3.8+
- requests, beautifulsoup4, ddgs (bkz. [requirements.txt](requirements.txt))
