import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from clipflow import hourly


class HourlyTests(unittest.TestCase):
    def test_completed_hour_finalized_before_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            recorder = hourly.HourlyRecorder('canal')
            recorder.stop_event.wait = lambda *_: recorder.stop_event.set()
            class Pipe:
                def close(self): pass
            class Process:
                stdout = Pipe()
                def __init__(self, stream=False): self.stream = stream
                def wait(self, timeout=None): return 0
                def poll(self): return 0
                def terminate(self): pass
            def popen(args, **kwargs):
                if args[0] == hourly.C.FFMPEG:
                    self.assertEqual(args[args.index('-c') + 1], 'copy')
                    Path(args[-1]).write_bytes(b'ts')
                    return Process()
                self.assertEqual(args[-1], 'best')
                return Process(True)
            def run(args, **kwargs):
                if args[0] == hourly.C.FFPROBE:
                    return SimpleNamespace(stdout='3600.0')
                Path(args[-1]).write_bytes(b'mp4')
                recorder.stop_event.set()
                return SimpleNamespace(returncode=0)
            with patch.object(hourly, 'HOURS_DIR', directory), patch.object(hourly.C, 'STREAM_QUALITY', '360p'), \
                 patch.object(hourly.C, 'HOURLY_STREAM_QUALITY', 'best'), patch.object(hourly.subprocess, 'Popen', side_effect=popen), \
                 patch.object(hourly.subprocess, 'run', side_effect=run):
                recorder._loop()
            files = list(directory.iterdir())
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].suffix, '.mp4')
            self.assertEqual(files[0].read_bytes(), b'mp4')
            self.assertNotIn('partial', files[0].name)

    def test_partial_is_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); recorder = hourly.HourlyRecorder('canal')
            recorder.stop_event.wait = lambda *_: recorder.stop_event.set()
            class Pipe:
                def close(self): pass
            class Process:
                stdout = Pipe()
                def wait(self, timeout=None): return 0
                def poll(self): return 0
                def terminate(self): pass
            def popen(args, **kwargs):
                if args[0] == hourly.C.FFMPEG: Path(args[-1]).write_bytes(b'partial')
                return Process()
            with patch.object(hourly, 'HOURS_DIR', directory), patch.object(hourly.subprocess, 'Popen', side_effect=popen), \
                 patch.object(hourly.subprocess, 'run', return_value=SimpleNamespace(stdout='20.0')):
                recorder._loop()
            self.assertEqual(len(list(directory.glob('*.partial.ts'))), 1)
            self.assertEqual(len(list(directory.glob('*.mp4'))), 0)


if __name__ == '__main__': unittest.main()
