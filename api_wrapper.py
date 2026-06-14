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
    def start_download(job_id, models, category="", max_per_model=3):
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
            'category': category,
            'max_per_model': max_per_model,
            'progress': 0,
            'completed': 0,
            'failed': 0,
            'log_file': job_file
        }

        # Arka planda indirmeyi çalıştır
        def run_download():
            try:
                # Python script'ini çalıştır: resim.py <dosya> [kategori] [max_per_model]
                # Kategori bos olsa bile, max_per_model'i konum olarak gecirebilmek icin
                # kategori arguman yerine bos string gonderiyoruz.
                cmd = [sys.executable,
                       os.path.join(os.path.dirname(__file__), 'resim.py'),
                       job_file, category or '', str(max_per_model)]
                result = subprocess.run(
                    cmd,
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
        """İndirilen görselleri listele (kategori alt klasörleri dahil)"""
        if not os.path.exists(RESIMLER_DIR):
            return []

        images = []
        for root, dirs, files in os.walk(RESIMLER_DIR):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                    file_path = os.path.join(root, file)
                    # RESIMLER_DIR'e gore goreli yol (URL'de / kullanilir)
                    rel_path = os.path.relpath(file_path, RESIMLER_DIR).replace(os.sep, '/')
                    images.append({
                        'filename': file,
                        'path': rel_path,
                        'size': os.path.getsize(file_path),
                        'created': datetime.fromtimestamp(os.path.getctime(file_path)).isoformat()
                    })

        return sorted(images, key=lambda x: x['created'], reverse=True)

    @staticmethod
    def get_failed_models():
        """Başarısız modelleri getir (tüm kategori klasörlerinden)"""
        failed = []
        if not os.path.exists(RESIMLER_DIR):
            return failed
        for root, dirs, files in os.walk(RESIMLER_DIR):
            if 'failed_models.txt' in files:
                with open(os.path.join(root, 'failed_models.txt'), 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            failed.append(line)
        return failed


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
  .opts { display:flex; gap:16px; margin-top:14px; flex-wrap:wrap; }
  .opt { flex:1; min-width:200px; }
  .opt-num { flex:0 0 150px; min-width:120px; }
  .opt input { width:100%; background:#0b1220; color:#e5e7eb; border:1px solid #374151; border-radius:10px; padding:10px 12px; font-family:inherit; font-size:0.9rem; outline:none; }
  .opt input:focus { border-color:#3b82f6; }
  .hint { display:block; font-size:0.72rem; color:#6b7280; margin-top:5px; }
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
  <div class="sub">Model listesini gir, kategori ve resim sayısını seç; her arama için otomatik görsel indirilir. Görselleri <strong>ZIP olarak bilgisayarına indirip sunucudan silebilirsin</strong>.</div>

  <div class="card">
    <label for="models">Arama listesi — <strong>her satır ayrı bir aramadır</strong> (model kodu yaz; tırnak gerekmez; # ile başlayan satır yorumdur)</label>
    <textarea id="models" placeholder="IPC-HFW1249S-S-IL&#10;B1A21-U-IL&#10;..."></textarea>
    <div class="opts">
      <div class="opt">
        <label for="category">Kategori (isteğe bağlı)</label>
        <input type="text" id="category" placeholder="örn: kamera, araba, telefon">
        <span class="hint">Her aramaya eklenir. Boş = jenerik arama.</span>
      </div>
      <div class="opt opt-num">
        <label for="maxPer">Arama başına resim</label>
        <input type="number" id="maxPer" value="3" min="1" max="20">
        <span class="hint">1-20 arası</span>
      </div>
    </div>
    <div class="row">
      <button class="primary" id="startBtn" title="Önceki görselleri siler, sadece bu aramanın sonuçlarını gösterir">🔍 Aramayı Başlat</button>
      <button id="appendBtn" title="Önceki görselleri korur, bu aramanın YENİ sonuçlarını üzerine ekler">➕ Aramaya Ekle</button>
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

function setBusy(b) { $('startBtn').disabled = b; $('appendBtn').disabled = b; }

async function start(append) {
  const models = parseModels();
  if (!models.length) { showStatus('err', '⚠️ En az bir arama (model) girin.'); return; }
  const category = $('category').value.trim();
  const max_per_model = parseInt($('maxPer').value) || 3;
  setBusy(true);
  showStatus('run', '<span class="spin"></span> ' +
    (append ? 'Aramaya ekleniyor... (önceki görseller korunuyor)'
            : 'Arama başlatılıyor... (önceki sonuçlar temizleniyor)'));
  try {
    const r = await fetch('api/download/start', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ models, category, max_per_model, append })
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Başlatılamadı');
    poll(d.job_id, models.length);
  } catch(e) {
    showStatus('err', '❌ ' + e.message); setBusy(false);
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
        setBusy(false);
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
    g.innerHTML = d.images.map(im => {
      // path alt klasör içerebilir (kategori/dosya.jpg); her parçayı ayrı encode et
      const src = 'image/' + (im.path || im.filename).split('/').map(encodeURIComponent).join('/');
      return '<div class="thumb"><a href="'+src+'" target="_blank">'+
        '<img loading="lazy" src="'+src+'"></a>'+
        '<div class="cap">'+im.filename+'</div></div>';
    }).join('');
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
$('startBtn').addEventListener('click', () => start(false));
$('appendBtn').addEventListener('click', () => start(true));
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
    category = (data.get('category') or '').strip()
    max_per_model = data.get('max_per_model', 3)
    # append=True ise önceki görseller KORUNUR (üzerine eklenir), aksi halde temizlenir
    append = bool(data.get('append', False))

    if not models:
        return jsonify({'error': 'Model listesi gerekli'}), 400

    # Max per model dogrula
    try:
        max_per_model = max(1, min(20, int(max_per_model)))
    except (ValueError, TypeError):
        max_per_model = 3

    # Yeni aramada (ekleme degilse) sunucudaki önceki görselleri temizle
    if not append:
        _clear_images()

    job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    ResimIndirManager.start_download(job_id, models, category, max_per_model)

    return jsonify({
        'job_id': job_id,
        'status': 'started',
        'models_count': len(models),
        'category': category,
        'max_per_model': max_per_model,
        'append': append
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
    """Tüm görselleri (kategori alt klasörleri dahil) RESIMLER_DIR'e göreli yol olarak döndür."""
    if not os.path.exists(RESIMLER_DIR):
        return []
    files = []
    for root, dirs, names in os.walk(RESIMLER_DIR):
        for f in names:
            if f.lower().endswith(IMAGE_EXTS):
                rel = os.path.relpath(os.path.join(root, f), RESIMLER_DIR)
                files.append(rel)
    return files


def _clear_images():
    """Tüm görselleri ve failed_models.txt'leri (alt klasörler dahil) sil, boş kategori klasörlerini temizle."""
    removed = 0
    if not os.path.exists(RESIMLER_DIR):
        return 0
    for root, dirs, names in os.walk(RESIMLER_DIR, topdown=False):
        for f in names:
            if f.lower().endswith(IMAGE_EXTS) or f == 'failed_models.txt':
                try:
                    os.remove(os.path.join(root, f))
                    if f.lower().endswith(IMAGE_EXTS):
                        removed += 1
                except OSError:
                    pass
        # Ana klasör değilse ve boşaldıysa kategori klasörünü kaldır
        if root != RESIMLER_DIR:
            try:
                os.rmdir(root)
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


@app.route('/image/<path:relpath>', methods=['GET'])
def get_image(relpath):
    """Görseli getir (kategori alt klasörleri dahil)"""
    # Güvenlik: yolun RESIMLER_DIR içinde kaldığından emin ol (path traversal koruması)
    base = os.path.realpath(RESIMLER_DIR)
    file_path = os.path.realpath(os.path.join(RESIMLER_DIR, relpath))

    if not file_path.startswith(base + os.sep):
        return jsonify({'error': 'Geçersiz yol'}), 400

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
