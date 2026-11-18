"""Servico principal: captura + chat + deteccao + edicao + Telegram."""
import asyncio
import logging
import json
import os
import re
from datetime import datetime
from pathlib import Path

from . import config as C
from . import db
from .bot import build_app, send_preview
from .capture import Capture
from .chat import run_chat
from .detector import PeakDetector
from .pipeline import extract_peak, run_from_raw
from .edit_settings import load as load_edit_settings, validate as validate_edit_settings
from .hourly import HourlyRecorder
from .resource_guard import heavy_work

log = logging.getLogger("main")


def render_serialized(*args, **kwargs):
    with heavy_work():
        return run_from_raw(*args, **kwargs)


async def worker(queue: asyncio.Queue, capture: Capture, bot):
    """Processa um corte por vez (a placa de 4 GB nao aguenta dois ao mesmo tempo)."""
    while True:
        job_id, raw, info = await queue.get()
        try:
            settings = validate_edit_settings(info.get('settings', {}))
            channel = info.get('channel', C.CHANNEL)
            res = await asyncio.to_thread(render_serialized, raw, raw.parent, settings['context_before'], channel,
                                          on_stage=lambda stage: db.update_job(job_id, stage), settings=settings)
            clip_id = db.add_clip(channel, res["out"], res["title"], res["score"],
                                  method=res['method'], provider=res.get('provider'), model=res.get('model'), decision=res.get('decision'))
            db.update_job(job_id, 'enviando', clip_id=clip_id)
            flag = "" if res["publish"] else "\n⚠️ A IA sugere descartar este corte."
            score_label = f"Nota IA ({res['provider']}): {res['score']}/100" if res['method'] == 'ia' else 'Sem nota de IA'
            caption = (f"🎬 {res['title']}\n{score_label} | duração: {res['method']} | chat z={info['z']:.1f} "
                       f"({info['msgs']} msgs/5s)\nCredito: twitch.tv/{channel}{flag}")
            await send_preview(bot, clip_id, res["preview"], caption)
            db.update_job(job_id, 'enviado')
            log.info("corte %s enviado para aprovacao", clip_id)
        except Exception as exc:
            db.update_job(job_id, 'erro', error=str(exc)[:500])
            log.exception("falha ao processar o pico")
        finally:
            queue.task_done()


async def schedule(queue: asyncio.Queue, capture: Capture, info: dict, channel=None, extraction_lock=None):
    channel = channel or C.CHANNEL
    stored_info = {key: value for key, value in info.items() if key != 'time'}
    stored_info['channel'] = channel
    settings = load_edit_settings()
    stored_info['settings'] = settings
    job_id = db.add_job(channel, info['time'], stored_info)
    # espera o fim do lance + o segmento em escrita ser fechado
    await asyncio.sleep(settings['context_after'] + C.SEGMENT_SECONDS + 3)
    try:
        db.update_job(job_id, 'extraindo')
        if extraction_lock:
            async with extraction_lock:
                raw = await asyncio.to_thread(extract_peak, capture, info['time'], job_id, settings)
        else:
            raw = await asyncio.to_thread(extract_peak, capture, info['time'], job_id, settings)
        db.update_job(job_id, 'na_fila', raw_path=raw)
        await queue.put((job_id, raw, stored_info))
        log.info('trecho %s salvo e adicionado a fila', job_id)
    except Exception as exc:
        db.update_job(job_id, 'erro', error=str(exc)[:500])
        log.exception('falha ao salvar trecho %s', job_id)


async def amain():
    channels = [s.strip().lower() for s in os.getenv('TWITCH_CHANNELS', C.CHANNEL).split(',') if s.strip()]
    if not channels or len(channels) > 3 or len(set(channels)) != len(channels) or any(not re.fullmatch(r'[a-z0-9_]{1,25}', s) for s in channels):
        raise SystemExit("Defina TWITCH_CHANNEL no .env")
    if not (C.TELEGRAM_TOKEN and C.TELEGRAM_CHAT_ID):
        raise SystemExit("Defina TELEGRAM_TOKEN e TELEGRAM_CHAT_ID no .env")

    captures = {channel: Capture(channel) for channel in channels}
    hourly = {channel: HourlyRecorder(channel) for channel in channels}
    for capture in captures.values():
        capture.start()
    for recorder in hourly.values():
        recorder.start()
    app = build_app()
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    detectors = {channel: PeakDetector() for channel in channels}
    queue: asyncio.Queue = asyncio.Queue()
    extraction_lock = asyncio.Semaphore(1)
    for job in reversed(db.list_jobs(1000)):
        if job['channel'] not in channels:
            continue
        if job['status'] in ('detectado', 'extraindo'):
            db.update_job(job['id'], 'erro', error='Monitor reiniciado antes de concluir a extracao.')
            continue
        if job['status'] == 'enviando':
            db.update_job(job['id'], 'erro', error='Envio interrompido; confira o Telegram antes de reenviar.')
            continue
        if job['status'] not in ('na_fila', 'transcrevendo', 'analisando', 'renderizando', 'gerando_previa'):
            continue
        raw = Path(job['raw_path']) if job['raw_path'] else None
        if raw and raw.is_file():
            db.update_job(job['id'], 'na_fila')
            info = json.loads(job['info'])
            info['channel'] = job['channel']
            queue.put_nowait((job['id'], raw, info))
        else:
            db.update_job(job['id'], 'erro', error='Trecho bruto nao encontrado apos reinicio.')
    tasks = [asyncio.create_task(run_chat(channel, detectors[channel].add_message)) for channel in channels]
    tasks.append(asyncio.create_task(worker(queue, None, app.bot)))
    await app.bot.send_message(C.TELEGRAM_CHAT_ID, 'ClipFlow ligado. Monitorando: ' + ', '.join('twitch.tv/' + channel for channel in channels))
    try:
        while True:
            await asyncio.sleep(C.WINDOW_SECONDS)
            for channel in channels:
                peak = detectors[channel].tick(datetime.now())
                if peak:
                    log.info("PICO %s: z=%.1f, %d msgs", channel, peak["z"], peak["msgs"])
                    asyncio.create_task(schedule(queue, captures[channel], peak, channel, extraction_lock))
    finally:
        for t in tasks:
            t.cancel()
        for capture in captures.values():
            capture.stop()
        for recorder in hourly.values():
            recorder.stop()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    # O httpx registra URLs completas em INFO; no Telegram elas contem o token do bot.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
