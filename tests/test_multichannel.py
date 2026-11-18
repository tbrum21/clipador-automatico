import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from clipflow import capture, config, dashboard, db, main


class MultiChannelTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_buffers_are_separate(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(config, 'BUFFER_DIR', Path(temp)):
            a, b, c = capture.Capture('alfa'), capture.Capture('bravo'), capture.Capture('charlie')
            self.assertEqual(len({a.buffer_dir, b.buffer_dir, c.buffer_dir}), 3)
            for item in (a, b, c): self.assertTrue(item.buffer_dir.is_dir())

    async def test_dashboard_accepts_three_and_rejects_invalid(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(config, 'DATA', Path(temp)), \
             patch.object(dashboard, 'PAUSED_PATH', Path(temp) / 'paused'), \
             patch.object(dashboard, 'MODES_PATH', Path(temp) / 'modes.json'), \
             patch.object(config, 'TELEGRAM_TOKEN', 'token'), patch.object(config, 'TELEGRAM_CHAT_ID', '123'), \
             patch.object(dashboard, 'process', None), patch.object(dashboard, 'channel', ''), \
             patch.object(dashboard, 'channels', []), patch.object(dashboard, 'running', False), \
             patch.object(dashboard.subprocess, 'Popen') as popen, patch.object(dashboard.threading, 'Thread'):
            for names in ([], ['a','b','c','d'], ['abc','abc'], ['../a']):
                with self.assertRaises(ValueError): dashboard.start(names)
            dashboard.start(['alfa', 'https://www.twitch.tv/bravo', 'charlie'])
            env = popen.call_args.kwargs['env']
            self.assertEqual(env['TWITCH_CHANNELS'], 'alfa,bravo,charlie')
            self.assertEqual(dashboard.channels, ['alfa','bravo','charlie'])

    async def test_modes_are_validated_and_saved_for_restart(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(config, 'DATA', Path(temp)), \
             patch.object(dashboard, 'PAUSED_PATH', Path(temp) / 'paused'), \
             patch.object(dashboard, 'MODES_PATH', Path(temp) / 'modes.json'), \
             patch.object(config, 'TELEGRAM_TOKEN', ''), patch.object(config, 'TELEGRAM_CHAT_ID', ''), \
             patch.object(dashboard, 'process', None), patch.object(dashboard, 'monitor_modes', {}), \
             patch.object(dashboard.subprocess, 'Popen') as popen, patch.object(dashboard.threading, 'Thread'):
            for modes in ({'peaks': False, 'recordings': False}, {'peaks': 'false', 'recordings': True}, {'peaks': True}):
                with self.assertRaises(ValueError): dashboard.start(['alfa'], modes)
            with self.assertRaises(ValueError): dashboard.start(['alfa'], {'peaks': True, 'recordings': False})
            modes = {'peaks': False, 'recordings': True}
            dashboard.start(['alfa'], modes)
            env = popen.call_args.kwargs['env']
            self.assertEqual((env['CLIPFLOW_PEAKS'], env['CLIPFLOW_RECORDINGS']), ('0', '1'))
            self.assertEqual(__import__('json').loads(dashboard.MODES_PATH.read_text()), modes)

    async def test_monitor_starts_only_selected_capture_paths(self):
        for peaks, recordings in ((True, True), (True, False), (False, True)):
            env = {'TWITCH_CHANNELS': 'alfa', 'CLIPFLOW_PEAKS': str(int(peaks)), 'CLIPFLOW_RECORDINGS': str(int(recordings))}
            app = MagicMock()
            app.initialize = AsyncMock(); app.start = AsyncMock(); app.stop = AsyncMock(); app.shutdown = AsyncMock()
            app.updater.start_polling = AsyncMock(); app.updater.stop = AsyncMock(); app.bot.send_message = AsyncMock()
            with self.subTest(peaks=peaks, recordings=recordings), patch.dict('os.environ', env), \
                 patch.object(config, 'TELEGRAM_TOKEN', 'token'), patch.object(config, 'TELEGRAM_CHAT_ID', '123'), \
                 patch.object(main, 'Capture') as capture_class, patch.object(main, 'HourlyRecorder') as hourly_class, \
                 patch.object(main, 'build_app', return_value=app) as bot, patch.object(main.db, 'list_jobs', return_value=[]), \
                 patch.object(main.asyncio, 'sleep', side_effect=asyncio.CancelledError):
                with self.assertRaises(asyncio.CancelledError):
                    await main.amain()
                self.assertEqual(capture_class.called, peaks)
                self.assertEqual(hourly_class.called, recordings)
                self.assertEqual(bot.called, peaks)

    async def test_worker_preserves_channel_and_uses_one_queue(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(config, 'DB_PATH', Path(temp) / 'db.sqlite'):
            queue = asyncio.Queue()
            for i, channel in enumerate(('alfa','bravo','charlie'), 1):
                job = db.add_job(channel, __import__('datetime').datetime.now(), {})
                await queue.put((job, Path(temp) / f'{i}.mp4', {'channel': channel, 'z': 4, 'msgs': 20}))
            seen = []
            def render(raw, workdir, offset, channel, **kwargs):
                seen.append(channel)
                return {'out':raw, 'preview':raw, 'title':'Teste', 'score':50, 'publish':True, 'method':'fixo'}
            async def send(*args): pass
            with patch.object(main, 'run_from_raw', side_effect=render), patch.object(main, 'send_preview', side_effect=send):
                task = asyncio.create_task(main.worker(queue, None, object()))
                await asyncio.wait_for(queue.join(), timeout=10)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError): await task
            self.assertEqual(seen, ['alfa','bravo','charlie'])
            with db._conn() as c:
                self.assertEqual([row['channel'] for row in c.execute('SELECT channel FROM clips ORDER BY id')], seen)


if __name__ == '__main__': unittest.main()
