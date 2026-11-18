import asyncio
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from clipflow import config, db, main


class JobsTest(unittest.IsolatedAsyncioTestCase):
    async def test_extract_before_queue_and_track_stages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / 'raw.mp4'
            with patch.object(config, 'DB_PATH', root / 'clips.db'), \
                 patch.object(main.C, 'CHANNEL', 'teste'), \
                 patch.object(main.C, 'POST_SECONDS', 0), \
                 patch.object(main.C, 'SEGMENT_SECONDS', -3):
                queue = asyncio.Queue()
                def extract(capture, peak, job_id, settings):
                    self.assertTrue(queue.empty())
                    raw.write_bytes(b'raw')
                    return raw
                with patch.object(main, 'extract_peak', side_effect=extract), patch.object(main.asyncio, 'sleep', return_value=None):
                    await main.schedule(queue, object(), {'time': datetime.now(), 'z': 4.2, 'msgs': 20})
                job = db.list_jobs()[0]
                self.assertEqual(job['status'], 'na_fila')
                self.assertEqual(job['raw_path'], str(raw))
                def render(source, workdir, offset, template, on_stage, settings):
                    on_stage('transcrevendo')
                    self.assertEqual(db.list_jobs()[0]['status'], 'transcrevendo')
                    on_stage('renderizando')
                    return {'out': root / 'result.mp4', 'preview': root / 'preview.mp4',
                            'title': 'Teste', 'score': 50, 'publish': True, 'method': 'fixo'}
                async def send(*args):
                    self.assertEqual(db.list_jobs()[0]['status'], 'enviando')
                with patch.object(main, 'run_from_raw', side_effect=render), patch.object(main, 'send_preview', side_effect=send):
                    worker = asyncio.create_task(main.worker(queue, object(), object()))
                    await asyncio.wait_for(queue.join(), timeout=5)
                    worker.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await worker
                job = db.list_jobs()[0]
                self.assertEqual(job['status'], 'enviado')
                self.assertIsNotNone(job['clip_id'])

    async def test_extraction_failure_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'DB_PATH', Path(directory) / 'clips.db'), \
             patch.object(main.C, 'CHANNEL', 'teste'), patch.object(main.C, 'POST_SECONDS', 0), \
             patch.object(main.C, 'SEGMENT_SECONDS', -3), patch.object(main, 'extract_peak', side_effect=RuntimeError('sem buffer')), \
             patch.object(main.asyncio, 'sleep', return_value=None):
            queue = asyncio.Queue()
            await main.schedule(queue, object(), {'time': datetime.now(), 'z': 4, 'msgs': 20})
            self.assertTrue(queue.empty())
            job = db.list_jobs()[0]
            self.assertEqual(job['status'], 'erro')
            self.assertIn('sem buffer', job['error'])


if __name__ == '__main__':
    unittest.main()
