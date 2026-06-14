import os
import requests
import time
import re
import json
from urllib.parse import quote, urlparse
from bs4 import BeautifulSoup
import hashlib
from ddgs import DDGS

class DahuaImageDownloader:
    def __init__(self):
        self.download_folder = "Resimler"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en;q=0.8',
        })
        self.downloaded_count = 0
        self.failed_models = []
        self.seen_urls = set()
        
    def create_folders(self):
        """Klasör yapısını oluştur"""
        if not os.path.exists(self.download_folder):
            os.makedirs(self.download_folder)
            print(f"✅ '{self.download_folder}' klasörü oluşturuldu")
        
        # Başarısız modeller için log dosyası
        self.failed_log = os.path.join(self.download_folder, "failed_models.txt")
    
    def read_models_from_txt(self, txt_file_path):
        """TXT dosyasından model listesini oku"""
        try:
            with open(txt_file_path, 'r', encoding='utf-8') as file:
                models = []
                for line in file:
                    line = line.strip()
                    # Boş satırları ve yorum satırlarını atla
                    if line and not line.startswith('#'):
                        models.append(line)
            
            print(f"📖 {len(models)} model okundu: {txt_file_path}")
            return models
        except FileNotFoundError:
            print(f"❌ Dosya bulunamadı: {txt_file_path}")
            return []
        except Exception as e:
            print(f"❌ Dosya okuma hatası: {e}")
            return []
    
    def search_google_images(self, model_name):
        """DuckDuckGo Görsel araması yap (ddgs paketi üzerinden)"""
        queries = [
            f"{model_name} Dahua camera",
            f"{model_name} Dahua",
        ]
        all_image_urls = []
        for q in queries:
            try:
                print(f"  🔍 DDG'de aranıyor: {q}")
                with DDGS() as ddgs:
                    results = list(ddgs.images(q, max_results=8))
                for item in results:
                    url = item.get("image")
                    if url and url.startswith("http"):
                        all_image_urls.append(url)
                if all_image_urls:
                    print(f"  📸 {len(all_image_urls)} görsel bulundu")
                    break
            except Exception as e:
                print(f"  ⚠️ Arama hatası: {str(e)[:80]}")
                continue
        return list(dict.fromkeys(all_image_urls))[:5]
    
    def search_direct_sites(self, model_name):
        """Doğrudan Dahua ve satıcı sitelerinde ara"""
        # Model numarasını temizle (sondaki harfleri çıkararak daha geniş arama)
        base_model = re.sub(r'-[A-Z]+$', '', model_name)
        base_model = re.sub(r'-[0-9]+[A-Z]$', '', base_model)
        
        search_urls = [
            f"https://www.dahuasecurity.com/products/allProducts/1?keyword={quote(model_name)}",
            f"https://www.dahuasecurity.com/ceen/products/All-Products?keyword={quote(base_model)}",
            f"https://www.aliexpress.com/wholesale?SearchText={quote(model_name)}+Dahua+camera",
            f"https://www.amazon.com/s?k={quote(model_name)}+Dahua"
        ]
        
        image_urls = []
        
        for url in search_urls[:2]:  # Sadece Dahua siteleri dene
            try:
                print(f"  🔍 Dahua sitesinde aranıyor...")
                response = self.session.get(url, timeout=10)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Ürün görseli olabilecek elementler
                    img_elements = soup.find_all('img', src=re.compile(r'\.(jpg|png|jpeg|webp)', re.I))
                    
                    for img in img_elements:
                        img_url = img.get('src') or img.get('data-src')
                        if img_url:
                            if img_url.startswith('//'):
                                img_url = 'https:' + img_url
                            elif img_url.startswith('/'):
                                img_url = 'https://www.dahuasecurity.com' + img_url
                            
                            # Filtre: URL gerçekten bu modele ait olmalı
                            url_lower = img_url.lower()
                            model_tokens = [model_name.lower(), base_model.lower()]
                            # En az bir model token'ı URL'de geçmeli (zorunlu)
                            if not any(tok and tok in url_lower for tok in model_tokens):
                                continue
                            if any(black in url_lower for black in
                                   ['logo', 'icon', 'flag', 'social', 'banner', 'sprite']):
                                continue
                            image_urls.append(img_url)
                    
                    if image_urls:
                        break
                        
            except Exception as e:
                continue
        
        return list(dict.fromkeys(image_urls))[:3]
    
    def download_image(self, image_url, model_name, attempt=1):
        """Görseli indir ve kaydet"""
        if not image_url or not image_url.startswith(('http://', 'https://')):
            return False

        # Aynı URL daha önce başka model adıyla indirildiyse atla
        if image_url in self.seen_urls:
            print(f"  ⏭️  Bu URL başka model için zaten indirildi")
            return False
        self.seen_urls.add(image_url)
        
        # Dosya uzantısını belirle
        url_path = urlparse(image_url).path
        extension = os.path.splitext(url_path)[1].lower()
        
        if extension not in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
            # Content-Type'dan anlamaya çalış
            extension = '.jpg'  # varsayılan
        
        # Güvenli dosya adı oluştur
        safe_name = re.sub(r'[\\/*?:"<>|]', '_', model_name)
        file_hash = hashlib.md5(image_url.encode()).hexdigest()[:8]
        filename = f"{safe_name}_{file_hash}{extension}"
        filepath = os.path.join(self.download_folder, filename)
        
        # Aynı dosya zaten var mı kontrol et
        if os.path.exists(filepath):
            print(f"  ⏭️  Zaten var: {filename}")
            return True
        
        try:
            print(f"  📥 İndiriliyor: {image_url[:60]}...")
            
            # Görseli indir
            response = self.session.get(image_url, timeout=15, stream=True)
            response.raise_for_status()
            
            # Content-Type kontrolü
            content_type = response.headers.get('content-type', '')
            if 'image' not in content_type:
                print(f"  ⚠️ Görsel değil: {content_type}")
                return False
            
            # Dosyayı kaydet
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Dosya boyutu kontrolü
            file_size = os.path.getsize(filepath)
            if file_size < 5000:  # 5KB'dan küçükse
                os.remove(filepath)
                print(f"  ❌ Çok küçük dosya ({file_size} bytes)")
                return False
            
            print(f"  ✅ {filename} ({file_size/1024:.1f} KB)")
            self.downloaded_count += 1
            return True
            
        except Exception as e:
            print(f"  ❌ İndirme hatası: {str(e)[:50]}")
            return False
    
    def process_model(self, model_name):
        """Tek bir model için tüm arama yöntemlerini dene"""
        print(f"\n{'='*60}")
        print(f"📷 İşleniyor: {model_name}")
        print(f"{'='*60}")
        
        all_image_urls = []

        # Yöntem 1: DuckDuckGo görsel (asıl kaynak)
        print("  [1/2] DuckDuckGo görsel aranıyor...")
        ddg_images = self.search_google_images(model_name)
        all_image_urls.extend(ddg_images)

        # Yöntem 2: Yedek olarak satıcı siteleri
        if len(all_image_urls) < 2:
            print("  [2/2] Satıcı siteleri taranıyor...")
            site_images = self.search_direct_sites(model_name)
            all_image_urls.extend(site_images)
        
        # Benzersiz URL'leri al
        all_image_urls = list(dict.fromkeys(all_image_urls))
        
        if not all_image_urls:
            print(f"  ❌ Hiç görsel bulunamadı: {model_name}")
            self.failed_models.append(model_name)
            return False
        
        print(f"\n  📸 {len(all_image_urls)} görsel bulundu, indiriliyor...")
        
        # Görselleri indir (en fazla 3)
        downloaded = 0
        for i, img_url in enumerate(all_image_urls[:3], 1):
            if self.download_image(img_url, model_name, i):
                downloaded += 1
            time.sleep(1)  # Rate limiting
        
        if downloaded > 0:
            print(f"  ✅ {downloaded} görsel indirildi")
            return True
        else:
            print(f"  ❌ İndirme başarısız: {model_name}")
            self.failed_models.append(model_name)
            return False
    
    def save_failed_log(self):
        """Başarısız modelleri logla"""
        if self.failed_models:
            with open(self.failed_log, 'w', encoding='utf-8') as f:
                f.write("# İndirilemeyen modeller\n")
                f.write("# Bunları manuel olarak indirmeyi deneyin\n\n")
                for model in self.failed_models:
                    f.write(f"{model}\n")
            print(f"\n⚠️ {len(self.failed_models)} model indirilemedi: {self.failed_log}")
    
    def run(self, txt_file_path):
        """Ana çalıştırma fonksiyonu"""
        print("\n" + "="*60)
        print("📸 DAHUA KAMERA GÖRSEL İNDİRME ARACI")
        print("="*60)
        
        # Klasörü oluştur
        self.create_folders()
        
        # Modelleri oku
        models = self.read_models_from_txt(txt_file_path)
        
        if not models:
            print("❌ Hiç model bulunamadı. TXT dosyasını kontrol edin.")
            return
        
        # Her model için işlem yap
        for idx, model in enumerate(models, 1):
            print(f"\n📌 İlerleme: {idx}/{len(models)}")
            self.process_model(model)
            
            # İşlemler arasında bekle (sunucuyu yormamak için)
            if idx < len(models):
                time.sleep(3)
        
        # Rapor
        print("\n" + "="*60)
        print("📊 İŞLEM TAMAMLANDI!")
        print(f"✅ Başarıyla indirilen: {self.downloaded_count} görsel")
        print(f"📁 Kayıt konumu: {os.path.abspath(self.download_folder)}")
        print(f"📝 İşlenen model: {len(models)}")
        print("="*60)
        
        self.save_failed_log()

