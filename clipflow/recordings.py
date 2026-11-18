"""Analise de gravacoes locais em blocos, com revisao antes da renderizacao."""
import json
import logging
import math
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from . import config as C, db, edit_settings
from .pipeline import probe_duration, run_from_raw
from .transcribe import transcribe
from .resource_guard import heavy_work
from .hourly import HOURS_DIR

log = logging.getLogger('recordings')
INPUT = C.ROOT / 'input'
EXTENSIONS = {'.mp4', '.mkv', '.mov', '.webm'}
BLOCK = 300
OVERLAP = 30
MAX_SECONDS = 3600
lock = threading.Lock()
busy = False


def source_path(name):
    if isinstance(name, str) and name.startswith('hourly:'):
        filename = name[len('hourly:'):]
        if not re.fullmatch(r'[a-z0-9_]{1,25}_\d{8}_\d{6}_[a-f0-9]{10}\.mp4', filename):
            raise ValueError('Nome de gravacao automatica invalido.')
        original = HOURS_DIR / filename
        path = original.resolve()
        if original.is_symlink() or path.parent != HOURS_DIR.resolve() or not path.is_file():
            raise ValueError('Gravacao automatica nao encontrada.')
        return path
    if not isinstance(name, str) or not name or Path(name).name != name or '/' in name or '\\' in name:
        raise ValueError('Nome de arquivo invalido.')
    path = (INPUT / name).resolve()
    if path.parent != INPUT.resolve() or path.suffix.lower() not in EXTENSIONS or not path.is_file():
        raise ValueError('Video nao encontrado na pasta input.')
    return path


def sources():
    if not INPUT.exists():
        return []
    return sorted([p.name for p in INPUT.iterdir() if p.is_file() and not p.is_symlink() and p.suffix.lower() in EXTENSIONS])


def _update(analysis_id, status, progress, error=None):
    with db._conn() as c:
        c.execute('UPDATE recording_analyses SET status=?, progress=?, error=? WHERE id=?',
                  (status, progress, error, analysis_id))


def reserve():
    global busy
    with lock:
        if busy:
            raise ValueError('Ja existe uma analise ou renderizacao de gravacao em andamento.')
        busy = True


def release():
    global busy
    with lock:
        busy = False


def analyze_block(words, duration, provider, minimum, maximum):
    if not words:
        return []
    lines = []
    for i in range(0, len(words), 12):
        chunk = words[i:i+12]
        lines.append(f'[{chunk[0].start:.1f}s] ' + ' '.join(w.text for w in chunk))
    prompt = (f'Analise a transcricao de uma live para encontrar ate tres momentos independentes com potencial '
              f'de engajamento em videos curtos. O bloco tem {duration:.1f}s. '
              f'Escolha intervalos entre {minimum} e {maximum} segundos com inicio, contexto e encerramento. '
              'Baseie-se apenas no texto, nao invente imagens nem prometa viralizacao. '
              'A nota de 0 a 100 e uma estimativa editorial subjetiva. '
              'Inclua apenas momentos que realmente tenham interesse; retorne lista vazia se nao houver. '
              'Responda em JSON: {"candidates":[{"start":numero,"end":numero,"title":"titulo",'
              '"score":inteiro,"reason":"justificativa com limites da avaliacao"}]}\nTranscricao:\n' + '\n'.join(lines))
    if provider == 'openai':
        if not C.OPENAI_API_KEY:
            raise ValueError('Configure OPENAI_API_KEY para analisar a gravacao.')
        from openai import OpenAI
        response = OpenAI(api_key=C.OPENAI_API_KEY, timeout=90, max_retries=1).responses.create(
            model=C.OPENAI_MODEL, input=prompt, max_output_tokens=2500, reasoning={'effort':'low'},
            text={'format': {'type':'json_object'}}, store=False)
        if response.status != 'completed':
            raise ValueError('Resposta da OpenAI incompleta.')
        text = response.output_text
    elif provider == 'anthropic':
        if not C.ANTHROPIC_API_KEY:
            raise ValueError('Configure ANTHROPIC_API_KEY para analisar a gravacao.')
        import anthropic
        response = anthropic.Anthropic(api_key=C.ANTHROPIC_API_KEY, timeout=90, max_retries=1).messages.create(
            model=C.LLM_MODEL, max_tokens=1500, messages=[{'role':'user','content':prompt}])
        text = ''.join(item.text for item in response.content if getattr(item, 'type', '') == 'text')
    else:
        raise ValueError('Provedor invalido.')
    try:
        result = json.loads(re.search(r'\{.*\}', text, re.DOTALL).group())['candidates']
    except (ValueError, KeyError, AttributeError, TypeError):
        raise ValueError('Resposta da IA invalida.') from None
    if not isinstance(result, list):
        raise ValueError('Lista de sugestoes invalida.')
    validated = []
    for item in result[:3]:
        try:
            start, end = float(item['start']), float(item['end'])
            score, title, reason = item['score'], item['title'], item['reason']
            if (not math.isfinite(start) or not math.isfinite(end) or start < 0 or end > duration
                or not minimum <= end-start <= maximum or type(score) is not int or not 0 <= score <= 100
                or not isinstance(title, str) or not title.strip() or len(title) > 160
                or not isinstance(reason, str) or not reason.strip() or len(reason) > 1000):
                continue
            validated.append({'start':start, 'end':end, 'score':score, 'title':title.strip(), 'reason':reason.strip()})
        except (TypeError, ValueError, KeyError):
            continue
    return validated


