"""Descobre gravacoes finalizadas e despacha analise, com exclusao apos revisao completa."""
import json
import logging
import threading
from datetime import datetime
from . import config as C, db, edit_settings, recordings
from .hourly import HOURS_DIR

log = logging.getLogger('automatic')


def register_completed():
    HOURS_DIR.mkdir(parents=True, exist_ok=True)
    for file in HOURS_DIR.glob('*.mp4'):
        name = 'hourly:' + file.name
        try:
            if file.name.endswith('.partial.mp4') or file.is_symlink():
                continue
            path = recordings.source_path(name)
            stat = path.stat()
            if stat.st_size == 0:
                continue
            settings = edit_settings.load()
            with db._conn() as c:
                if c.execute('SELECT 1 FROM hourly_assets WHERE filename=?', (file.name,)).fetchone():
                    continue
                aid = c.execute('INSERT INTO recording_analyses (created,filename,status,progress,provider,settings) VALUES (?,?,?,?,?,?)',
                                (datetime.now().isoformat(timespec='seconds'), name, 'fila_automatica', 'Aguardando analise',
                                 settings['ai_provider'], json.dumps(settings))).lastrowid
                c.execute('INSERT INTO hourly_assets (filename,analysis_id,size,modified_ns) VALUES (?,?,?,?)',
                          (file.name, aid, stat.st_size, stat.st_mtime_ns))
            log.info('gravacao %s adicionada a fila automatica', file.name)
        except (ValueError, OSError):
            log.exception('nao foi possivel registrar gravacao %s', file.name)


def dispatch_next():
    with db._conn() as c:
        row = c.execute("SELECT id FROM recording_analyses WHERE status='fila_automatica' ORDER BY id LIMIT 1").fetchone()
    if not row:
        return
    try:
        recordings.reserve()
    except ValueError:
        return
    try:
        recordings._update(row['id'], 'aguardando', 'Iniciando analise automatica')
        threading.Thread(target=recordings._analyze, args=(row['id'],), daemon=True).start()
    except BaseException:
        recordings.release()
        raise


def discard_candidate(candidate_id):
    with db._conn() as c:
        row = c.execute('SELECT * FROM recording_candidates WHERE id=?', (candidate_id,)).fetchone()
        if not row or row['status'] not in ('sugerido', 'erro'):
            raise ValueError('Sugestao nao pode ser rejeitada neste estado.')
        c.execute("UPDATE recording_candidates SET status='rejeitado' WHERE id=?", (candidate_id,))
    maybe_delete(row['analysis_id'])


def retry_analysis(analysis_id):
    with db._conn() as c:
        asset = c.execute('SELECT * FROM hourly_assets WHERE analysis_id=?', (analysis_id,)).fetchone()
        analysis = c.execute('SELECT status FROM recording_analyses WHERE id=?', (analysis_id,)).fetchone()
        if not asset or asset['status'] != 'disponivel' or not analysis or analysis['status'] != 'erro':
            raise ValueError('Analise nao disponivel para nova tentativa.')
        path = recordings.source_path('hourly:' + asset['filename'])
        stat = path.stat()
        if stat.st_size != asset['size'] or stat.st_mtime_ns != asset['modified_ns']:
            raise ValueError('O arquivo original foi modificado.')
        c.execute("UPDATE recording_analyses SET status='fila_automatica', progress='Aguardando nova tentativa', error=NULL WHERE id=?", (analysis_id,))


def maybe_delete_for_clip(clip_id):
    with db._conn() as c:
        row = c.execute('SELECT analysis_id FROM recording_candidates WHERE clip_id=?', (clip_id,)).fetchone()
    if row:
        maybe_delete(row['analysis_id'])


def maybe_delete(analysis_id):
    """Somente arquivos proprios com identidade inalterada e todas as sugestoes revisadas."""
    with db._conn() as c:
        asset = c.execute('SELECT * FROM hourly_assets WHERE analysis_id=?', (analysis_id,)).fetchone()
        if not asset or asset['status'] != 'disponivel':
            return False
        analysis = c.execute('SELECT status FROM recording_analyses WHERE id=?', (analysis_id,)).fetchone()
        rows = c.execute('''SELECT r.status, r.clip_id, c.status AS clip_status, c.path AS clip_path
                            FROM recording_candidates r LEFT JOIN clips c ON c.id=r.clip_id
                            WHERE r.analysis_id=?''', (analysis_id,)).fetchall()
        if not analysis or analysis['status'] != 'concluido' or not rows:
            return False
        for row in rows:
            if row['status'] == 'rejeitado':
                continue
            if row['status'] != 'pronto' or row['clip_status'] not in ('aprovado', 'rejeitado'):
                return False
            if row['clip_status'] == 'aprovado':
                from pathlib import Path
                src = Path(row['clip_path']).resolve()
                approved = C.APPROVED_DIR / src.name
                if (not src.is_relative_to(C.OUT_DIR.resolve()) or not src.is_file() or not approved.is_file()
                        or approved.stat().st_size == 0 or approved.stat().st_size != src.stat().st_size):
                    return False
        try:
            original = HOURS_DIR / asset['filename']
            if original.is_symlink():
                raise ValueError('Origem substituida por link')
            path = recordings.source_path('hourly:' + asset['filename'])
            stat = path.stat()
            if stat.st_size != asset['size'] or stat.st_mtime_ns != asset['modified_ns']:
                raise ValueError('Gravacao foi modificada apos registro')
            path.unlink()
            c.execute("UPDATE hourly_assets SET status='excluido', error=NULL WHERE analysis_id=?", (analysis_id,))
            log.info('gravacao original %s excluida apos revisao', asset['filename'])
            return True
        except (OSError, ValueError) as exc:
            c.execute('UPDATE hourly_assets SET error=? WHERE analysis_id=?', (str(exc)[:300], analysis_id))
            log.error('gravacao nao excluida: %s', type(exc).__name__)
            return False


def loop(stop_event):
    while not stop_event.is_set():
        try:
            register_completed()
            dispatch_next()
        except Exception:
            log.exception('falha no despachante automatico')
        stop_event.wait(10)
