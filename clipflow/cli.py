"""Ferramentas de teste:
  python -m clipflow.cli check
  python -m clipflow.cli make video.mp4 --peak 25 [--template nome] [--no-llm] [--send]
"""
import argparse
import asyncio
import logging
import shutil
import subprocess
from datetime import datetime

from . import config as C


def check(live: bool = False):
    ok = True
    for name, exe in [("ffmpeg", C.FFMPEG), ("ffprobe", C.FFPROBE), ("streamlink", C.STREAMLINK),
                      ("whisper", C.WHISPER_BIN)]:
        found = shutil.which(exe)
        print(f"[{'OK' if found else 'FALTA'}] {name}: {found or exe}")
        ok &= bool(found)
    from pathlib import Path
    m = Path(C.WHISPER_MODEL) if C.WHISPER_MODEL else None
    model_ok = bool(m and m.is_file() and m.stat().st_size > 0)
    print(f"[{'OK' if model_ok else 'FALTA'}] modelo whisper: {C.WHISPER_MODEL or '(vazio)'}")
    ok &= model_ok
    if shutil.which(C.FFMPEG):
        result = subprocess.run([C.FFMPEG, "-hide_banner", "-encoders"], capture_output=True, text=True)
        encoder_ok = result.returncode == 0 and C.ENCODER in result.stdout
        print(f"[{'OK' if encoder_ok else 'FALTA'}] encoder {C.ENCODER}")
        ok &= encoder_ok
    telegram_ok = bool(C.TELEGRAM_TOKEN and C.TELEGRAM_CHAT_ID)
    print(f"[{'OK' if telegram_ok else '--'}] Telegram configurado (necessario para envio/bot/live)")
    if live:
        channel_ok = bool(C.CHANNEL and C.CHANNEL != 'nome_do_canal')
        print(f"[{'OK' if channel_ok else 'FALTA'}] canal Twitch configurado")
        ok &= telegram_ok and channel_ok
    print(f"[{'OK' if C.OPENAI_API_KEY else '--'}] chave OpenAI configurada (opcional; nao validada)")
    print(f"[{'OK' if C.ANTHROPIC_API_KEY else '--'}] chave Anthropic configurada (opcional; nao validada)")
    return ok


def make(args):
    from .pipeline import run_from_raw

    src = shutil.os.path.abspath(args.video)
    workdir = C.WORK_DIR / f"manual_{datetime.now():%Y%m%d_%H%M%S}"
    workdir.mkdir(parents=True)
    raw = workdir / "raw.mp4"
    shutil.copy2(src, raw)
    res = run_from_raw(raw, workdir, args.peak, args.template, use_llm=not args.no_llm)
    print("Corte final:", res["out"])
    print("Titulo:", res["title"], "| nota:", res["score"])
    if args.send:
        from telegram import Bot
        from . import db
        from .bot import send_preview

        clip_id = db.add_clip("manual", res["out"], res["title"], res["score"],
                              method=res['method'], provider=res.get('provider'), model=res.get('model'), decision=res.get('decision'))
        asyncio.run(send_preview(Bot(C.TELEGRAM_TOKEN), clip_id, res["preview"], f"🎬 {res['title']}"))
        print("Previa enviada ao Telegram (rode 'clipflow.cli bot' ou o servico principal para os botoes funcionarem).")


def main():
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    checker = sub.add_parser("check")
    checker.add_argument("--live", action="store_true", help="exige tambem canal e configuracao do Telegram")
    sub.add_parser("bot", help="ouve aprovacoes do Telegram sem capturar uma live")
    m = sub.add_parser("make")
    m.add_argument("video")
    m.add_argument("--peak", type=float, default=25.0, help="segundo do video onde o chat 'explodiu'")
    m.add_argument("--template", default="default")
    m.add_argument("--no-llm", action="store_true")
    m.add_argument("--send", action="store_true")
    a = ap.parse_args()
    if a.cmd == "check":
        raise SystemExit(0 if check(live=a.live) else 1)
    if a.cmd == "bot":
        if not (C.TELEGRAM_TOKEN and C.TELEGRAM_CHAT_ID):
            raise SystemExit("Defina TELEGRAM_TOKEN e TELEGRAM_CHAT_ID no .env")
        from .bot import build_app
        build_app().run_polling()
    else:
        make(a)


if __name__ == "__main__":
    main()