def select_candidates(items, limit=5):
    selected = []
    for item in sorted(items, key=lambda x: x['score'], reverse=True):
        if any(max(0, min(item['end'], x['end']) - max(item['start'], x['start'])) > 0 for x in selected):
            continue
        selected.append(item)
        if len(selected) == limit:
            break
    return selected


def list_analyses():
    with db._conn() as c:
        analyses = [dict(row) for row in c.execute('SELECT * FROM recording_analyses ORDER BY id DESC LIMIT 20')]
        for a in analyses:
            a['candidates'] = [dict(row) for row in c.execute('SELECT r.*, c.status AS clip_status FROM recording_candidates r LEFT JOIN clips c ON r.clip_id=c.id WHERE r.analysis_id=? ORDER BY r.score DESC', (a['id'],))]
            asset = c.execute('SELECT status,error FROM hourly_assets WHERE analysis_id=?', (a['id'],)).fetchone()
            a['original_status'] = asset['status'] if asset else None
            a['original_error'] = asset['error'] if asset else None
        return analyses


def create_analysis(filename, settings):
    source_path(filename)
    if settings['ai_provider'] == 'openai' and not C.OPENAI_API_KEY or settings['ai_provider'] == 'anthropic' and not C.ANTHROPIC_API_KEY:
        raise ValueError('Configure a chave do provedor de IA selecionado.')
    reserve()
    try:
        with db._conn() as c:
            analysis_id = c.execute('INSERT INTO recording_analyses (created,filename,status,progress,provider,settings) VALUES (?,?,?,?,?,?)',
                (datetime.now().isoformat(timespec='seconds'), filename, 'aguardando', 'Preparando', settings['ai_provider'], json.dumps(settings))).lastrowid
        threading.Thread(target=_analyze, args=(analysis_id,), daemon=True).start()
        return analysis_id
    except BaseException:
        release()
        raise


def _analyze(analysis_id):
    try:
        _update(analysis_id, 'em_fila', 'Aguardando recursos de processamento')
        with heavy_work():
            _analyze_work(analysis_id)
    finally:
        release()


