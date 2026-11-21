#!/usr/bin/env python3
"""
Web UI Localhost cho rea-video.
Khởi chạy: python3 web_server.py [--port 8765]
"""
from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUT_DIR = BASE_DIR / "out"
CASES_DIR = BASE_DIR / "docs" / "cases" / "videos"

UPLOAD_DIR.mkdir(exist_ok=True)
OUT_DIR.mkdir(exist_ok=True)

# Bộ nhớ quản lý các tiến trình (Jobs)
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def server_bind(self):
        # Tránh socket.getfqdn() vì trên macOS sẽ bị treo mDNS/DNS ngược
        import socketserver
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port


def get_samples() -> list[dict]:
    samples = []
    # Readme sample
    readme_mp4 = BASE_DIR / "Readme.mp4"
    if readme_mp4.is_file():
        samples.append({
            "name": "Readme.mp4 (Mẫu mặc định)",
            "path": str(readme_mp4),
            "size": f"{readme_mp4.stat().st_size / (1024 * 1024):.1f} MB",
            "url": "/file/Readme.mp4"
        })
    # Docs cases
    if CASES_DIR.is_dir():
        for f in sorted(CASES_DIR.glob("*.mp4")):
            samples.append({
                "name": f.name,
                "path": str(f),
                "size": f"{f.stat().st_size / (1024 * 1024):.1f} MB",
                "url": f"/docs/cases/videos/{f.name}"
            })
    return samples


def get_history() -> list[dict]:
    items = []
    if OUT_DIR.is_dir():
        for d in sorted(OUT_DIR.iterdir(), key=lambda p: p.stat().st_mtime if p.is_dir() else 0, reverse=True):
            if d.is_dir() and (d / "report.html").is_file():
                summary = {}
                bd_path = d / "breakdown.json"
                if bd_path.is_file():
                    try:
                        with open(bd_path, "r", encoding="utf-8") as f:
                            bd = json.load(f)
                            summary = bd.get("summary", {})
                    except Exception:
                        pass
                items.append({
                    "id": d.name,
                    "title": d.name,
                    "has_report": (d / "report.html").is_file(),
                    "has_breakdown": (d / "breakdown.json").is_file(),
                    "has_videomd": (d / "VIDEO.md").is_file(),
                    "stems": [s.name for s in (d / "stems").glob("*.wav")] if (d / "stems").is_dir() else [],
                    "summary": summary,
                    "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(d.stat().st_mtime))
                })
    return items


def run_worker(job_id: str, cmd: list[str], out_dir: Path):
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["status"] = "running"
        job["start_time"] = time.time()

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=str(BASE_DIR)
    )

    logs = []
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            logs.append(line)
            with JOBS_LOCK:
                job["logs"] = logs[-200:]  # Giữ lại 200 dòng mới nhất

    rc = process.poll()
    with JOBS_LOCK:
        job["end_time"] = time.time()
        job["returncode"] = rc
        if rc == 0:
            job["status"] = "completed"
            job["report_url"] = f"/out/{out_dir.name}/report.html"
            # Read breakdown.json if exists
            bd_path = out_dir / "breakdown.json"
            if bd_path.is_file():
                try:
                    with open(bd_path, "r", encoding="utf-8") as f:
                        job["result"] = json.load(f)
                except Exception:
                    pass
        else:
            job["status"] = "failed"


class ReaVideoHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.do_GET()

    def address_string(self):
        # Tránh getfqdn() khi log địa chỉ client
        return str(self.client_address[0])

    def log_message(self, format, *args):
        # Tắt bớt log rác trong terminal
        return

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        path = url.path

        if path == "/" or path == "/index.html":
            content = HTML_PAGE.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if path == "/api/samples":
            self.send_json(get_samples())
            return

        if path == "/api/history":
            self.send_json(get_history())
            return

        if path.startswith("/api/job/"):
            job_id = path[len("/api/job/"):]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
            if job:
                self.send_json(job)
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "Job not found")
            return

        # Phục vụ file tĩnh từ out/
        if path.startswith("/out/"):
            rel_path = path[len("/out/"):]
            file_path = OUT_DIR / rel_path
            self.serve_file(file_path)
            return

        # Phục vụ file mẫu từ docs/cases/videos/
        if path.startswith("/docs/cases/videos/"):
            rel_path = path[len("/docs/cases/videos/"):]
            file_path = CASES_DIR / rel_path
            self.serve_file(file_path)
            return

        # Phục vụ video Readme.mp4
        if path == "/file/Readme.mp4":
            self.serve_file(BASE_DIR / "Readme.mp4")
            return

        # Phục vụ file từ uploads/
        if path.startswith("/uploads/"):
            rel_path = path[len("/uploads/"):]
            file_path = UPLOAD_DIR / rel_path
            self.serve_file(file_path)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        path = url.path

        # Tải file lên (upload trực tiếp raw bytes với query ?name=...)
        if path == "/api/upload":
            query = urllib.parse.parse_qs(url.query)
            filename = query.get("name", [f"upload_{int(time.time())}.mp4"])[0]
            # Loại bỏ ký tự độc hại
            clean_name = Path(filename).name
            target_path = UPLOAD_DIR / clean_name

            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                self.send_error(HTTPStatus.BAD_REQUEST, "Zero content length")
                return

            try:
                with open(target_path, "wb") as f:
                    remaining = content_length
                    while remaining > 0:
                        chunk = self.rfile.read(min(remaining, 65536))
                        if not chunk:
                            break
                        f.write(chunk)
                        remaining -= len(chunk)

                self.send_json({
                    "status": "ok",
                    "filename": clean_name,
                    "path": str(target_path),
                    "size": f"{target_path.stat().st_size / (1024 * 1024):.1f} MB",
                    "url": f"/uploads/{clean_name}"
                })
            except Exception as e:
                self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))
            return

        # Khởi chạy phân tích (Run Job)
        if path == "/api/run":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)

            video_path = data.get("video_path")
            mode = data.get("mode", "decompose")
            lang = data.get("lang", "zh")
            no_stems = data.get("no_stems", False)
            no_ocr = data.get("no_ocr", False)

            if not video_path or not Path(video_path).is_file():
                self.send_error(HTTPStatus.BAD_REQUEST, "File video không tồn tại")
                return

            video_p = Path(video_path)
            stem_name = video_p.stem
            out_target = OUT_DIR / stem_name

            job_id = f"{stem_name}_{int(time.time())}"
            cmd = [sys.executable, "-m", "rea_video.cli"]

            if mode == "decompose":
                cmd.extend(["decompose", str(video_p), "-o", str(out_target), "--lang", lang])
                if no_stems:
                    cmd.append("--no-stems")
                if no_ocr:
                    cmd.append("--no-ocr")
            elif mode == "stems":
                cmd.extend(["stems", str(video_p), "-o", str(out_target)])
            elif mode == "probe":
                cmd.extend(["probe", str(video_p)])
            else:
                self.send_error(HTTPStatus.BAD_REQUEST, f"Chế độ {mode} không hợp lệ")
                return

            with JOBS_LOCK:
                JOBS[job_id] = {
                    "id": job_id,
                    "cmd": cmd,
                    "video": str(video_p),
                    "out_dir": str(out_target),
                    "status": "queued",
                    "logs": [],
                    "created_at": time.time(),
                }

            # Chạy worker nền
            t = threading.Thread(target=run_worker, args=(job_id, cmd, out_target), daemon=True)
            t.start()

            self.send_json({"job_id": job_id, "status": "queued"})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def send_json(self, data: any):
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def serve_file(self, file_path: Path):
        if not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "application/octet-stream"

        file_size = file_path.stat().st_size
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(file_size))
        self.end_headers()

        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                self.wfile.write(chunk)


