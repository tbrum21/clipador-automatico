import unittest
from unittest.mock import patch

from clipflow import edit_settings, llm
from clipflow.transcribe import Word


class DurationTest(unittest.TestCase):
    def test_legacy_settings_migrate(self):
        old = {k: v for k, v in edit_settings.DEFAULTS.items() if k not in
               ('duration_mode', 'context_before', 'context_after', 'min_duration', 'max_duration')}
        self.assertEqual(edit_settings.validate(old)['context_before'], 25)

    def test_validation(self):
        with self.assertRaises(ValueError):
            edit_settings.validate({**edit_settings.DEFAULTS, 'duration_mode': 'pause', 'min_duration': 80})
        with self.assertRaises(ValueError):
            edit_settings.validate({**edit_settings.DEFAULTS, 'context_before': 0})

    def test_pause_selection_and_short_clip(self):
        words = [Word('inicio', 10, 11), Word('fala', 12, 13), Word('fim', 28, 29)]
        result = llm.pause_decision(words, 90, 35, 15, 55)
        self.assertLessEqual(result['start'], 35)
        self.assertGreaterEqual(result['end'], 35)
        self.assertGreaterEqual(result['end'] - result['start'], 15)
        self.assertLessEqual(result['end'] - result['start'], 55)
        result = llm.pause_decision([], 8, 5, 15, 55)
        self.assertEqual((result['start'], result['end']), (0, 8))
        result = llm.pause_decision([], 90, 60, 15, 55)
        self.assertLessEqual(result['start'], 60)
        self.assertGreaterEqual(result['end'], 60)

    def test_ai_invalid_ranges_and_fallback(self):
        for start, end in [(float('nan'), 3), (100, 110), (12, 5), (-1, 10)]:
            with self.assertRaises(ValueError):
                llm._clamp({'start': start, 'end': end}, 90, 15, 55)
        with patch.object(llm.C, 'OPENAI_API_KEY', ''):
            self.assertEqual(llm.refine([Word('fala', 1, 2)], 90, 60, 15, 55)['method'], 'pausas')


if __name__ == '__main__':
    unittest.main()
