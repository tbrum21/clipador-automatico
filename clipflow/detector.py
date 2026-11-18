"""Detecta picos de atividade no chat (media movel + desvio padrao)."""
import statistics
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

from . import config as C

KEYWORDS = (
    "kekw", "omegalul", "lul", "pog", "poggers", "pogchamp", "wtf", "no way", "lmao", "lol",
    "clip", "???", "!!!", "kkkk", "mds", "caralho", "meu deus", "eita", "pqp", "inacreditavel",
    "gta", "rip", "f ",
)


class PeakDetector:
    def __init__(self, history_windows: int = 60, warmup: int = 12):
        self.history = deque(maxlen=history_windows)
        self.warmup = warmup
        self.count = 0
        self.kw = 0
        self.cooldown_until: Optional[datetime] = None

    def add_message(self, text: str):
        self.count += 1
        low = text.lower()
        if any(k in low for k in KEYWORDS):
            self.kw += 1

    def tick(self, now: datetime) -> Optional[dict]:
        """Chamar ao fim de cada janela de WINDOW_SECONDS."""
        rate = self.count + 2 * self.kw
        raw = self.count
        self.count = 0
        self.kw = 0
        peak = None
        if len(self.history) >= self.warmup:
            mean = statistics.fmean(self.history)
            std = max(statistics.pstdev(self.history), 1.0)
            z = (rate - mean) / std
            in_cooldown = self.cooldown_until and now < self.cooldown_until
            if z >= C.PEAK_Z and raw >= C.PEAK_MIN_MSGS and not in_cooldown:
                peak = {"time": now, "z": z, "msgs": raw, "rate": rate}
                self.cooldown_until = now + timedelta(seconds=C.COOLDOWN_SECONDS)
        self.history.append(rate)
        return peak
