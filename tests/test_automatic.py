import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from clipflow import automatic, recordings, config, db, edit_settings


class AutomaticTests(unittest.TestCase):
    def test_automatic_dispatch_and_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); hours = root / 'hourly'; hours.mkdir()
            (hours / 'alfa_20261118_120000_0123456789.mp4').write_bytes(b'video')
            with patch.object(config, 'DB_PATH', root / 'db.sqlite'), patch.object(automatic, 'HOURS_DIR', hours), \
                 patch.object(recordings, 'HOURS_DIR', hours), patch.object(edit_settings, 'PATH', root / 'prefs.json'), \
                 patch.object(automatic.threading, 'Thread') as worker, patch.object(recordings, 'busy', False):
                automatic.register_completed()
                self.assertEqual(recordings.list_analyses()[0]['status'], 'fila_automatica')
                automatic.dispatch_next()
                self.assertEqual(recordings.list_analyses()[0]['status'], 'aguardando')
                self.assertTrue(worker.return_value.start.called)
                recordings.mark_interrupted()
                self.assertEqual(recordings.list_analyses()[0]['status'], 'fila_automatica')

    def test_review_gates_deletion_and_manual_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); hours = root / 'hourly'; hours.mkdir()
            out = root / 'out'; out.mkdir(); approved = root / 'approved'; approved.mkdir()
            name = 'alfa_20261118_120000_0123456789.mp4'; original = hours / name
            original.write_bytes(b'video de uma hora')
            with patch.object(config, 'DB_PATH', root / 'db.sqlite'), patch.object(config, 'OUT_DIR', out), \
                 patch.object(config, 'APPROVED_DIR', approved), patch.object(automatic, 'HOURS_DIR', hours), \
                 patch.object(recordings, 'HOURS_DIR', hours), patch.object(edit_settings, 'PATH', root / 'prefs.json'):
                automatic.register_completed()
                automatic.register_completed()
                rows = recordings.list_analyses(); self.assertEqual(len(rows), 1)
                aid = rows[0]['id']
                with db._conn() as c:
                    c.execute("UPDATE recording_analyses SET status='concluido' WHERE id=?", (aid,))
                self.assertFalse(automatic.maybe_delete(aid))  # zero sugestoes
                self.assertTrue(original.exists())
                with db._conn() as c:
                    first = c.execute("INSERT INTO recording_candidates (analysis_id,start,end,title,score,reason,decision) VALUES (?,?,?,?,?,?,?)", (aid,0,20,'a',70,'x','{}')).lastrowid
                    second = c.execute("INSERT INTO recording_candidates (analysis_id,start,end,title,score,reason,decision) VALUES (?,?,?,?,?,?,?)", (aid,30,50,'b',70,'x','{}')).lastrowid
                automatic.discard_candidate(first)
                self.assertTrue(original.exists())
                rendered = out / 'approved.mp4'; rendered.write_bytes(b'final')
                clip_id = db.add_clip('alfa', rendered, 'b', 70)
                with db._conn() as c:
                    c.execute("UPDATE recording_candidates SET status='pronto', clip_id=? WHERE id=?", (clip_id, second))
                db.set_status(clip_id, 'aprovado')  # sem copia aprovada: nao remove
                self.assertTrue(original.exists())
                (approved / rendered.name).write_bytes(b'final')
                self.assertTrue(automatic.maybe_delete(aid))
                self.assertFalse(original.exists())
                with db._conn() as c:
                    self.assertEqual(c.execute('SELECT status FROM hourly_assets WHERE analysis_id=?', (aid,)).fetchone()[0], 'excluido')

    def test_changed_original_and_unrelated_files_are_never_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); hours = root / 'hourly'; hours.mkdir()
            original = hours / 'alfa_20261118_120000_0123456789.mp4'; original.write_bytes(b'original')
            with patch.object(config, 'DB_PATH', root / 'db.sqlite'), patch.object(automatic, 'HOURS_DIR', hours), \
                 patch.object(recordings, 'HOURS_DIR', hours), patch.object(edit_settings, 'PATH', root / 'prefs.json'):
                automatic.register_completed()
                aid = recordings.list_analyses()[0]['id']
                with db._conn() as c:
                    c.execute("UPDATE recording_analyses SET status='concluido' WHERE id=?", (aid,))
                    cid = c.execute("INSERT INTO recording_candidates (analysis_id,start,end,title,score,reason,decision) VALUES (?,?,?,?,?,?,?)", (aid,0,20,'a',70,'x','{}')).lastrowid
                original.write_bytes(b'alterado e maior')
                automatic.discard_candidate(cid)
                self.assertTrue(original.exists())
                self.assertEqual(recordings.list_analyses()[0]['original_status'], 'disponivel')


if __name__ == '__main__': unittest.main()
