import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from clipflow import config, db, edit_settings, recordings
from clipflow.transcribe import Word


class RecordingTests(unittest.TestCase):
    def test_block_validate_and_provider_failure(self):
        payload = {'candidates': [
            {'start': 10, 'end': 30, 'title': 'Momento', 'score': 82, 'reason': 'Tem surpresa.'},
            {'start': -1, 'end': 30, 'title': 'Invalido', 'score': 80, 'reason': 'Erro.'}]}
        with patch.object(config, 'OPENAI_API_KEY', 'fake'), patch('openai.OpenAI') as client:
            client.return_value.responses.create.return_value = SimpleNamespace(status='completed', output_text=json.dumps(payload))
            result = recordings.analyze_block([Word('ola', 1, 2)], 300, 'openai', 15, 90)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['title'], 'Momento')
            self.assertFalse(client.return_value.responses.create.call_args.kwargs['store'])
            client.return_value.responses.create.return_value.status = 'incomplete'
            with self.assertRaises(ValueError):
                recordings.analyze_block([Word('ola', 1, 2)], 300, 'openai', 15, 90)

    def test_dedup_and_limit(self):
        items = [{'start':i*100, 'end':i*100+40, 'score':99-i} for i in range(8)]
        items.append({'start':5, 'end':30, 'score':50})
        result = recordings.select_candidates(items)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0]['start'], 0)

    def test_end_to_end_suggestions_without_render_or_sending(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inputs = root / 'input'; inputs.mkdir()
            (inputs / 'live.mp4').write_bytes(b'sample')
            work = root / 'work'; work.mkdir()
            settings = dict(edit_settings.DEFAULTS, min_duration=15, max_duration=90)
            with patch.object(config, 'DB_PATH', root / 'test.db'), patch.object(config, 'WORK_DIR', work), \
                 patch.object(recordings, 'INPUT', inputs), patch.object(recordings, 'probe_duration', return_value=600), \
                 patch.object(recordings.subprocess, 'run'), patch.object(recordings, 'transcribe', return_value=[Word('oi',1,2)]), \
                 patch.object(recordings, 'analyze_block', side_effect=lambda *args: [{'start':10.,'end':30.,'title':'Bom','score':80,'reason':'Surpresa'}]) as ai:
                with db._conn() as c:
                    analysis_id = c.execute('INSERT INTO recording_analyses (created,filename,status,progress,provider,settings) VALUES (?,?,?,?,?,?)',
                        ('2026','live.mp4','aguardando','', 'openai', json.dumps(settings))).lastrowid
                recordings._analyze(analysis_id)
                self.assertEqual(ai.call_count, 3)  # 300s com sobreposicao de 90s
                analysis = recordings.list_analyses()[0]
                self.assertEqual(analysis['status'], 'concluido')
                self.assertEqual(len(analysis['candidates']), 3)
                self.assertTrue(all(x['status'] == 'sugerido' and x['clip_id'] is None for x in analysis['candidates']))
                with self.assertRaises(ValueError): recordings.source_path('../live.mp4')
                with db._conn() as c:
                    self.assertEqual(c.execute('SELECT COUNT(*) FROM clips').fetchone()[0], 0)

    def test_render_only_selected_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); inputs = root / 'input'; inputs.mkdir(); work = root / 'work'; work.mkdir()
            (inputs / 'live.mp4').write_bytes(b'original')
            settings = dict(edit_settings.DEFAULTS)
            with patch.object(config, 'DB_PATH', root / 'test.db'), patch.object(config, 'WORK_DIR', work), \
                 patch.object(recordings, 'INPUT', inputs), patch.object(recordings.subprocess, 'run') as ffmpeg, \
                 patch.object(recordings, 'run_from_raw', return_value={'out':root / 'final.mp4'}) as pipeline:
                with db._conn() as c:
                    aid = c.execute('INSERT INTO recording_analyses (created,filename,status,progress,provider,settings) VALUES (?,?,?,?,?,?)',
                        ('2026','live.mp4','concluido','', 'openai', json.dumps(settings))).lastrowid
                    cid = c.execute('INSERT INTO recording_candidates (analysis_id,start,end,title,score,reason,decision) VALUES (?,?,?,?,?,?,?)',
                        (aid,10,40,'Trecho',80,'Motivo','{}')).lastrowid
                recordings._render(cid)
                self.assertEqual((inputs / 'live.mp4').read_bytes(), b'original')
                self.assertEqual(ffmpeg.call_args.args[0][ffmpeg.call_args.args[0].index('-ss') + 1], '10.0')
                self.assertFalse(pipeline.call_args.kwargs['use_llm'])
                self.assertEqual(pipeline.call_args.kwargs['settings']['duration_mode'], 'fixed')
                candidate = recordings.list_analyses()[0]['candidates'][0]
                self.assertEqual(candidate['status'], 'pronto')
                self.assertEqual(db.get_clip(candidate['clip_id'])['title'], 'Trecho')


if __name__ == '__main__':
    unittest.main()
