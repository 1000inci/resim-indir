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


@app.route('/', methods=['GET'])
def dashboard():
    """Resim İndir Dashboard"""
    return '''
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Resim İndir</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f7fa; color: #333; }
            .container { max-width: 900px; margin: 0 auto; padding: 20px; }
            .header { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 40px 20px; border-radius: 10px; margin-bottom: 30px; }
            .header h1 { font-size: 2em; margin-bottom: 10px; }
            .header p { opacity: 0.9; }
            .card { background: white; border-radius: 10px; padding: 25px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
            .card h2 { color: #f5576c; margin-bottom: 15px; font-size: 1.3em; }
            .form-group { margin-bottom: 15px; }
            label { display: block; margin-bottom: 5px; font-weight: 500; }
            textarea { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 1em; font-family: monospace; }
            textarea:focus { outline: none; border-color: #f5576c; box-shadow: 0 0 0 3px rgba(245, 87, 108, 0.1); }
            button { background: #f5576c; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-weight: 500; transition: background 0.3s; }
            button:hover { background: #d63a51; }
            button.secondary { background: #6b7280; }
            button.secondary:hover { background: #4b5563; }
            .result { background: #f9f9f9; padding: 15px; border-radius: 5px; margin-top: 15px; border-left: 4px solid #f5576c; }
            .success { border-left-color: #10b981; }
            .error { border-left-color: #ef4444; }
            .loading { display: none; color: #f5576c; margin-top: 10px; }
            .stats { display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }
            .stat { flex: 1; min-width: 120px; background: white; border-radius: 10px; padding: 20px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
            .stat .num { font-size: 2em; font-weight: bold; color: #f5576c; }
            .stat .lbl { color: #666; font-size: 0.9em; margin-top: 5px; }
            .img-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 10px; margin-top: 15px; }
            .img-item { border: 1px solid #eee; border-radius: 5px; padding: 8px; font-size: 0.8em; word-break: break-all; }
            pre { white-space: pre-wrap; word-break: break-all; font-size: 0.85em; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🖼️ Resim İndir</h1>
                <p>Model listesinden toplu ürün görseli indir</p>
            </div>

            <div class="stats">
                <div class="stat"><div class="num" id="stat-images">-</div><div class="lbl">İndirilen Görsel</div></div>
                <div class="stat"><div class="num" id="stat-failed">-</div><div class="lbl">Başarısız Model</div></div>
            </div>

            <div class="card">
                <h2>⬇️ İndirme Başlat</h2>
                <div class="form-group">
                    <label for="models">Model Listesi (satır satır):</label>
                    <textarea id="models" placeholder="ABC-123&#10;XYZ-456&#10;Model adı" rows="6"></textarea>
                </div>
                <button onclick="startDownload()">İndirmeyi Başlat</button>
                <button class="secondary" onclick="refreshAll()">🔄 Yenile</button>
                <div class="loading" id="dl-loading">İşleniyor...</div>
                <div id="dl-result"></div>
            </div>

            <div class="card">
                <h2>📊 İndirme Durumu</h2>
                <div id="job-status">Aktif iş yok. İndirme başlatınca burada görünür.</div>
            </div>

            <div class="card">
                <h2>🖼️ İndirilen Görseller</h2>
                <div id="images-list">Yükleniyor...</div>
            </div>

            <div class="card">
                <h2>⚠️ Başarısız Modeller</h2>
                <div id="failed-list">Yükleniyor...</div>
            </div>
        </div>

        <script>
            let currentJob = null;
            let pollTimer = null;

            async function startDownload() {
                const text = document.getElementById('models').value.trim();
                const models = text.split('\\n').map(m => m.trim()).filter(m => m);
                if (!models.length) { alert('En az bir model girin'); return; }
                document.getElementById('dl-loading').style.display = 'block';
                document.getElementById('dl-result').innerHTML = '';
                try {
                    const res = await fetch('/api/download/start', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({models}) });
                    const data = await res.json();
                    document.getElementById('dl-loading').style.display = 'none';
                    document.getElementById('dl-result').innerHTML = `<div class="result ${res.ok ? 'success' : 'error'}"><pre>${JSON.stringify(data, null, 2)}</pre></div>`;
                    if (data.job_id) { currentJob = data.job_id; pollStatus(); }
                } catch (e) {
                    document.getElementById('dl-loading').style.display = 'none';
                    document.getElementById('dl-result').innerHTML = `<div class="result error">${e.message}</div>`;
                }
            }

            async function pollStatus() {
                if (!currentJob) return;
                try {
                    const res = await fetch('/api/download/status/' + currentJob);
                    const data = await res.json();
                    document.getElementById('job-status').innerHTML = `<div class="result"><pre>${JSON.stringify(data, null, 2)}</pre></div>`;
                    if (data.status === 'running') {
                        clearTimeout(pollTimer);
                        pollTimer = setTimeout(pollStatus, 3000);
                    } else {
                        refreshAll();
                    }
                } catch (e) { /* sessizce gec */ }
            }

            async function loadImages() {
                try {
                    const res = await fetch('/api/images');
                    const data = await res.json();
                    document.getElementById('stat-images').textContent = data.total || 0;
                    if (data.total > 0) {
                        document.getElementById('images-list').innerHTML = '<div class="img-list">' +
                            data.images.map(img => `<div class="img-item">📄 ${img.filename}<br><small>${(img.size/1024).toFixed(1)} KB</small></div>`).join('') + '</div>';
                    } else {
                        document.getElementById('images-list').innerHTML = 'Henüz görsel indirilmedi.';
                    }
                } catch (e) { document.getElementById('images-list').innerHTML = 'Yüklenemedi.'; }
            }

            async function loadFailed() {
                try {
                    const res = await fetch('/api/failed-models');
                    const data = await res.json();
                    document.getElementById('stat-failed').textContent = data.total || 0;
                    if (data.total > 0) {
                        document.getElementById('failed-list').innerHTML = '<pre>' + data.models.join('\\n') + '</pre>';
                    } else {
                        document.getElementById('failed-list').innerHTML = 'Başarısız model yok. 👍';
                    }
                } catch (e) { document.getElementById('failed-list').innerHTML = 'Yüklenemedi.'; }
            }

            function refreshAll() { loadImages(); loadFailed(); }
            refreshAll();
        </script>
    </body>
    </html>
    '''


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
