"""Grava a live em segmentos de 10 s num buffer circular e extrai trechos por horario."""
import logging
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import config as C

log = logging.getLogger("capture")
NAME_RE = re.compile(r"^(\d{8}-\d{6})\.ts$")


def seg_start(p: Path):
    m = NAME_RE.match(p.name)
    return datetime.strptime(m.group(1), "%Y%m%d-%H%M%S") if m else None


class Capture:
    def __init__(self, channel: str):
        self.channel = channel
        self.buffer_dir = C.BUFFER_DIR / channel
        self.buffer_dir.mkdir(parents=True, exist_ok=True)
        self._stop = threading.Event()
        self._procs = []

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._cleanup, daemon=True).start()

    def stop(self):
        self._stop.set()
        self._kill()

    def _kill(self):
        for p in self._procs:
            try:
                p.kill()
            except Exception:
                pass
        self._procs = []

    def _loop(self):
        while not self._stop.is_set():
            sl_cmd = [C.STREAMLINK, "--stdout", "--loglevel", "error",
                      f"twitch.tv/{self.channel}", C.STREAM_QUALITY]
            ff_cmd = [C.FFMPEG, "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
                      "-c", "copy", "-f", "segment", "-segment_time", str(C.SEGMENT_SECONDS),
                      "-strftime", "1", "-reset_timestamps", "1",
                      str(self.buffer_dir / "%Y%m%d-%H%M%S.ts")]
            try:
                sl = subprocess.Popen(sl_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                ff = subprocess.Popen(ff_cmd, stdin=sl.stdout, stderr=subprocess.DEVNULL)
                sl.stdout.close()
                self._procs = [sl, ff]
                log.info("capturando %s", self.channel)
                ff.wait()
            except FileNotFoundError as e:
                log.error("ferramenta nao encontrada: %s", e)
            self._kill()
            if not self._stop.is_set():
                log.info("live offline ou conexao caiu; nova tentativa em 15 s")
                time.sleep(15)

    def _cleanup(self):
        while not self._stop.is_set():
            limit = time.time() - (C.BUFFER_SECONDS + 60)
            for p in self.buffer_dir.glob("*.ts"):
                try:
                    if p.stat().st_mtime < limit:
                        p.unlink()
                except OSError:
                    pass
            time.sleep(30)

    def extract(self, t0: datetime, t1: datetime, out: Path) -> Path:
        """Junta os segmentos que cobrem [t0, t1] e recorta com precisao."""
        pad = timedelta(seconds=C.SEGMENT_SECONDS + 2)
        sel = []
        for p in sorted(self.buffer_dir.glob("*.ts")):
            s = seg_start(p)
            if s and s + pad > t0 and s < t1:
                sel.append((s, p))
        if not sel:
            raise RuntimeError("buffer sem video para esse intervalo")
        lst = out.with_suffix(".txt")
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for _, p in sel), encoding="utf-8")
        ss = max(0.0, (t0 - sel[0][0]).total_seconds())
        cmd = [C.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
               "-f", "concat", "-safe", "0", "-i", str(lst),
               "-ss", f"{ss:.2f}", "-t", f"{(t1 - t0).total_seconds():.2f}",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
               "-c:a", "aac", "-b:a", "160k", str(out)]
        subprocess.run(cmd, check=True)
        return out
