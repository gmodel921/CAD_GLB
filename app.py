# app.py
import os
import shutil
import uuid
import mimetypes
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# ensure correct MIME for GLB
mimetypes.add_type('model/gltf-binary', '.glb')

BASE = Path(__file__).parent.resolve()
UPLOAD_DIR = BASE / "uploads"
OUTPUT_DIR = BASE / "outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="STEP → GLB Converter (web)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

# Allowed extensions
# ALLOWED = {".step", ".stp"}
ALLOWED = {".step", ".stp", ".stl", ".obj", ".ply", ".off", ".gltf", ".glb", ".dae"}
MESH_EXTS = {".stl", ".obj", ".ply", ".off", ".gltf", ".glb", ".dae"}
CAD_EXTS  = {".step", ".stp"}


INDEX_HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <title>STEP → GLB Converter</title>
    <style>
      body{font-family:system-ui,Segoe UI,Roboto,Arial;padding:20px;max-width:900px}
      .drop{border:2px dashed #bbb;padding:30px;text-align:center;margin-bottom:10px}
      .btn{padding:8px 14px;background:#0b76ef;color:#fff;border-radius:6px;border:none;cursor:pointer}
    </style>
  </head>
  <body>
    <h1>Upload a STEP/STP file</h1>
    <div class="drop" id="drop">Drag & drop or choose file</div>
    <input id="file" type="file" />
    <div><button id="upload" class="btn">Upload & Convert</button></div>
    <p id="status"></p>
    <a id="viewerLink" href="#" target="_blank" style="display:none">Open viewer</a>

    <script>
      const drop = document.getElementById('drop');
      const fileInput = document.getElementById('file');
      const status = document.getElementById('status');
      const viewerLink = document.getElementById('viewerLink');
      let picked = null;

      drop.addEventListener('dragover', e => { e.preventDefault(); drop.style.borderColor='#444'; });
      drop.addEventListener('dragleave', e => { drop.style.borderColor='#bbb'; });
      drop.addEventListener('drop', e => {
        e.preventDefault();
        const f = e.dataTransfer.files[0];
        fileInput.files = e.dataTransfer.files;
        picked = f;
        drop.textContent = f.name;
      });

      fileInput.addEventListener('change', e => {
        picked = e.target.files[0];
        drop.textContent = picked ? picked.name : 'Drag & drop or choose file';
      });

      document.getElementById('upload').addEventListener('click', async () => {
        if (!picked) { alert('Choose a file'); return; }
        status.textContent = 'Uploading...';
        const fd = new FormData();
        fd.append('file', picked);
        try {
          const resp = await fetch('/upload', { method: 'POST', body: fd });
          if (!resp.ok) {
            const t = await resp.text();
            status.textContent = 'Error: ' + t;
            return;
          }
          const j = await resp.json();
          status.textContent = 'Converted: ' + j.message;
          viewerLink.href = j.viewer_url;
          viewerLink.style.display = 'inline-block';
          viewerLink.textContent = 'Open model viewer';
          window.open(j.viewer_url, '_blank');
        } catch (err) {
          status.textContent = 'Upload error: ' + err;
        }
      });
    </script>
  </body>
</html>
"""

VIEWER_TEMPLATE = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <title>Viewer - {fname}</title>
    <script type="module" src="https://unpkg.com/@google/model-viewer/dist/model-viewer.min.js"></script>
    <style>
      body{{margin:0;font-family:system-ui}}
      model-viewer{{width:100vw;height:100vh;display:block}}
      header{{padding:12px;background:#111;color:white;display:flex;align-items:center}}
    </style>
  </head>
  <body>
    <header>
      <div style="font-weight:600">{fname}</div>
      <div style="margin-left:auto"><a href="{download_url}" download style="background:#0b76ef;color:#fff;padding:6px 10px;border-radius:6px;text-decoration:none">Download GLB</a></div>
    </header>
    <model-viewer src="{model_url}" alt="{fname}" camera-controls auto-rotate exposure="1" shadow-intensity="1" ar ar-modes="webxr scene-viewer quick-look">
      <div>Your browser does not support &lt;model-viewer&gt;.</div>
    </model-viewer>
  </body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(INDEX_HTML)

def safe_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "._-").strip("_")

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    # Basic validation
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"Extension {suffix} not allowed. Only .step/.stp")

    uid = uuid.uuid4().hex
    in_path = UPLOAD_DIR / f"{uid}{suffix}"
    out_name = f"{uid}.glb"
    out_path = OUTPUT_DIR / out_name

    # save upload
    with in_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # convert using converter.py
    try:
        # import here so app can run without pythonocc if needed
        from converter import convert_step_to_glb
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Converter module import failed: {e}")

    success, message = convert_step_to_glb(in_path, out_path)
    if not success:
        raise HTTPException(status_code=500, detail=message)

    viewer_url = f"/view/{out_name}"
    download_url = f"/outputs/{out_name}"
    return JSONResponse({"viewer_url": viewer_url, "download_url": download_url, "message": message})

@app.get("/view/{file_name}", response_class=HTMLResponse)
async def view_model(file_name: str):
    p = OUTPUT_DIR / file_name
    if not p.exists():
        raise HTTPException(status_code=404, detail="File not found")
    model_url = f"/outputs/{file_name}"
    download_url = model_url
    html = VIEWER_TEMPLATE.format(fname=file_name, model_url=model_url, download_url=download_url)
    return HTMLResponse(html)

@app.get("/download/{file_name}")
async def download(file_name: str):
    p = OUTPUT_DIR / file_name
    if not p.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(p, media_type="model/gltf-binary", filename=file_name)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
