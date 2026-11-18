"""Transcricao com timestamp por palavra usando whisper.cpp (Vulkan ou CPU)."""
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import config as C


@dataclass
class Word:
    text: str
    start: float
    end: float


def transcribe(video: Path, workdir: Path) -> list[Word]:
    if not C.WHISPER_MODEL:
        raise RuntimeError("defina WHISPER_MODEL no .env")
    wav = workdir / "audio.wav"
    subprocess.run([C.FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(video),
                    "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)
    prefix = workdir / "words"
    cmd = [C.WHISPER_BIN, "-m", C.WHISPER_MODEL, "-f", str(wav), "-l", C.WHISPER_LANG,
           "-t", str(C.WHISPER_THREADS), "-oj", "-of", str(prefix), "-ml", "1", "-sow", "-np"]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    data = json.loads((workdir / "words.json").read_text(encoding="utf-8", errors="replace"))
    words: list[Word] = []
    for seg in data.get("transcription", []):
        txt = seg.get("text", "")
        if not txt.strip() or (txt.strip().startswith("[") and txt.strip().endswith("]")):
            continue
        off = seg["offsets"]
        w = Word(txt.strip(), off["from"] / 1000, off["to"] / 1000)
        # pontuacao solta vem sem espaco inicial: cola na palavra anterior
        if words and not txt.startswith(" "):
            words[-1].text += w.text
        else:
            words.append(w)
    return words
