"""
Resim-İndir API Wrapper
Web entegrasyonu için API endpoints
"""

from flask import Flask, jsonify, request, send_file, Response
from datetime import datetime
import os
import sys
import io
import json
import zipfile
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
                    [sys.executable, os.path.join(os.path.dirname(__file__), 'resim.py'), job_file],
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


INDEX_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Resim İndir — 1000inci.com</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:'Segoe UI',system-ui,sans-serif; background:linear-gradient(135deg,#1f2937,#111827); color:#e5e7eb; min-height:100vh; padding:28px 18px; }
  .wrap { max-width:1100px; margin:0 auto; }
  h1 { font-size:1.8rem; margin-bottom:4px; display:flex; align-items:center; gap:10px; }
  .sub { color:#9ca3af; font-size:0.9rem; margin-bottom:22px; }
  .card { background:rgba(31,41,55,0.7); border:1px solid #374151; border-radius:14px; padding:20px; margin-bottom:20px; }
  label { font-size:0.85rem; color:#9ca3af; display:block; margin-bottom:8px; }
  textarea { width:100%; min-height:160px; background:#0b1220; color:#e5e7eb; border:1px solid #374151; border-radius:10px; padding:12px; font-family:monospace; font-size:0.9rem; resize:vertical; outline:none; }
  textarea:focus { border-color:#3b82f6; }
  .row { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-top:14px; }
  button { font-family:inherit; font-size:0.9rem; font-weight:600; padding:11px 20px; border-radius:10px; border:1px solid #374151; background:#1f2937; color:#e5e7eb; cursor:pointer; transition:.15s; }
  button:hover { border-color:#3b82f6; }
  button.primary { background:linear-gradient(135deg,#2563eb,#1d4ed8); border-color:#3b82f6; color:#fff; }
  button:disabled { opacity:.5; cursor:not-allowed; }
  .status { margin-top:14px; font-size:0.9rem; padding:12px 14px; border-radius:10px; display:none; }
  .status.show { display:block; }
  .status.run { background:rgba(37,99,235,0.15); border:1px solid #2563eb; color:#93c5fd; }
  .status.ok { background:rgba(34,197,94,0.15); border:1px solid #22c55e; color:#86efac; }
  .status.err { background:rgba(239,68,68,0.15); border:1px solid #ef4444; color:#fca5a5; }
  .spin { display:inline-block; width:14px; height:14px; border:2px solid #93c5fd; border-top-color:transparent; border-radius:50%; animation:sp 0.8s linear infinite; vertical-align:middle; margin-right:8px; }
  @keyframes sp { to { transform:rotate(360deg); } }
  .gallery { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:14px; }
  .thumb { background:#0b1220; border:1px solid #374151; border-radius:10px; overflow:hidden; }
  .thumb a { display:block; }
  .thumb img { width:100%; height:130px; object-fit:cover; display:block; background:#111; }
  .thumb .cap { font-size:0.7rem; color:#9ca3af; padding:6px 8px; word-break:break-all; }
  .head { display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; }
  .muted { color:#9ca3af; font-size:0.85rem; }
  .failed { list-style:none; }
  .failed li { font-family:monospace; font-size:0.85rem; color:#fca5a5; padding:3px 0; border-bottom:1px solid #374151; }
  .empty { color:#6b7280; font-style:italic; padding:20px; text-align:center; }
</style>
</head>
<body>
<div class="wrap">
  <h1>🖼️ Resim İndir</h1>
  <div class="sub">Model listesini gir, her model için otomatik görsel indirilir (model başına en çok 3 adet). Görselleri <strong>ZIP olarak bilgisayarına indirip sunucudan silebilirsin</strong>.</div>

  <div class="card">
    <label for="models">Arama listesi — <strong>her satır ayrı bir aramadır</strong> (model kodu yaz; tırnak gerekmez; # ile başlayan satır yorumdur)</label>
    <textarea id="models" placeholder="IPC-HFW1249S-S-IL&#10;B1A21-U-IL&#10;..."></textarea>
    <div class="row">
      <button class="primary" id="startBtn">🔍 Aramayı Başlat</button>
      <span class="muted" id="count"></span>
    </div>
    <div class="status" id="status"></div>
  </div>

  <div class="card">
    <div class="head">
      <strong>📁 İndirilen Görseller (<span id="imgCount">0</span>)</strong>
      <div class="row" style="margin:0;">
        <button class="primary" id="zipBtn">📦 Bilgisayarıma indir (ZIP)</button>
        <button id="clearBtn">🗑️ Sunucudan sil</button>
      </div>
    </div>
    <div class="gallery" id="gallery"></div>
    <div class="empty" id="galleryEmpty">Henüz görsel yok.</div>
  </div>

  <div class="card" id="failedCard" style="display:none;">
    <div class="head"><strong>⚠️ Başarısız Modeller (<span id="failCount">0</span>)</strong></div>
    <ul class="failed" id="failed"></ul>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
let pollTimer = null;

function parseModels() {
  return $('models').value.split(/\\r?\\n/).map(s => s.trim())
    .filter(s => s && !s.startsWith('#'));
}
$('models').addEventListener('input', () => {
  const n = parseModels().length;
  $('count').textContent = n ? n + ' model' : '';
});

function showStatus(cls, html) {
  const el = $('status');
  el.className = 'status show ' + cls;
  el.innerHTML = html;
}

async function start() {
  const models = parseModels();
  if (!models.length) { showStatus('err', '⚠️ En az bir arama (model) girin.'); return; }
  $('startBtn').disabled = true;
  showStatus('run', '<span class="spin"></span> Arama başlatılıyor... (önceki sonuçlar temizleniyor)');
  try {
    const r = await fetch('api/download/start', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ models })
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Başlatılamadı');
    poll(d.job_id, models.length);
  } catch(e) {
    showStatus('err', '❌ ' + e.message); $('startBtn').disabled = false;
  }
}

function poll(jobId, total) {
  const t0 = Date.now();
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const r = await fetch('api/download/status/' + jobId);
      const d = await r.json();
      const sec = Math.round((Date.now()-t0)/1000);
      if (d.status === 'running') {
        showStatus('run', '<span class="spin"></span> ' + total + ' arama yapılıyor, görseller indiriliyor... (' + sec + ' sn)');
      } else {
        clearInterval(pollTimer);
        $('startBtn').disabled = false;
        if (d.status === 'completed') showStatus('ok', '✓ Tamamlandı (' + sec + ' sn). Galeri güncellendi.');
        else showStatus('err', '❌ Hata: ' + (d.error || 'indirme başarısız'));
        loadGallery(); loadFailed();
      }
    } catch(e) { /* gecici hata, devam */ }
  }, 3000);
}

async function loadGallery() {
  try {
    const r = await fetch('api/images');
    const d = await r.json();
    $('imgCount').textContent = d.total;
    const g = $('gallery');
    if (!d.total) { g.innerHTML=''; $('galleryEmpty').style.display='block'; return; }
    $('galleryEmpty').style.display='none';
    g.innerHTML = d.images.map(im =>
      '<div class="thumb"><a href="image/'+encodeURIComponent(im.filename)+'" target="_blank">'+
      '<img loading="lazy" src="image/'+encodeURIComponent(im.filename)+'"></a>'+
      '<div class="cap">'+im.filename+'</div></div>'
    ).join('');
  } catch(e) {}
}

async function loadFailed() {
  try {
    const r = await fetch('api/failed-models');
    const d = await r.json();
    $('failCount').textContent = d.total;
    $('failedCard').style.display = d.total ? 'block' : 'none';
    $('failed').innerHTML = d.models.map(m => '<li>'+m+'</li>').join('');
  } catch(e) {}
}

$('zipBtn').addEventListener('click', () => {
  if (!Number($('imgCount').textContent)) { showStatus('err', '⚠️ İndirilecek görsel yok.'); return; }
  // ZIP'i bilgisayara indir + sunucudan sil
  window.location.href = 'api/images/zip?clear=1';
  setTimeout(() => { loadGallery(); loadFailed(); showStatus('ok', '📦 ZIP indirildi, görseller sunucudan temizlendi.'); }, 3000);
});
$('clearBtn').addEventListener('click', async () => {
  if (!Number($('imgCount').textContent)) { showStatus('err', '⚠️ Silinecek görsel yok.'); return; }
  if (!confirm('Sunucudaki tüm görseller silinsin mi? (Bilgisayarına inmez)')) return;
  await fetch('api/images/clear', { method:'POST' });
  loadGallery(); loadFailed(); showStatus('ok', '🗑️ Sunucudan silindi.');
});
$('startBtn').addEventListener('click', start);
loadGallery(); loadFailed();
</script>
</body>
</html>"""


@app.route('/', methods=['GET'])
def index():
    return Response(INDEX_HTML, mimetype='text/html; charset=utf-8')


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

    # Her yeni arama öncesi sunucudaki önceki görselleri temizle (birikme olmasın)
    _clear_images()

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


IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.webp')


def _image_files():
    if not os.path.exists(RESIMLER_DIR):
        return []
    return [f for f in os.listdir(RESIMLER_DIR) if f.lower().endswith(IMAGE_EXTS)]


def _clear_images():
    removed = 0
    if not os.path.exists(RESIMLER_DIR):
        return 0
    for f in os.listdir(RESIMLER_DIR):
        if f.lower().endswith(IMAGE_EXTS) or f == 'failed_models.txt':
            try:
                os.remove(os.path.join(RESIMLER_DIR, f))
                if f.lower().endswith(IMAGE_EXTS):
                    removed += 1
            except OSError:
                pass
    return removed


@app.route('/api/images/zip', methods=['GET'])
def api_images_zip():
    """Tüm görselleri ZIP olarak indir. ?clear=1 ile indirme sonrası sunucudan siler."""
    files = _image_files()
    if not files:
        return jsonify({'error': 'İndirilecek görsel yok'}), 404
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(os.path.join(RESIMLER_DIR, f), arcname=f)
    buf.seek(0)
    # ZIP bellekte hazır; istenmişse dosyaları sunucudan sil
    if request.args.get('clear') == '1':
        _clear_images()
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name=f'resimler_{ts}.zip')


@app.route('/api/images/clear', methods=['POST'])
def api_images_clear():
    """Sunucudaki tüm görselleri (ve failed_models.txt) sil."""
    n = _clear_images()
    return jsonify({'message': 'Temizlendi', 'removed': n})


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
