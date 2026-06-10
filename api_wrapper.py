"""
Resim-İndir API Wrapper
Web entegrasyonu için API endpoints
"""

from flask import Flask, jsonify, request, send_file
from datetime import datetime
import os
import json
from pathlib import Path
import threading
import subprocess

app = Flask(__name__)

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
RESIMLER_DIR = os.path.join(os.path.dirname(__file__), 'Resimler')

# Arka planda çalışan indirme işlemlerini takip et
DOWNLOAD_JOBS = {}

def ensure_directories():
    """Gerekli klasörleri oluştur"""
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    os.makedirs(RESIMLER_DIR, exist_ok=True)

ensure_directories()

class ResimIndirManager:
    """Resim indirme yöneticisi"""

    @staticmethod
    def validate_models_file(file_path):
        """Model dosyasını valide et"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            models = []
            for line in lines:
                line = line.strip()
                # Yorum satırlarını ve boş satırları atla
                if line and not line.startswith('#'):
                    models.append(line)

            return {
                'valid': True,
                'total_lines': len(lines),
                'model_count': len(models),
                'models': models
            }
        except Exception as e:
            return {
                'valid': False,
                'error': str(e)
            }

    @staticmethod
    def start_download(job_id, models, options=None):
        """Arka planda indirme başlat"""
        job_file = os.path.join(UPLOADS_DIR, f'models_{job_id}.txt')

        # Model dosyasını oluştur
        with open(job_file, 'w', encoding='utf-8') as f:
            for model in models:
                f.write(model + '\n')

        DOWNLOAD_JOBS[job_id] = {
            'status': 'running',
            'started': datetime.now().isoformat(),
            'models_count': len(models),
            'progress': 0,
            'completed': 0,
            'failed': 0,
            'log_file': job_file
        }

        # Arka planda indirmeyi çalıştır
        def run_download():
            try:
                # Python script'ini çalıştır
                result = subprocess.run(
                    ['python', os.path.join(os.path.dirname(__file__), 'resim.py'), job_file],
                    cwd=os.path.dirname(__file__),
                    capture_output=True,
                    timeout=3600
                )

                DOWNLOAD_JOBS[job_id]['status'] = 'completed' if result.returncode == 0 else 'error'
                DOWNLOAD_JOBS[job_id]['output'] = result.stdout.decode('utf-8', errors='ignore')

            except Exception as e:
                DOWNLOAD_JOBS[job_id]['status'] = 'error'
                DOWNLOAD_JOBS[job_id]['error'] = str(e)
            finally:
                DOWNLOAD_JOBS[job_id]['ended'] = datetime.now().isoformat()

        thread = threading.Thread(target=run_download, daemon=True)
        thread.start()

        return job_id

    @staticmethod
    def get_job_status(job_id):
        """İndirme işleminin durumunu getir"""
        if job_id not in DOWNLOAD_JOBS:
            return None
        return DOWNLOAD_JOBS[job_id]

    @staticmethod
    def list_downloaded_images():
        """İndirilen görselleri listele"""
        if not os.path.exists(RESIMLER_DIR):
            return []

        images = []
        for file in os.listdir(RESIMLER_DIR):
            if file.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                file_path = os.path.join(RESIMLER_DIR, file)
                images.append({
                    'filename': file,
                    'size': os.path.getsize(file_path),
                    'created': datetime.fromtimestamp(os.path.getctime(file_path)).isoformat()
                })

        return sorted(images, key=lambda x: x['created'], reverse=True)

    @staticmethod
    def get_failed_models():
        """Başarısız modelleri getir"""
        failed_file = os.path.join(RESIMLER_DIR, 'failed_models.txt')
        if not os.path.exists(failed_file):
            return []

        with open(failed_file, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]


@app.route('/api/validate', methods=['POST'])
def api_validate():
    """Model dosyasını valide et"""
    if 'file' not in request.files:
        return jsonify({'error': 'Dosya gerekli'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Dosya seçilmedi'}), 400

    # Dosyayı geçici olarak kaydet ve valide et
    temp_path = os.path.join(UPLOADS_DIR, file.filename)
    file.save(temp_path)

    result = ResimIndirManager.validate_models_file(temp_path)

    if result['valid']:
        return jsonify(result)
    else:
        return jsonify(result), 400


@app.route('/api/download/start', methods=['POST'])
def api_download_start():
    """İndirme işlemini başlat"""
    data = request.get_json()
    models = data.get('models', [])

    if not models:
        return jsonify({'error': 'Model listesi gerekli'}), 400

    job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    ResimIndirManager.start_download(job_id, models)

    return jsonify({
        'job_id': job_id,
        'status': 'started',
        'models_count': len(models)
    })


@app.route('/api/download/status/<job_id>', methods=['GET'])
def api_download_status(job_id):
    """İndirme durumunu kontrol et"""
    status = ResimIndirManager.get_job_status(job_id)

    if status is None:
        return jsonify({'error': 'İş bulunamadı'}), 404

    return jsonify(status)


@app.route('/api/images', methods=['GET'])
def api_images_list():
    """İndirilen görselleri listele"""
    images = ResimIndirManager.list_downloaded_images()
    return jsonify({
        'total': len(images),
        'images': images
    })


@app.route('/api/failed-models', methods=['GET'])
def api_failed_models():
    """Başarısız modelleri getir"""
    failed = ResimIndirManager.get_failed_models()
    return jsonify({
        'total': len(failed),
        'models': failed
    })


@app.route('/image/<filename>', methods=['GET'])
def get_image(filename):
    """Görseli indir"""
    file_path = os.path.join(RESIMLER_DIR, filename)

    if not os.path.exists(file_path):
        return jsonify({'error': 'Dosya bulunamadı'}), 404

    return send_file(file_path)


@app.route('/health', methods=['GET'])
def health():
    """Sağlık kontrolü"""
    return jsonify({
        'status': 'ok',
        'service': 'resim-indir-api',
        'timestamp': datetime.now().isoformat(),
        'images_count': len(ResimIndirManager.list_downloaded_images())
    })


@app.route('/config', methods=['GET'])
def config():
    """Ayarları getir"""
    return jsonify({
        'resimler_dir': RESIMLER_DIR,
        'uploads_dir': UPLOADS_DIR,
        'max_images_per_model': 3
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5002)), debug=False)