def choose_txt_file():
    """Script klasöründeki .txt dosyalarını listele ve kullanıcıya seçtir."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    txt_files = sorted(
        f for f in os.listdir(script_dir)
        if f.lower().endswith(".txt") and os.path.isfile(os.path.join(script_dir, f))
    )

    if not txt_files:
        print(f"❌ '{script_dir}' içinde hiç .txt dosyası yok.")
        manual = input("Dosya yolunu elle girin (boş = çık): ").strip()
        return manual or None

    print("\n📂 Bulunan TXT dosyaları:")
    for i, name in enumerate(txt_files, 1):
        size_kb = os.path.getsize(os.path.join(script_dir, name)) / 1024
        print(f"  {i}) {name}  ({size_kb:.1f} KB)")

    while True:
        choice = input(f"\nSeçim (1-{len(txt_files)}, Enter = 1): ").strip()
        if not choice:
            choice = "1"
        if choice.isdigit() and 1 <= int(choice) <= len(txt_files):
            return os.path.join(script_dir, txt_files[int(choice) - 1])
        print("⚠️ Geçersiz seçim, tekrar deneyin.")

def main(txt_path=None):
    print("\nDAHUA GÖRSEL İNDİRİCİ")
    print("-" * 40)

    # Komut satırı argümanından dosya yolu alınabilir
    if not txt_path:
        txt_path = choose_txt_file()

    if not txt_path:
        print("Çıkılıyor.")
        return

    print(f"✅ Kullanılacak dosya: {txt_path}")

    downloader = DahuaImageDownloader()
    downloader.run(txt_path)

if __name__ == "__main__":
    import sys
    try:
        # Komut satırı argümanı olarak model dosya yolu al
        txt_path = sys.argv[1] if len(sys.argv) > 1 else None
        main(txt_path)
    except KeyboardInterrupt:
        print("\n\n⚠️ İşlem kullanıcı tarafından durduruldu.")
    except Exception as e:
        print(f"\n❌ Beklenmeyen hata: {e}")
        print("Script'i kapatıp tekrar deneyin.")