HTML_PAGE = """<!DOCTYPE html>
<html lang="vi" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>rea-video Studio - Phân tích ngược video</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: { 50: '#f5f3ff', 500: '#8b5cf6', 600: '#7c3aed', 700: '#6d28d9' }
          }
        }
      }
    }
  </script>
  <style>
    pre::-webkit-scrollbar { width: 6px; height: 6px; }
    pre::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 3px; }
    iframe { border: none; }
  </style>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen flex flex-col font-sans">
  <!-- Navbar -->
  <header class="border-b border-gray-800 bg-gray-900/80 backdrop-blur sticky top-0 z-50 px-6 py-4 flex items-center justify-between">
    <div class="flex items-center space-x-3">
      <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-purple-600 to-indigo-500 flex items-center justify-center font-black text-xl shadow-lg shadow-purple-500/20">
        R
      </div>
      <div>
        <h1 class="text-lg font-bold bg-gradient-to-r from-purple-400 to-indigo-300 bg-clip-text text-transparent">rea-video Studio</h1>
        <p class="text-xs text-gray-400">Reverse-Engineering Video & Forensics</p>
      </div>
    </div>
    <div class="flex items-center space-x-4">
      <span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
        <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse mr-1.5"></span>
        Localhost 8765
      </span>
      <a href="https://github.com/JuneYaooo/rea-video" target="_blank" class="text-xs text-gray-400 hover:text-white transition">GitHub Repo ↗</a>
    </div>
  </header>

  <!-- Main Content -->
  <main class="flex-1 max-w-7xl w-full mx-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
    <!-- Left Column: Controls (5 cols) -->
    <div class="lg:col-span-5 space-y-6">
      
      <!-- Video Input Card -->
      <div class="bg-gray-900/60 border border-gray-800 rounded-2xl p-5 shadow-xl">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-400 mb-3 flex items-center justify-between">
          <span>1. Chọn video cần phân tích</span>
        </h2>

        <!-- Tabs: Upload or Sample -->
        <div class="flex border-b border-gray-800 mb-4">
          <button id="tab-upload-btn" onclick="switchInputTab('upload')" class="px-4 py-2 text-sm font-medium border-b-2 border-purple-500 text-purple-400">
            Tải lên từ máy
          </button>
          <button id="tab-sample-btn" onclick="switchInputTab('sample')" class="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">
            Video mẫu có sẵn
          </button>
        </div>

        <!-- Tab Content: Upload -->
        <div id="tab-upload-content" class="space-y-3">
          <div id="drop-zone" class="border-2 border-dashed border-gray-700 hover:border-purple-500/60 rounded-xl p-6 text-center cursor-pointer transition bg-gray-950/40">
            <svg class="w-10 h-10 mx-auto text-gray-500 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path>
            </svg>
            <p class="text-sm text-gray-300 font-medium">Kéo thả file video vào đây</p>
            <p class="text-xs text-gray-500 mt-1">hoặc nhấn để duyệt file (MP4, MOV)</p>
            <input type="file" id="file-input" accept="video/mp4,video/quicktime,video/*" class="hidden">
          </div>
          <div id="upload-progress" class="hidden">
            <div class="flex justify-between text-xs text-gray-400 mb-1">
              <span id="upload-filename">Đang tải lên...</span>
              <span id="upload-percent">0%</span>
            </div>
            <div class="w-full bg-gray-800 h-1.5 rounded-full overflow-hidden">
              <div id="upload-bar" class="bg-purple-500 h-full w-0 transition-all duration-200"></div>
            </div>
          </div>
        </div>

        <!-- Tab Content: Sample -->
        <div id="tab-sample-content" class="hidden space-y-2">
          <label class="text-xs text-gray-400">Chọn 1 video mẫu trong kho:</label>
          <select id="sample-select" onchange="onSampleSelect()" class="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-purple-500">
            <option value="">-- Đang tải danh sách mẫu... --</option>
          </select>
        </div>

        <!-- Selected Video Info Preview -->
        <div id="selected-video-box" class="hidden mt-4 p-3 bg-gray-800/40 rounded-xl border border-gray-700/60 flex items-center justify-between">
          <div class="truncate mr-2">
            <p id="selected-video-name" class="text-xs font-semibold text-purple-300 truncate">video.mp4</p>
            <p id="selected-video-size" class="text-[11px] text-gray-400">0 MB</p>
          </div>
          <button onclick="clearSelectedVideo()" class="text-gray-400 hover:text-red-400 text-xs px-2 py-1">Xóa</button>
        </div>
      </div>

      <!-- Analysis Options Card -->
      <div class="bg-gray-900/60 border border-gray-800 rounded-2xl p-5 shadow-xl space-y-4">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-400">2. Cấu hình phân tích</h2>

        <!-- Mode -->
        <div>
          <label class="block text-xs font-medium text-gray-400 mb-1.5">Chế độ hoạt động</label>
          <div class="grid grid-cols-3 gap-2">
            <button type="button" onclick="setMode('decompose')" id="mode-decompose" class="p-2.5 rounded-xl border border-purple-500 bg-purple-500/10 text-purple-300 text-xs font-medium text-center">
              🔬 Decompose<br><span class="text-[10px] text-gray-400 font-normal">Toàn diện</span>
            </button>
            <button type="button" onclick="setMode('stems')" id="mode-stems" class="p-2.5 rounded-xl border border-gray-800 bg-gray-950 text-gray-400 text-xs font-medium text-center hover:border-gray-700">
              🎵 Stems<br><span class="text-[10px] text-gray-500 font-normal">Tách âm</span>
            </button>
            <button type="button" onclick="setMode('probe')" id="mode-probe" class="p-2.5 rounded-xl border border-gray-800 bg-gray-950 text-gray-400 text-xs font-medium text-center hover:border-gray-700">
              🔍 Probe<br><span class="text-[10px] text-gray-500 font-normal">Metadata</span>
            </button>
          </div>
        </div>

        <!-- Options for Decompose -->
        <div id="decompose-options" class="space-y-3 pt-2 border-t border-gray-800/80">
          <div class="flex items-center justify-between">
            <label class="text-xs text-gray-300">Ngôn ngữ báo cáo</label>
            <select id="report-lang" class="bg-gray-950 border border-gray-700 rounded-lg px-2.5 py-1 text-xs text-gray-200">
              <option value="zh">Tiếng Trung (Gốc)</option>
              <option value="en" selected>Tiếng Anh (English)</option>
            </select>
          </div>
          <div class="flex items-center justify-between">
            <label class="text-xs text-gray-300" title="Bóc tách giọng nói và nhạc nền">Tách âm thanh (Stems)</label>
            <input type="checkbox" id="opt-stems" checked class="rounded border-gray-700 bg-gray-950 text-purple-500 focus:ring-0">
          </div>
          <div class="flex items-center justify-between">
            <label class="text-xs text-gray-300" title="Trích xuất phụ đề, chữ hiệu ứng">Nhận diện chữ (OCR)</label>
            <input type="checkbox" id="opt-ocr" checked class="rounded border-gray-700 bg-gray-950 text-purple-500 focus:ring-0">
          </div>
        </div>

        <!-- Run Button -->
        <button id="run-btn" onclick="startAnalysis()" disabled class="w-full py-3 px-4 rounded-xl font-semibold text-sm bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed transition shadow-lg shadow-purple-600/30 flex items-center justify-center space-x-2">
          <span>Bắt đầu phân tích</span>
        </button>
      </div>

      <!-- History List -->
      <div class="bg-gray-900/60 border border-gray-800 rounded-2xl p-5 shadow-xl">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-400 mb-3 flex items-center justify-between">
          <span>Lịch sử đã phân tích</span>
          <button onclick="loadHistory()" class="text-xs text-purple-400 hover:underline">Làm mới</button>
        </h2>
        <div id="history-list" class="space-y-2 max-h-56 overflow-y-auto pr-1">
          <p class="text-xs text-gray-500">Chưa có bản ghi nào.</p>
        </div>
      </div>

    </div>

    <!-- Right Column: Results & Logs (7 cols) -->
    <div class="lg:col-span-7 flex flex-col space-y-6">
      
      <!-- Status Card -->
      <div class="bg-gray-900/60 border border-gray-800 rounded-2xl p-5 shadow-xl">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-400">Tiến trình & Kết quả</h2>
          <span id="job-badge" class="hidden text-xs px-2 py-0.5 rounded-full font-medium"></span>
        </div>

        <!-- Summary Metric Cards (When completed) -->
        <div id="verdict-cards" class="hidden grid grid-cols-3 gap-3 mb-4">
          <div class="bg-gray-950 border border-gray-800 rounded-xl p-3 text-center">
            <p class="text-[11px] text-gray-400">Phán quyết</p>
            <p id="card-verdict" class="text-base font-bold text-purple-400 mt-0.5">—</p>
          </div>
          <div class="bg-gray-950 border border-gray-800 rounded-xl p-3 text-center">
            <p class="text-[11px] text-gray-400">Số cảnh (Shots)</p>
            <p id="card-shots" class="text-base font-bold text-gray-100 mt-0.5">—</p>
          </div>
          <div class="bg-gray-950 border border-gray-800 rounded-xl p-3 text-center">
            <p class="text-[11px] text-gray-400">Độ tin cậy</p>
            <p id="card-conf" class="text-base font-bold text-emerald-400 mt-0.5">—</p>
          </div>
        </div>

        <!-- Tabs for View -->
        <div class="flex border-b border-gray-800 mb-3">
          <button id="view-report-btn" onclick="switchViewTab('report')" class="px-4 py-2 text-xs font-semibold border-b-2 border-purple-500 text-purple-400">
            Báo cáo trực quan (Report.html)
          </button>
          <button id="view-logs-btn" onclick="switchViewTab('logs')" class="px-4 py-2 text-xs font-semibold border-b-2 border-transparent text-gray-400 hover:text-gray-200">
            Terminal Logs
          </button>
          <button id="view-files-btn" onclick="switchViewTab('files')" class="px-4 py-2 text-xs font-semibold border-b-2 border-transparent text-gray-400 hover:text-gray-200">
            Tài nguyên & Âm thanh
          </button>
        </div>

        <!-- View: Report iframe -->
        <div id="tab-view-report" class="bg-gray-950 rounded-xl border border-gray-800 overflow-hidden h-[620px] flex items-center justify-center">
          <div id="empty-report" class="text-center p-8 text-gray-500">
            <svg class="w-12 h-12 mx-auto mb-2 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
            </svg>
            <p class="text-xs">Chưa có báo cáo nào được chọn. Hãy chạy phân tích một video.</p>
          </div>
          <iframe id="report-frame" class="w-full h-full hidden" src="about:blank"></iframe>
        </div>

        <!-- View: Logs -->
        <div id="tab-view-logs" class="hidden">
          <pre id="log-box" class="bg-black/90 p-4 rounded-xl border border-gray-800 font-mono text-[11px] leading-relaxed text-emerald-400 h-[620px] overflow-y-auto whitespace-pre-wrap">Chưa có tiến trình đang chạy.</pre>
        </div>

        <!-- View: Files & Stems -->
        <div id="tab-view-files" class="hidden p-4 bg-gray-950 rounded-xl border border-gray-800 h-[620px] overflow-y-auto space-y-4">
          <div id="files-content" class="text-xs text-gray-400">
            Chưa có tài nguyên nào.
          </div>
        </div>

      </div>

    </div>
  </main>

  <script>
    let currentSelectedVideo = null;
    let currentMode = 'decompose';
    let currentJobId = null;
    let pollInterval = null;

    // Khởi động
    document.addEventListener('DOMContentLoaded', () => {
      loadSamples();
      loadHistory();
      setupDragDrop();
    });

    function switchInputTab(tab) {
      const isUpload = tab === 'upload';
      document.getElementById('tab-upload-btn').className = isUpload ? 'px-4 py-2 text-sm font-medium border-b-2 border-purple-500 text-purple-400' : 'px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200';
      document.getElementById('tab-sample-btn').className = !isUpload ? 'px-4 py-2 text-sm font-medium border-b-2 border-purple-500 text-purple-400' : 'px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200';
      document.getElementById('tab-upload-content').classList.toggle('hidden', !isUpload);
      document.getElementById('tab-sample-content').classList.toggle('hidden', isUpload);
    }

    function switchViewTab(tab) {
      ['report', 'logs', 'files'].forEach(t => {
        const btn = document.getElementById(`view-${t}-btn`);
        const content = document.getElementById(`tab-view-${t}`);
        if (t === tab) {
          btn.className = 'px-4 py-2 text-xs font-semibold border-b-2 border-purple-500 text-purple-400';
          content.classList.remove('hidden');
        } else {
          btn.className = 'px-4 py-2 text-xs font-semibold border-b-2 border-transparent text-gray-400 hover:text-gray-200';
          content.classList.add('hidden');
        }
      });
    }

    function setMode(mode) {
      currentMode = mode;
      ['decompose', 'stems', 'probe'].forEach(m => {
        const el = document.getElementById(`mode-${m}`);
        if (m === mode) {
          el.className = 'p-2.5 rounded-xl border border-purple-500 bg-purple-500/10 text-purple-300 text-xs font-medium text-center';
        } else {
          el.className = 'p-2.5 rounded-xl border border-gray-800 bg-gray-950 text-gray-400 text-xs font-medium text-center hover:border-gray-700';
        }
      });
      document.getElementById('decompose-options').classList.toggle('hidden', mode !== 'decompose');
    }

    async function loadSamples() {
      try {
        const res = await fetch('/api/samples');
        const data = await res.json();
        const sel = document.getElementById('sample-select');
        sel.innerHTML = '<option value="">-- Chọn 1 video trong kho mẫu --</option>';
        data.forEach((s, idx) => {
          const opt = document.createElement('option');
          opt.value = JSON.stringify(s);
          opt.textContent = `${s.name} (${s.size})`;
          sel.appendChild(opt);
        });
      } catch (err) {
        console.error("Lỗi tải samples:", err);
      }
    }

    function onSampleSelect() {
      const sel = document.getElementById('sample-select');
      if (!sel.value) return;
      const sample = JSON.parse(sel.value);
      setSelectedVideo(sample.name, sample.size, sample.path);
    }

    function setupDragDrop() {
      const dz = document.getElementById('drop-zone');
      const input = document.getElementById('file-input');

      dz.onclick = () => input.click();

      dz.ondragover = (e) => { e.preventDefault(); dz.classList.add('border-purple-500'); };
      dz.ondragleave = () => { dz.classList.remove('border-purple-500'); };
      dz.ondrop = (e) => {
        e.preventDefault();
        dz.classList.remove('border-purple-500');
        if (e.dataTransfer.files.length > 0) {
          uploadFile(e.dataTransfer.files[0]);
        }
      };

      input.onchange = () => {
        if (input.files.length > 0) {
          uploadFile(input.files[0]);
        }
      };
    }

    function uploadFile(file) {
      const progressBox = document.getElementById('upload-progress');
      const bar = document.getElementById('upload-bar');
      const percentText = document.getElementById('upload-percent');
      const nameText = document.getElementById('upload-filename');

      progressBox.classList.remove('hidden');
      nameText.textContent = `Đang tải: ${file.name}`;

      const xhr = new XMLHttpRequest();
      xhr.open('POST', `/api/upload?name=${encodeURIComponent(file.name)}`, true);

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const pct = Math.round((e.loaded / e.total) * 100);
          bar.style.width = pct + '%';
          percentText.textContent = pct + '%';
        }
      };

      xhr.onload = () => {
        if (xhr.status === 200) {
          const res = JSON.parse(xhr.responseText);
          setSelectedVideo(res.filename, res.size, res.path);
          progressBox.classList.add('hidden');
        } else {
          alert('Upload thất bại: ' + xhr.statusText);
          progressBox.classList.add('hidden');
        }
      };

      xhr.onerror = () => {
        alert('Lỗi kết nối khi tải file.');
        progressBox.classList.add('hidden');
      };

      xhr.send(file);
    }

    function setSelectedVideo(name, size, path) {
      currentSelectedVideo = { name, size, path };
      document.getElementById('selected-video-name').textContent = name;
      document.getElementById('selected-video-size').textContent = size;
      document.getElementById('selected-video-box').classList.remove('hidden');
      document.getElementById('run-btn').removeAttribute('disabled');
    }

    function clearSelectedVideo() {
      currentSelectedVideo = null;
      document.getElementById('selected-video-box').classList.add('hidden');
      document.getElementById('run-btn').setAttribute('disabled', 'true');
      document.getElementById('sample-select').value = '';
    }

    async function startAnalysis() {
      if (!currentSelectedVideo) return;

      const payload = {
        video_path: currentSelectedVideo.path,
        mode: currentMode,
        lang: document.getElementById('report-lang').value,
        no_stems: !document.getElementById('opt-stems').checked,
        no_ocr: !document.getElementById('opt-ocr').checked,
      };

      document.getElementById('run-btn').setAttribute('disabled', 'true');
      document.getElementById('run-btn').innerHTML = 'Đang khởi chạy...';

      // Switch to logs tab
      switchViewTab('logs');
      document.getElementById('log-box').textContent = "Đang kết nối và khởi tạo tiến trình...\\n";

      try {
        const res = await fetch('/api/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        currentJobId = data.job_id;
        pollJob();
      } catch (err) {
        alert("Khởi chạy thất bại: " + err);
        document.getElementById('run-btn').removeAttribute('disabled');
        document.getElementById('run-btn').innerHTML = 'Bắt đầu phân tích';
      }
    }

    function pollJob() {
      if (pollInterval) clearInterval(pollInterval);
      const badge = document.getElementById('job-badge');
      badge.classList.remove('hidden');
      badge.className = 'text-xs px-2 py-0.5 rounded-full font-medium bg-amber-500/20 text-amber-300 border border-amber-500/30';
      badge.textContent = 'Đang chạy (Running)...';

      pollInterval = setInterval(async () => {
        if (!currentJobId) return;
        try {
          const res = await fetch(`/api/job/${currentJobId}`);
          const job = await res.json();

          if (job.logs && job.logs.length > 0) {
            const logBox = document.getElementById('log-box');
            logBox.textContent = job.logs.join('');
            logBox.scrollTop = logBox.scrollHeight;
          }

          if (job.status === 'completed') {
            clearInterval(pollInterval);
            badge.className = 'text-xs px-2 py-0.5 rounded-full font-medium bg-emerald-500/20 text-emerald-300 border border-emerald-500/30';
            badge.textContent = 'Hoàn thành (Done)';
            document.getElementById('run-btn').removeAttribute('disabled');
            document.getElementById('run-btn').innerHTML = 'Bắt đầu phân tích';

            // Show report
            if (job.report_url) {
              openReport(job.report_url);
            }
            loadHistory();
          } else if (job.status === 'failed') {
            clearInterval(pollInterval);
            badge.className = 'text-xs px-2 py-0.5 rounded-full font-medium bg-rose-500/20 text-rose-300 border border-rose-500/30';
            badge.textContent = 'Thất bại (Failed)';
            document.getElementById('run-btn').removeAttribute('disabled');
            document.getElementById('run-btn').innerHTML = 'Bắt đầu phân tích';
          }
        } catch (e) {
          console.error("Lỗi polling:", e);
        }
      }, 1000);
    }

    async function loadHistory() {
      try {
        const res = await fetch('/api/history');
        const items = await res.json();
        const list = document.getElementById('history-list');
        if (items.length === 0) {
          list.innerHTML = '<p class="text-xs text-gray-500">Chưa có bản ghi nào.</p>';
          return;
        }
        list.innerHTML = '';
        items.forEach(it => {
          const el = document.createElement('div');
          el.className = 'p-2.5 rounded-xl bg-gray-950/60 border border-gray-800 hover:border-purple-500/40 cursor-pointer transition flex items-center justify-between';
          el.onclick = () => {
            openReport(`/out/${it.id}/report.html`);
            showFilesForHistory(it);
          };
          el.innerHTML = `
            <div class="truncate mr-2">
              <p class="text-xs font-semibold text-gray-200 truncate">${it.title}</p>
              <p class="text-[10px] text-gray-500">${it.time} • ${it.summary.verdict || 'Phân tích'}</p>
            </div>
            <span class="text-xs text-purple-400 font-medium">Xem ↗</span>
          `;
          list.appendChild(el);
        });
      } catch (err) {
        console.error("Lỗi tải lịch sử:", err);
      }
    }

    function openReport(url) {
      switchViewTab('report');
      document.getElementById('empty-report').classList.add('hidden');
      const frame = document.getElementById('report-frame');
      frame.classList.remove('hidden');
      frame.src = url;
    }

    function showFilesForHistory(it) {
      const container = document.getElementById('files-content');
      let html = `<div class="space-y-4">
        <div>
          <h3 class="font-semibold text-sm text-gray-200 mb-2">Các file xuất ra (${it.title})</h3>
          <ul class="space-y-1.5 text-xs">
            <li><a href="/out/${it.id}/report.html" target="_blank" class="text-purple-400 hover:underline">📄 report.html (Xem trang báo cáo riêng)</a></li>
            ${it.has_videomd ? `<li><a href="/out/${it.id}/VIDEO.md" target="_blank" class="text-indigo-400 hover:underline">📑 VIDEO.md (Tài liệu cho AI Agent)</a></li>` : ''}
            ${it.has_breakdown ? `<li><a href="/out/${it.id}/breakdown.json" target="_blank" class="text-emerald-400 hover:underline">📊 breakdown.json (Dữ liệu gốc JSON)</a></li>` : ''}
          </ul>
        </div>`;

      if (it.stems && it.stems.length > 0) {
        html += `<div>
          <h3 class="font-semibold text-sm text-gray-200 mb-2">Âm thanh đã tách (Stems)</h3>
          <div class="space-y-2">`;
        it.stems.forEach(stem => {
          html += `
            <div class="p-2.5 rounded-lg bg-gray-900 border border-gray-800">
              <p class="text-xs font-medium text-gray-300 mb-1">${stem}</p>
              <audio controls class="w-full h-8" src="/out/${it.id}/stems/${stem}"></audio>
            </div>
          `;
        });
        html += `</div></div>`;
      }
      html += `</div>`;
      container.innerHTML = html;
    }
  </script>
</body>
</html>
"""

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="rea-video Localhost Web UI")
    parser.add_argument("--port", type=int, default=8888, help="Port to listen on (default: 8888)")
    args = parser.parse_args()

    server_address = ("127.0.0.1", args.port)
    httpd = ThreadedHTTPServer(server_address, ReaVideoHandler)
    print(f"=====================================================")
    print(f"🚀 rea-video Web Studio đang chạy tại:")
    print(f"👉 http://localhost:{args.port}")
    print(f"=====================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nĐang tắt server...")
        httpd.server_close()
