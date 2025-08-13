import os
import shutil
import threading
import tempfile
import zipfile
import uuid
from flask import Flask, render_template, request, jsonify, send_file, abort
from dotenv import load_dotenv
from yt_dlp import YoutubeDL
from flask import jsonify

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "MyDownloader")
DEBUG = os.getenv("DEBUG", "True") == "True"

app = Flask(__name__, static_folder="static", template_folder="templates")

# Jobs store: job_id -> {status, progress(float 0-100), filepath, filename, type}
jobs = {}

def sanitize_filename(name: str) -> str:
    # simple sanitizer for filenames
    return "".join(c if c.isalnum() or c in " .-_()" else "_" for c in name).strip()

def download_worker(job_id, url, mode):
    """
    mode: 'mp3', 'mp4', 'playlist'
    """
    tmpdir = tempfile.mkdtemp(prefix="ydlp_")
    jobs[job_id] = {"status": "running", "progress": 0.0, "filepath": None, "filename": None, "type": mode}

    def progress_hook(d):
        # d is a dict from yt-dlp
        # possible keys: 'status','downloaded_bytes','total_bytes','filename','speed','eta'
        try:
            if d.get("status") == "downloading":
                if d.get("total_bytes") and d.get("downloaded_bytes") is not None and d["total_bytes"] > 0:
                    pct = (d["downloaded_bytes"] / d["total_bytes"]) * 100
                    jobs[job_id]["progress"] = round(pct, 2)
            elif d.get("status") == "finished":
                jobs[job_id]["progress"] = 100.0
        except Exception:
            pass

    try:
        if mode == "mp3":
            outtmpl = os.path.join(tmpdir, "%(title)s.%(ext)s")
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": outtmpl,
                "progress_hooks": [progress_hook],
                "postprocessors": [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
                ],
                # Use safe filenames
                "restrictfilenames": True,
                "noplaylist": True
            }
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # info may be a dict
                # find created file
            # locate mp3 file
            files = [f for f in os.listdir(tmpdir) if f.lower().endswith(".mp3")]
            if not files:
                raise RuntimeError("MP3 not found")
            filename = files[0]
            jobs[job_id]["filepath"] = os.path.join(tmpdir, filename)
            jobs[job_id]["filename"] = filename

        elif mode == "mp4":
            outtmpl = os.path.join(tmpdir, "%(title)s.%(ext)s")
            ydl_opts = {
                "format": "bestvideo+bestaudio/best",
                "outtmpl": outtmpl,
                "progress_hooks": [progress_hook],
                "merge_output_format": "mp4",
                "restrictfilenames": True,
                "noplaylist": True
            }
            with YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)
            files = [f for f in os.listdir(tmpdir) if f.lower().endswith(".mp4")]
            if not files:
                # sometimes extension differs, pick any file
                candidates = os.listdir(tmpdir)
                if not candidates:
                    raise RuntimeError("MP4 not found")
                filename = candidates[0]
            else:
                filename = files[0]
            jobs[job_id]["filepath"] = os.path.join(tmpdir, filename)
            jobs[job_id]["filename"] = filename

        elif mode == "playlist":
            # download entire playlist into tmpdir, then zip it
            outtmpl = os.path.join(tmpdir, "%(playlist_index)s - %(title)s.%(ext)s")
            ydl_opts = {
                "format": "bestvideo+bestaudio/best",
                "outtmpl": outtmpl,
                "progress_hooks": [progress_hook],
                "merge_output_format": "mp4",
                "restrictfilenames": True,
                "yes_playlist": True
            }
            with YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)
            # zip folder
            zip_name = f"playlist_{job_id}.zip"
            zip_path = os.path.join(tmpdir, zip_name)
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(tmpdir):
                    for f in files:
                        # skip the zip itself while creating
                        if f == zip_name:
                            continue
                        full = os.path.join(root, f)
                        # add file with relative name
                        zf.write(full, arcname=f)
            jobs[job_id]["filepath"] = zip_path
            jobs[job_id]["filename"] = zip_name
        else:
            raise ValueError("Unknown mode")
        jobs[job_id]["status"] = "finished"
        jobs[job_id]["progress"] = 100.0
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
    finally:
        # Do not delete tmpdir here; keep files until served.
        # We will keep tmpdir in jobs record to allow cleanup later.
        jobs[job_id]["tmpdir"] = tmpdir


@app.route("/")
def index():
    return render_template("index.html", app_name=APP_NAME)


@app.route("/start_download", methods=["POST"])
def start_download():
    data = request.get_json()
    url = data.get("url")
    mode = data.get("mode")  # 'mp3', 'mp4', 'playlist'
    if not url or mode not in {"mp3", "mp4", "playlist"}:
        return jsonify({"error": "invalid params"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "progress": 0.0}
    thread = threading.Thread(target=download_worker, args=(job_id, url, mode), daemon=True)
    thread.start()
    return jsonify({"job_id": job_id}), 202


@app.route("/progress/<job_id>")
def progress(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    # Return minimal info
    return jsonify({
        "status": job.get("status"),
        "progress": job.get("progress", 0.0),
        "filename": job.get("filename"),
        "error": job.get("error") if job.get("status") == "error" else None
    })


@app.route("/download_file/<job_id>")
def download_file(job_id):
    job = jobs.get(job_id)
    if not job:
        return abort(404)
    if job.get("status") != "finished":
        return jsonify({"error": "not ready"}), 400
    path = job.get("filepath")
    if not path or not os.path.exists(path):
        return abort(404)
    # send file as attachment (Save As will appear in browser)
    # Use download_name if Flask >=2.2 else attachment_filename
    fname = job.get("filename")
    try:
        return send_file(path, as_attachment=True, download_name=fname)
    finally:
        # Optionally cleanup after sending (comment out if you want manual retention)
        try:
            tmpdir = job.get("tmpdir")
            if tmpdir and os.path.exists(tmpdir):
                shutil.rmtree(tmpdir)
            jobs.pop(job_id, None)
        except Exception:
            pass

if __name__ == "__main__":
    app.run(debug=DEBUG, host="0.0.0.0", port=5000)



