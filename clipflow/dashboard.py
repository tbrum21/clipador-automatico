"""Painel local e supervisor de uma instancia do monitor."""
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

from . import config as C, db
from . import edit_settings
from . import recordings
from . import automatic
from .resource_guard import queue_snapshot

logs = deque(maxlen=500)
lock = threading.RLock()
process = None
channel = C.CHANNEL
channels = [C.CHANNEL] if C.CHANNEL else []
monitor_modes = {'peaks': True, 'recordings': True}
running = False
PAUSED_PATH = C.DATA / 'monitor-paused'
MODES_PATH = C.DATA / 'dashboard-modes.json'


def validate_modes(modes):
    if not isinstance(modes, dict) or set(modes) != {'peaks', 'recordings'} or any(type(modes[k]) is not bool for k in modes):
        raise ValueError('Selecione opcoes validas de monitoramento.')
    if not any(modes.values()):
        raise ValueError('Selecione pelo menos um tipo de corte.')
    return dict(modes)


def start(names, modes=None):
    global process, channel, channels, running, monitor_modes
    modes = validate_modes(modes if modes is not None else {'peaks': True, 'recordings': True})
    names = [names] if isinstance(names, str) else names
    if not isinstance(names, list) or not 1 <= len(names) <= 3 or not all(isinstance(x, str) for x in names):
        raise ValueError('Informe entre um e tres canais Twitch.')
    names = [re.sub(r'^https?://(?:www\.)?twitch\.tv/', '', name.strip().lower()).strip('/') for name in names]
    if any(not re.fullmatch(r'[a-z0-9_]{1,25}', name) for name in names) or len(set(names)) != len(names):
        raise ValueError('Informe canais Twitch validos e sem repeticao.')
    if modes['peaks'] and not (C.TELEGRAM_TOKEN and C.TELEGRAM_CHAT_ID):
        raise ValueError('Configure o Telegram para os cortes por pico.')
    with lock:
        if recordings.busy:
            raise ValueError('Aguarde a analise ou renderizacao da gravacao terminar.')
        if process and process.poll() is None:
            raise ValueError('Pare o monitoramento antes de trocar o canal.')
        env = os.environ.copy()
        env['TWITCH_CHANNEL'] = names[0]
        env['TWITCH_CHANNELS'] = ','.join(names)
        env['CLIPFLOW_PEAKS'] = '1' if modes['peaks'] else '0'
        env['CLIPFLOW_RECORDINGS'] = '1' if modes['recordings'] else '0'
        process = subprocess.Popen([sys.executable, '-u', '-m', 'clipflow.main'], env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                   errors='replace', start_new_session=True)
        channel, channels, running = names[0], names, True
        monitor_modes = modes
        (C.DATA / 'dashboard-channel.txt').write_text(names[0], encoding='utf-8')
        (C.DATA / 'dashboard-channels.json').write_text(json.dumps(names), encoding='utf-8')
        MODES_PATH.write_text(json.dumps(modes), encoding='utf-8')
        PAUSED_PATH.unlink(missing_ok=True)
        threading.Thread(target=collect, args=(process,), daemon=True).start()


def collect(child):
    for line in child.stdout:
        line = re.sub(r'bot\d+:[\w-]+', 'bot[oculto]', line.rstrip())
        with lock:
            logs.append(line)
    with lock:
        logs.append(f'Monitor encerrado (codigo {child.wait()}).')


