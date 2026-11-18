import tempfile
import unittest
from pathlib import Path

from clipflow import edit_settings
from clipflow.editor import build_filter
from clipflow.subtitles import write_ass
from clipflow.transcribe import Word


class VideoLayoutTest(unittest.TestCase):
    def test_defaults_and_invalid_options(self):
        self.assertEqual(edit_settings.validate({})['orientation'], 'vertical')
        self.assertEqual(edit_settings.validate({})['background'], 'blur')
        for key, value in [('orientation', 'square'), ('background', 'other')]:
            with self.assertRaises(ValueError):
                edit_settings.validate({key: value})

    def test_horizontal_and_vertical_subtitle_dimensions(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'subs.ass'
            write_ass([Word('teste', 0, 1)], path, orientation='horizontal', watermark='@teste', duration=2)
            data = path.read_text(encoding='utf-8')
            self.assertIn('PlayResX: 1920\nPlayResY: 1080', data)
            self.assertIn('@teste', data)
            write_ass([], path, orientation='vertical')
            self.assertIn('PlayResX: 1080\nPlayResY: 1920', path.read_text(encoding='utf-8'))

    def test_graphs_preserve_options(self):
        for orientation in ('vertical', 'horizontal'):
            for bg in ('black', 'blur'):
                graph, _ = build_filter({'facecam': None}, 'subs.ass', .5, orientation, bg)
                self.assertIn('drawbox=color=black' if bg == 'black' else 'boxblur', graph)
                self.assertIn('ass=subs.ass', graph)


if __name__ == '__main__':
    unittest.main()
