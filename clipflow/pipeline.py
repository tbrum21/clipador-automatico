"""Fluxo completo: trecho bruto -> transcricao -> decisao -> legenda -> render -> preview."""
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from . import config as C
from .editor import load_template, make_preview, render
from .llm import default_decision, pause_decision, refine
from .subtitles import write_ass
from .transcribe import Word, transcribe
from .edit_settings import load as load_edit_settings, validate as validate_edit_settings

log = logging.getLogger("pipeline")


def probe_duration(path: Path) -> float:
    out = subprocess.run([C.FFPROBE, "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def run_from_raw(raw: Path, workdir: Path, peak_offset: float, template_name: str = "default",
                 use_llm: bool = True, on_stage=None, settings=None) -> dict:
    def stage(name):
        if on_stage:
            on_stage(name)
    dur = probe_duration(raw)
    settings = validate_edit_settings(settings) if settings is not None else load_edit_settings()
    stage('transcrevendo')
    log.info("transcrevendo %.0fs de video...", dur)
    words = transcribe(raw, workdir)
    stage('analisando')
    mode = settings['duration_mode']
    minimum, maximum = settings['min_duration'], settings['max_duration']
    if mode == 'fixed':
        decision = {'start': 0.0, 'end': dur, 'title': 'Momento da live', 'score': 50,
                    'publish': True, 'method': 'fixo'}
    elif mode == 'ai' and use_llm:
        decision = refine(words, dur, peak_offset, minimum, maximum, settings['ai_provider'])
    else:
        decision = pause_decision(words, dur, peak_offset, minimum, maximum)
    log.info('duracao escolhida: %.1fs–%.1fs (%s)', decision['start'], decision['end'], decision['method'])
    start, end = decision["start"], decision["end"]

    shifted = [Word(w.text, w.start - start, w.end - start)
               for w in words if w.end > start and w.start < end]
    ass = workdir / "subs.ass"
    write_ass(shifted if settings['subtitles'] else [], ass, style=settings['subtitle_style'],
              watermark=settings['watermark'], watermark_position=settings['watermark_position'], duration=end - start,
              orientation=settings['orientation'])

    zoom_at = None
    if settings['zoom']:
        z = peak_offset - C.ZOOM_LEAD - start
        zoom_at = z if 0 <= z <= (end - start) else None

    out = C.OUT_DIR / f"{workdir.name}.mp4"
    log.info("renderizando %.0fs -> %s", end - start, out.name)
    stage('renderizando')
    render(raw, start, end - start, ass.name, workdir, out, load_template(template_name), zoom_at,
           orientation=settings['orientation'], background=settings['background'])
    preview = workdir / "preview.mp4"
    stage('gerando_previa')
    make_preview(out, preview, orientation=settings['orientation'])
    return {"out": out, "preview": preview, "title": decision["title"],
            "score": decision["score"], "publish": decision["publish"], 'method': decision['method'],
            'provider': decision.get('provider'), 'model': decision.get('model'),
            'decision': decision if decision['method'] == 'ia' else None}


def extract_peak(capture, t_peak: datetime, job_id: int, settings=None) -> Path:
    settings = settings or load_edit_settings()
    t0 = t_peak - timedelta(seconds=settings['context_before'])
    t1 = t_peak + timedelta(seconds=settings['context_after'])
    workdir = C.WORK_DIR / f"clip_{t_peak:%Y%m%d_%H%M%S}_{job_id}"
    workdir.mkdir(parents=True, exist_ok=True)
    return capture.extract(t0, t1, workdir / "raw.mp4")
