import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from clipflow import config, db, edit_settings, llm
from clipflow.transcribe import Word


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.words = [Word('Um momento', 1, 3), Word('incrível', 9, 10)]
        self.result = json.dumps({'start': 1, 'end': 20, 'title': 'Muito bom', 'publish': True,
                                  'criteria': {'gancho': 20, 'emocao': 21, 'compartilhamento': 22, 'autonomia': 19},
                                  'reason': 'O contexto e a conclusao estao claros.'})

    def test_openai_responses_and_metadata(self):
        response = SimpleNamespace(status='completed', output_text=self.result)
        with patch.object(config, 'OPENAI_API_KEY', 'fake'), patch('openai.OpenAI') as client:
            client.return_value.responses.create.return_value = response
            result = llm.refine(self.words, 40, 15, 15, 30, 'openai')
            self.assertEqual((result['method'], result['provider'], result['model']), ('ia', 'openai', config.OPENAI_MODEL))
            self.assertEqual(result['score'], 82)
            self.assertEqual(result['criteria']['gancho'], 20)
            self.assertEqual(result['rubric_version'], 2)
            request = client.return_value.responses.create.call_args.kwargs
            self.assertEqual(request['model'], config.OPENAI_MODEL)
            self.assertFalse(request['store'])
            self.assertEqual(request['text']['format']['type'], 'json_object')

    def test_anthropic_and_fallback(self):
        message = SimpleNamespace(content=[SimpleNamespace(type='text', text=self.result)])
        with patch.object(config, 'ANTHROPIC_API_KEY', 'fake'), patch('anthropic.Anthropic') as client:
            client.return_value.messages.create.return_value = message
            result = llm.refine(self.words, 40, 15, 15, 30, 'anthropic')
            self.assertEqual((result['method'], result['provider']), ('ia', 'anthropic'))
            client.return_value.messages.create.side_effect = RuntimeError('unavailable')
            self.assertEqual(llm.refine(self.words, 40, 15, 15, 30, 'anthropic')['method'], 'pausas')

    def test_openai_incomplete_response_and_missing_key(self):
        with patch.object(config, 'OPENAI_API_KEY', 'fake'), patch('openai.OpenAI') as client:
            client.return_value.responses.create.return_value = SimpleNamespace(status='incomplete', output_text=self.result)
            self.assertEqual(llm.refine(self.words, 40, 15, 15, 30, 'openai')['method'], 'pausas')
        with patch.object(config, 'OPENAI_API_KEY', ''):
            self.assertEqual(llm.refine(self.words, 40, 15, 15, 30, 'openai')['method'], 'pausas')

    def test_migrate_database_and_keep_provenance(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'legacy.db'
            with sqlite3.connect(path) as conn:
                conn.execute('CREATE TABLE clips (id INTEGER PRIMARY KEY, created TEXT, channel TEXT, path TEXT, title TEXT, score INTEGER, status TEXT)')
                conn.execute("INSERT INTO clips VALUES (1, '2020', 'test', '/tmp/a', 'old', 50, 'aguardando_aprovacao')")
            with patch.object(config, 'DB_PATH', path):
                clip_id = db.add_clip('test', '/tmp/b', 'new', 82, method='ia', provider='openai', model='gpt-5-mini', decision={'reason':'teste'})
                self.assertEqual(db.get_clip(clip_id)['ai_provider'], 'openai')
                self.assertEqual(json.loads(db.get_clip(clip_id)['ai_decision'])['reason'], 'teste')
                self.assertIsNone(db.get_clip(1)['analysis_method'])

    def test_missing_or_invalid_criteria_falls_back(self):
        response = SimpleNamespace(status='completed', output_text=json.dumps({'start': 1, 'end': 20, 'title': 'Teste', 'publish': True, 'criteria': {'gancho': 99}, 'reason': 'teste'}))
        with patch.object(config, 'OPENAI_API_KEY', 'fake'), patch('openai.OpenAI') as client:
            client.return_value.responses.create.return_value = response
            self.assertEqual(llm.refine(self.words, 40, 15, 15, 30, 'openai')['method'], 'pausas')

    def test_old_settings_and_unknown_provider(self):
        self.assertEqual(edit_settings.validate({})['ai_provider'], 'openai')
        with self.assertRaises(ValueError):
            edit_settings.validate({'ai_provider': 'other'})


if __name__ == '__main__':
    unittest.main()