def stop(persist=True):
    global running
    with lock:
        running = False
        if persist:
            PAUSED_PATH.touch()
        child = process
    if child and child.poll() is None:
        os.killpg(child.pid, signal.SIGINT)
        try:
            child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGTERM)


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, payload, content_type='application/json; charset=utf-8'):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            return self.respond(200, (Path(__file__).parent / 'dashboard.html').read_bytes(), 'text/html; charset=utf-8')
        if path in ('/editor-controls.js', '/editor-controls.css', '/jobs-controls.js', '/navigation.js', '/recordings.js', '/multi-controls.js'):
            content_type = 'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8'
            return self.respond(200, (Path(__file__).parent / path[1:]).read_bytes(), content_type)
        if path == '/api/state':
            with db._conn() as conn:
                clips = [dict(row) for row in conn.execute('SELECT * FROM clips ORDER BY id DESC LIMIT 100')]
            with lock:
                state = {'active': bool(process and process.poll() is None), 'channel': channel, 'channels': channels, 'modes': monitor_modes,
                         'clips': clips, 'logs': list(logs),
                         'ai_configured': bool(C.ANTHROPIC_API_KEY or C.OPENAI_API_KEY)}
            return self.respond(200, state)
        if path == '/api/jobs':
            return self.respond(200, db.list_jobs())
        if path == '/api/processing':
            return self.respond(200, queue_snapshot())
        if path == '/api/recordings':
            return self.respond(200, {'files': recordings.sources(), 'analyses': recordings.list_analyses(),
                                      'busy': recordings.busy})
        if path.startswith('/api/recording-video/'):
            try:
                video = recordings.source_path(unquote(path[len('/api/recording-video/'):]))
                size = video.stat().st_size
                match = re.fullmatch(r'bytes=(\d+)-(\d*)', self.headers.get('Range', ''))
                start = int(match.group(1)) if match else 0
                end = min(int(match.group(2)), size - 1) if match and match.group(2) else size - 1
                if start > end or start >= size:
                    self.send_response(416); self.send_header('Content-Range', f'bytes */{size}'); self.end_headers(); return
                self.send_response(206 if match else 200)
                self.send_header('Content-Type', {'.mp4':'video/mp4', '.mov':'video/quicktime', '.webm':'video/webm', '.mkv':'video/x-matroska', '.ts':'video/mp2t'}[video.suffix.lower()])
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Content-Length', str(end-start+1))
                if match: self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                self.end_headers()
                with video.open('rb') as f:
                    f.seek(start); remaining = end-start+1
                    while remaining:
                        block = f.read(min(1024*1024, remaining))
                        if not block: break
                        self.wfile.write(block); remaining -= len(block)
            except (ValueError, OSError):
                return self.respond(404, {'error': 'Video indisponivel'})
            return
        if path == '/api/edit-settings':
            return self.respond(200, edit_settings.load())
        if path == '/api/ai-status':
            return self.respond(200, {'openai': {'configured': bool(C.OPENAI_API_KEY), 'model': C.OPENAI_MODEL},
                                      'anthropic': {'configured': bool(C.ANTHROPIC_API_KEY), 'model': C.LLM_MODEL}})
        match = re.fullmatch(r'/api/video/(\d+)', path)
        if match:
            clip = db.get_clip(int(match.group(1)))
            if clip:
                video = Path(clip['path']).resolve()
                if video.is_relative_to(C.OUT_DIR.resolve()) and video.is_file():
                    return self.respond(200, video.read_bytes(), 'video/mp4')
        self.respond(404, {'error': 'Nao encontrado'})

    def do_POST(self):
        if self.headers.get('Origin') not in (None, f'http://{self.headers.get("Host")}'):
            return self.respond(403, {'error': 'Origem nao permitida'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length > 4096:
                raise ValueError('Dados muito grandes')
            data = json.loads(self.rfile.read(length) or b'{}')
            if self.path == '/api/start':
                start(data.get('channels', data.get('channel', '')), data.get('modes'))
            elif self.path == '/api/stop':
                stop()
            elif self.path == '/api/edit-settings':
                edit_settings.save(data)
            elif self.path == '/api/recordings/analyze':
                with lock:
                    if process and process.poll() is None:
                        raise ValueError('Pare o monitoramento antes de analisar uma gravacao.')
                    recordings.create_analysis(data['filename'], edit_settings.load())
            elif self.path == '/api/recordings/render':
                with lock:
                    recordings.render_candidate(int(data['id']))
            elif self.path == '/api/recordings/discard':
                automatic.discard_candidate(int(data['id']))
            elif self.path == '/api/recordings/retry':
                automatic.retry_analysis(int(data['id']))
            elif self.path == '/api/clip':
                clip = db.get_clip(int(data['id']))
                status = data['status']
                if not clip or status not in ('aprovado', 'rejeitado'):
                    raise ValueError('Corte ou status invalido')
                if status == 'aprovado':
                    src = Path(clip['path']).resolve()
                    if not src.is_relative_to(C.OUT_DIR.resolve()) or not src.is_file():
                        raise ValueError('Arquivo do corte nao encontrado')
                    shutil.copy2(src, C.APPROVED_DIR / src.name)
                db.set_status(int(data['id']), status)
            else:
                return self.respond(404, {'error': 'Nao encontrado'})
            self.respond(200, {'ok': True})
        except (ValueError, KeyError, OSError) as exc:
            self.respond(400, {'error': str(exc)})

    def log_message(self, *_):
        pass


def main():
    recordings.mark_interrupted()
    automatic_stop = threading.Event()
    threading.Thread(target=automatic.loop, args=(automatic_stop,), daemon=True).start()
    saved = C.DATA / 'dashboard-channel.txt'
    name = saved.read_text(encoding='utf-8').strip() if saved.exists() else C.CHANNEL
    saved_channels = C.DATA / 'dashboard-channels.json'
    names = json.loads(saved_channels.read_text(encoding='utf-8')) if saved_channels.exists() else ([name] if name else [])
    global channel, channels, monitor_modes
    channels = names
    channel = names[0] if names else ''
    try:
        monitor_modes = validate_modes(json.loads(MODES_PATH.read_text(encoding='utf-8'))) if MODES_PATH.exists() else {'peaks': True, 'recordings': True}
    except (ValueError, OSError):
        logging.warning('Opcoes salvas invalidas; usando ambos os tipos de corte.')
        monitor_modes = {'peaks': True, 'recordings': True}
    if names and (not monitor_modes['peaks'] or C.TELEGRAM_TOKEN and C.TELEGRAM_CHAT_ID) and not PAUSED_PATH.exists():
        start(names, monitor_modes)
    server = ThreadingHTTPServer(('0.0.0.0', 8000), Handler)
    def shutdown(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    try:
        server.serve_forever()
    finally:
        automatic_stop.set()
        stop(persist=False)
        server.server_close()


if __name__ == '__main__':
    main()
