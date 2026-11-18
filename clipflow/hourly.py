"""Grava cada live em blocos fechados; preserva arquivos parciais em falhas."""
import logging
import os
import subprocess
import threading
import uuid
from datetime import datetime
from . import config as C

log = logging.getLogger('hourly')
HOURS_DIR = C.DATA / 'hourly'


class HourlyRecorder:
    def __init__(self, channel):
        self.channel = channel
        self.stop_event = threading.Event()
        self.procs = []
        self.thread = None

    def start(self):
        HOURS_DIR.mkdir(parents=True, exist_ok=True)
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        for proc in list(self.procs):
            if proc.poll() is None:
                proc.terminate()
        if self.thread:
            self.thread.join(timeout=8)

    def _loop(self):
        while not self.stop_event.is_set():
            stem = f'{self.channel}_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:10]}'
            partial = HOURS_DIR / (stem + '.partial.ts')
            completed = False
            try:
                sl = subprocess.Popen([C.STREAMLINK, '--stdout', '--loglevel', 'error',
                                       f'twitch.tv/{self.channel}', C.STREAM_QUALITY], stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL)
                ff = subprocess.Popen([C.FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', '-i', 'pipe:0',
                                       '-t', '3600', '-c', 'copy', '-f', 'mpegts', str(partial)],
                                      stdin=sl.stdout, stderr=subprocess.DEVNULL)
                sl.stdout.close()
                self.procs = [ff, sl]
                log.info('gravacao de uma hora iniciada para %s', self.channel)
                code = ff.wait()
                if sl.poll() is None:
                    sl.terminate()
                sl.wait(timeout=10)
                if partial.exists() and partial.stat().st_size:
                    probe = subprocess.run([C.FFPROBE, '-v', 'error', '-show_entries', 'format=duration',
                                            '-of', 'csv=p=0', str(partial)], capture_output=True, text=True, check=True)
                    seconds = float(probe.stdout.strip())
                    if code == 0 and seconds >= 3590 and not self.stop_event.is_set():
                        temp_mp4 = HOURS_DIR / (stem + '.partial.mp4')
                        subprocess.run([C.FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', '-i', str(partial),
                                        '-map', '0:v:0', '-map', '0:a:0?', '-c', 'copy', '-movflags', '+faststart', str(temp_mp4)], check=True)
                        if not temp_mp4.is_file() or not temp_mp4.stat().st_size:
                            raise ValueError('Arquivo MP4 vazio')
                        os.replace(temp_mp4, HOURS_DIR / (stem + '.mp4'))
                        partial.unlink()
                        completed = True
                        log.info('bloco de uma hora finalizado para %s: %s', self.channel, stem)
                    else:
                        log.warning('gravacao parcial preservada para %s (%0.1fs): %s', self.channel, seconds, partial.name)
                elif partial.exists():
                    partial.unlink()  # arquivo vazio criado nesta tentativa
            except Exception as exc:
                log.warning('falha na gravacao de %s (%s); arquivo parcial preservado', self.channel, type(exc).__name__)
            finally:
                for proc in self.procs:
                    if proc.poll() is None:
                        proc.terminate()
                self.procs = []
            if not completed and not self.stop_event.is_set():
                self.stop_event.wait(15)