def _analyze_work(analysis_id):
    try:
        with db._conn() as c:
            row = c.execute('SELECT * FROM recording_analyses WHERE id=?', (analysis_id,)).fetchone()
        source = source_path(row['filename'])
        duration = min(probe_duration(source), MAX_SECONDS)
        if duration <= 0:
            raise ValueError('Video sem duracao valida.')
        settings = json.loads(row['settings'])
        work = C.WORK_DIR / f'recording_{analysis_id}'
        work.mkdir(parents=True, exist_ok=True)
        candidates, offset, index = [], 0, 0
        while offset < duration:
            index += 1
            length = min(BLOCK, duration - offset)
            _update(analysis_id, 'transcrevendo', f'Bloco {index} · {offset/60:.1f} de {duration/60:.1f} min')
            block = work / f'block_{index}'
            block.mkdir(exist_ok=True)
            audio = block / 'block.wav'
            subprocess.run([C.FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', '-ss', str(offset), '-t', str(length),
                            '-i', str(source), '-vn', '-ac', '1', '-ar', '16000', str(audio)], check=True)
            try:
                words = transcribe(audio, block)
            finally:
                # Sao arquivos intermediarios deste bloco; o video original e preservado.
                audio.unlink(missing_ok=True)
                (block / 'audio.wav').unlink(missing_ok=True)
            _update(analysis_id, 'analisando', f'IA analisando bloco {index}')
            for candidate in analyze_block(words, length, row['provider'], settings['min_duration'], settings['max_duration']):
                candidate['start'] += offset
                candidate['end'] += offset
                candidates.append(candidate)
            if offset + length >= duration:
                break
            # A sobreposicao cobre a duracao maxima de um candidato, inclusive nas fronteiras.
            offset += BLOCK - max(OVERLAP, settings['max_duration'])
        with db._conn() as c:
            for candidate in select_candidates(candidates):
                c.execute('INSERT INTO recording_candidates (analysis_id,start,end,title,score,reason,decision) VALUES (?,?,?,?,?,?,?)',
                          (analysis_id, candidate['start'], candidate['end'], candidate['title'], candidate['score'], candidate['reason'], json.dumps(candidate, ensure_ascii=False)))
            c.execute('UPDATE recording_analyses SET status=?, progress=?, error=NULL WHERE id=?',
                      ('concluido', f'{min(duration, MAX_SECONDS)/60:.1f} min analisados', analysis_id))
    except Exception as exc:
        log.exception('Falha ao analisar gravacao %s', analysis_id)
        _update(analysis_id, 'erro', 'Analise interrompida', f'{type(exc).__name__}: verifique arquivo, modelo e conexao.')


def render_candidate(candidate_id):
    reserve()
    try:
        with db._conn() as c:
            candidate = c.execute('SELECT * FROM recording_candidates WHERE id=?', (candidate_id,)).fetchone()
            if not candidate or candidate['status'] not in ('sugerido','erro'):
                raise ValueError('Sugestao indisponivel para renderizacao.')
            c.execute("UPDATE recording_candidates SET status='renderizando' WHERE id=?", (candidate_id,))
        threading.Thread(target=_render, args=(candidate_id,), daemon=True).start()
    except BaseException:
        release()
        raise


def _render(candidate_id):
    try:
        with heavy_work():
            _render_work(candidate_id)
    finally:
        release()


def _render_work(candidate_id):
    try:
        with db._conn() as c:
            candidate = c.execute('SELECT c.*, a.filename, a.settings, a.provider FROM recording_candidates c JOIN recording_analyses a ON a.id=c.analysis_id WHERE c.id=?', (candidate_id,)).fetchone()
        source = source_path(candidate['filename'])
        work = C.WORK_DIR / f'recording_candidate_{candidate_id}'
        work.mkdir(exist_ok=True)
        raw = work / 'raw.mp4'
        subprocess.run([C.FFMPEG,'-y','-hide_banner','-loglevel','error','-ss',str(candidate['start']),
                        '-t',str(candidate['end']-candidate['start']),'-i',str(source),'-c:v','libx264',
                        '-preset','veryfast','-c:a','aac',str(raw)], check=True)
        settings = json.loads(candidate['settings'])
        settings['duration_mode'] = 'fixed'
        settings['zoom'] = False  # gravacoes nao possuem um instante de pico conhecido
        result = run_from_raw(raw, work, 0, use_llm=False, settings=settings)
        # A nota da selecao nao usa a rubrica da analise ao vivo.
        clip_id = db.add_clip('gravacao', result['out'], candidate['title'], candidate['score'], method='gravacao', provider=candidate['provider'])
        with db._conn() as c:
            c.execute("UPDATE recording_candidates SET status='pronto', clip_id=? WHERE id=?", (clip_id, candidate_id))
    except Exception:
        log.exception('Falha ao renderizar sugestao %s', candidate_id)
        with db._conn() as c:
            c.execute("UPDATE recording_candidates SET status='erro' WHERE id=?", (candidate_id,))


def mark_interrupted():
    with db._conn() as c:
        c.execute("""UPDATE recording_analyses SET status='fila_automatica', progress='Retomando apos reinicio', error=NULL
                     WHERE id IN (SELECT analysis_id FROM hourly_assets)
                     AND status IN ('aguardando','em_fila','transcrevendo','analisando')""")
        c.execute("UPDATE recording_analyses SET status='erro', progress='Analise interrompida', error='O painel foi reiniciado; inicie uma nova analise.' WHERE status IN ('aguardando','em_fila','transcrevendo','analisando')")
        c.execute("UPDATE recording_candidates SET status='erro' WHERE status='renderizando'")
