import multiprocessing
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from clipflow import config, resource_guard


def worker(name, acquired, release):
    with resource_guard.heavy_work('teste', name):
        acquired.put(name)
        release.wait(10)


class ResourceGuardTests(unittest.TestCase):
    def test_fifo_between_processes_and_abandoned_ticket(self):
        ctx = multiprocessing.get_context('fork')
        with tempfile.TemporaryDirectory() as temp, patch.object(config, 'DATA', Path(temp)):
            acquired = ctx.Queue()
            releases = [ctx.Event() for _ in range(3)]
            processes = []
            try:
                for i in range(3):
                    proc = ctx.Process(target=worker, args=(f'tarefa {i}', acquired, releases[i]))
                    proc.start()
                    processes.append(proc)
                    deadline = time.monotonic() + 10
                    while len(resource_guard.queue_snapshot()) < i + 1 and time.monotonic() < deadline:
                        time.sleep(.05)
                    self.assertEqual(len(resource_guard.queue_snapshot()), i + 1)
                self.assertEqual(acquired.get(timeout=5), 'tarefa 0')
                processes[1].terminate()
                processes[1].join(5)
                releases[0].set()
                self.assertEqual(acquired.get(timeout=5), 'tarefa 2')
                self.assertEqual([x['description'] for x in resource_guard.queue_snapshot()], ['tarefa 2'])
                releases[2].set()
                processes[0].join(5)
                processes[2].join(5)
                self.assertEqual(resource_guard.queue_snapshot(), [])
            finally:
                for proc in processes:
                    if proc.is_alive():
                        proc.terminate()
                    proc.join(5)


if __name__ == '__main__':
    unittest.main()
