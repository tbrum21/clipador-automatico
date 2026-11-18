"""Configuracao central (le o arquivo .env na raiz do projeto)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
BUFFER_DIR = DATA / "buffer"
WORK_DIR = DATA / "work"
OUT_DIR = DATA / "out"
APPROVED_DIR = DATA / "approved"
DB_PATH = DATA / "clipflow.db"
TEMPLATES_PATH = ROOT / "templates.json"
for _d in (BUFFER_DIR, WORK_DIR, OUT_DIR, APPROVED_DIR):
    _d.mkdir(parents=True, exist_ok=True)

CHANNEL = os.getenv("TWITCH_CHANNEL", "").strip().lower().lstrip("#")
STREAM_QUALITY = os.getenv("STREAM_QUALITY", "720p60,720p,best")
HOURLY_STREAM_QUALITY = os.getenv("HOURLY_STREAM_QUALITY", "best").strip() or "best"

FFMPEG = os.getenv("FFMPEG_PATH", "ffmpeg")
FFPROBE = os.getenv("FFPROBE_PATH", "ffprobe")
STREAMLINK = os.getenv("STREAMLINK_PATH", "streamlink")
WHISPER_BIN = os.getenv("WHISPER_BIN", "whisper-cli")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "")
WHISPER_LANG = os.getenv("WHISPER_LANG", "pt")
WHISPER_THREADS = int(os.getenv("WHISPER_THREADS", "6"))

ENCODER = os.getenv("ENCODER", "libx264")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-haiku-5-5")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

PEAK_Z = float(os.getenv("PEAK_Z", "3.0"))
PEAK_MIN_MSGS = int(os.getenv("PEAK_MIN_MSGS", "12"))
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "90"))
WINDOW_SECONDS = 5

SEGMENT_SECONDS = 10
BUFFER_SECONDS = 300
PRE_SECONDS = int(os.getenv("PRE_SECONDS", "25"))
POST_SECONDS = int(os.getenv("POST_SECONDS", "10"))
ZOOM = os.getenv("ZOOM", "1") == "1"
ZOOM_LEAD = 5.0  # o chat reage depois do lance; o zoom entra ~5 s antes do pico
