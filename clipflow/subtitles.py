"""Gera legenda .ass com destaque palavra por palavra."""
import re
from pathlib import Path

from .transcribe import Word

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

YELLOW = r"{\c&H00FFFF&}"
WHITE = r"{\c&HFFFFFF&}"


def _ts(t: float) -> str:
    cs = max(0, round(t * 100))
    return f"{cs // 360000}:{cs % 360000 // 6000:02d}:{cs % 6000 // 100:02d}.{cs % 100:02d}"


def _clean(s: str) -> str:
    return re.sub(r"[{}\\\n]", "", s).upper()


def _chunks(words, max_words=3, gap=0.6):
    cur = []
    for w in words:
        if cur and (len(cur) >= max_words or w.start - cur[-1].end > gap):
            yield cur
            cur = []
        cur.append(w)
        if re.search(r"[.!?,]$", w.text):
            yield cur
            cur = []
    if cur:
        yield cur


def write_ass(words: list[Word], path: Path, margin_v: int = 380, style: str = 'highlight',
              watermark: str = '', watermark_position: str = 'top_right', duration: float = 0):
    lines = [HEADER.format(margin=margin_v)]
    if watermark and duration > 0:
        align = {'top_left': 7, 'top_right': 9, 'bottom_left': 1, 'bottom_right': 3}[watermark_position]
        mark = re.sub(r'[{}\\\n]', '', watermark)
        lines.append(f'Dialogue: 1,0:00:00.00,{_ts(duration)},Default,,60,60,80,,{{\\an{align}\\fs44\\c&HFFFFFF&\\alpha&H30&\\bord2}}{mark}\n')
    for chunk in _chunks(words):
        for i, w in enumerate(chunk):
            end = chunk[i + 1].start if i + 1 < len(chunk) else w.end + 0.15
            if end <= w.start:
                end = w.start + 0.1
            active = {'highlight': YELLOW, 'pop': r'{\c&H00FFFF&\fscx115\fscy115\t(0,150,\fscx100\fscy100)}',
                      'clean': r'{\c&HFFFFFF&}'}[style]
            parts = [f"{active}{_clean(x.text)}{{\\r}}" if j == i else _clean(x.text)
                     for j, x in enumerate(chunk)]
            lines.append(f"Dialogue: 0,{_ts(w.start)},{_ts(end)},Default,,0,0,0,,{' '.join(parts)}\n")
    path.write_text("".join(lines), encoding="utf-8")
