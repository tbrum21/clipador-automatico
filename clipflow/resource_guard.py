"""Fila FIFO de trabalho pesado compartilhada entre processos do container."""
import contextlib
import fcntl
import os
import sqlite3
import time
from pathlib import Path

from . import config as C


def _identity(pid):
    try:
        # O nome entre parenteses pode conter espacos; os campos seguintes comecam no estado.
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return None if fields[0] == 'Z' else fields[19]
    except (OSError, IndexError):
        return None


def _connect():
    conn = sqlite3.connect(C.DATA / 'processing-queue.sqlite', timeout=30)
    conn.execute('PRAGMA busy_timeout=30000')
    conn.execute('''CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT, pid INTEGER NOT NULL, identity TEXT NOT NULL,
        kind TEXT NOT NULL, description TEXT NOT NULL, created REAL NOT NULL)''')
    return conn


def _clean(conn):
    for ticket, pid, identity in conn.execute('SELECT id, pid, identity FROM queue').fetchall():
        if _identity(pid) != identity:
            conn.execute('DELETE FROM queue WHERE id=?', (ticket,))


def queue_snapshot():
    with contextlib.closing(_connect()) as conn:
        with conn:
            _clean(conn)
            rows = conn.execute('SELECT kind, description, created FROM queue ORDER BY id').fetchall()
    now = time.time()
    return [{'position': i + 1, 'kind': row[0], 'description': row[1],
             'elapsed_seconds': max(0, int(now - row[2]))} for i, row in enumerate(rows)]


@contextlib.contextmanager
def heavy_work(kind='processamento', description='Processamento'):
    identity = _identity(os.getpid())
    if identity is None:
        raise RuntimeError('Nao foi possivel identificar o processo para a fila.')
    with contextlib.closing(_connect()) as conn:
        with conn:
            _clean(conn)
            ticket = conn.execute('INSERT INTO queue (pid,identity,kind,description,created) VALUES (?,?,?,?,?)',
                                  (os.getpid(), identity, kind, description, time.time())).lastrowid
        try:
            while True:
                with conn:
                    _clean(conn)
                    first = conn.execute('SELECT id FROM queue ORDER BY id LIMIT 1').fetchone()
                if first and first[0] == ticket:
                    break
                time.sleep(0.25)
            # Mantem a exclusao mutua com processos que ainda usam o bloqueio anterior.
            with (C.DATA / 'processing.lock').open('a') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        finally:
            with conn:
                conn.execute('DELETE FROM queue WHERE id=?', (ticket,))
