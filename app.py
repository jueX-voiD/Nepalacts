

import io
import base64
import zipfile
from pathlib import Path

from flask import Flask, request, jsonify, Response, send_file

import generate as g

app = Flask(__name__)
BASE_DIR = Path(__file__).parent


# ── HTML page ────────────────────────────────────────────────────────────────
PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Nepal Acts — Image Generator</title>
  <link rel="icon" type="image/x-icon" href="/favicon.ico">
  <link rel="icon" type="image/png" href="/favicon.png">
  <link rel="apple-touch-icon" href="/favicon.png">
  <style>
    :root { --accent:#EB4F57; --bg:#0f1316; --card:#181d21; --muted:#8a949c; }
    * { box-sizing:border-box; }
    body {
      margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
      background:var(--bg); color:#fff;
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    }
    .card {
      width:100%; max-width:560px; margin:24px; padding:36px;
      background:var(--card); border-radius:18px; box-shadow:0 20px 60px rgba(0,0,0,.4);
    }
    h1 { margin:0 0 6px; font-size:24px; }
    p.sub { margin:0 0 28px; color:var(--muted); font-size:14px; }
    label { display:block; font-size:13px; color:var(--muted); margin-bottom:8px; }
    input[type=text] {
      width:100%; padding:14px 16px; font-size:15px; border-radius:10px;
      border:1px solid #2a3138; background:#0f1316; color:#fff; outline:none;
    }
    input[type=text]:focus { border-color:var(--accent); }
    button {
      margin-top:18px; width:100%; padding:14px; font-size:16px; font-weight:600;
      border:0; border-radius:10px; background:var(--accent); color:#fff; cursor:pointer;
    }
    button:disabled { opacity:.5; cursor:not-allowed; }
    .status { margin-top:18px; font-size:14px; min-height:20px; }
    .status.err { color:#ff8a8a; }
    .preview { margin-top:24px; display:none; gap:14px; flex-wrap:wrap; }
    .preview.show { display:flex; }
    .preview figure { flex:1 1 40%; min-width:150px; margin:0; text-align:center; }
    .preview img { width:100%; border-radius:10px; border:1px solid #2a3138; }
    .preview figcaption { font-size:12px; color:var(--muted); margin-top:8px; }
    .dl { margin-top:6px; display:inline-block; font-size:13px; color:var(--accent); text-decoration:none; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Image Generator</h1>
    <p class="sub">Paste a Nepal Acts post URL to generate the English &amp; Nepali images.</p>

    <label for="url">Post URL</label>
    <input id="url" type="text" placeholder="https://nepalacts.com/voices/..."
           value="">

    <button id="go">Generate &amp; Download</button>
    <div id="status" class="status"></div>

    <div id="preview" class="preview"></div>
  </div>

<script>
const btn = document.getElementById('go');
const urlInput = document.getElementById('url');
const status = document.getElementById('status');
const preview = document.getElementById('preview');

function triggerDownload(blob, filename) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

btn.addEventListener('click', async () => {
  const url = urlInput.value.trim();
  if (!url) { status.textContent = 'Please enter a URL.'; status.className='status err'; return; }

  btn.disabled = true;
  status.className = 'status';
  status.textContent = 'Fetching & generating…';
  preview.className = 'preview';
  preview.innerHTML = '';

  try {
    const resp = await fetch('/generate?url=' + encodeURIComponent(url));
    if (!resp.ok) {
      const e = await resp.json().catch(() => ({error:'Request failed'}));
      throw new Error(e.error || 'Request failed');
    }
    const data = await resp.json();

    // Download a single ZIP containing both images
    const zipBytes = Uint8Array.from(atob(data.zip), c => c.charCodeAt(0));
    const zipBlob = new Blob([zipBytes], {type:'application/zip'});
    triggerDownload(zipBlob, data.zipname);

    // Show previews of each image
    for (const img of data.images) {
      const fig = document.createElement('figure');
      const im = document.createElement('img');
      im.src = 'data:image/png;base64,' + img.data;
      const cap = document.createElement('figcaption');
      cap.textContent = (img.variant ? img.variant + ' · ' : '') + img.lang;
      fig.appendChild(im); fig.appendChild(cap);
      preview.appendChild(fig);
    }
    preview.className = 'preview show';
    status.textContent = 'Done — downloaded ' + data.zipname;
  } catch (err) {
    status.className = 'status err';
    status.textContent = 'Error: ' + err.message;
  } finally {
    btn.disabled = false;
  }
});
</script>
</body>
</html>
"""


def image_to_b64(img):
    buf = io.BytesIO()
    img.save(buf, "PNG", dpi=(72, 72))
    return base64.b64encode(buf.getvalue()).decode("ascii")


@app.route("/")
def index():
    return Response(PAGE, mimetype="text/html")


@app.route("/favicon.ico")
def favicon_ico():
    return send_file(BASE_DIR / "favicon.ico", mimetype="image/x-icon")


@app.route("/favicon.png")
def favicon_png():
    return send_file(BASE_DIR / "favicon.png", mimetype="image/png")


@app.route("/generate")
def generate_endpoint():
    url = (request.args.get("url") or "").strip()
    if not url:
        return jsonify(error="No URL provided"), 400

    try:
        data = g.fetch_article(url)
    except Exception as e:
        return jsonify(error=f"Could not fetch article: {e}"), 502

    en, np_text, img_url = data["en_headline"], data["np_headline"], data["image_url"]
    en_tag, np_tag = data["en_tag"], data["np_tag"]
    if not img_url:
        return jsonify(error="No featured image found for this post."), 404

    try:
        photo = g.fetch_photo(img_url)
    except Exception as e:
        return jsonify(error=f"Could not download photo: {e}"), 502

    offset = (0, 0)
    images = []

    # Generate every variant (Post, Stories) for both languages.
    for variant, layout in g.LAYOUTS.items():
        if en:
            img = g.generate_image(photo, en, layout, "en", "#ffffff", offset,
                                   tag_text=en_tag)
            images.append({
                "lang":     "English",
                "variant":  variant,
                "filename": f"{variant}/{g.safe_filename(en)}.png",
                "data":     image_to_b64(img),
            })
        if np_text:
            img = g.generate_image(photo, np_text, layout, "ne", "#ffffff", offset,
                                   tag_text=np_tag)
            images.append({
                "lang":     "Nepali",
                "variant":  variant,
                "filename": f"{variant}/{g.safe_filename(np_text)}.png",
                "data":     image_to_b64(img),
            })

    if not images:
        return jsonify(error="No headlines found for this post."), 404

    # Bundle both PNGs into a single ZIP (in memory)
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for img in images:
            zf.writestr(img["filename"], base64.b64decode(img["data"]))
    zip_b64 = base64.b64encode(zip_buf.getvalue()).decode("ascii")

    # Name the zip after the English headline (fallback to Nepali)
    base = g.safe_filename(en or np_text)

    return jsonify(images=images, zip=zip_b64, zipname=base + ".zip")


if __name__ == "__main__":
    import os
    # Use $PORT if set (hosting platforms), else 5050 for local dev.
    PORT = int(os.environ.get("PORT", 5050))
    HOST = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    print("\n  Nepal Acts Image Generator")
    print(f"  Open → http://127.0.0.1:{PORT}\n")
    app.run(host=HOST, port=PORT, debug=False)
