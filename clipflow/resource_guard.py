"""Limita trabalho pesado entre o monitor e o painel no container Linux."""
import contextlib
import fcntl
from . import config as C


@contextlib.contextmanager
def heavy_work():
    with (C.DATA / 'processing.lock').open('a') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
