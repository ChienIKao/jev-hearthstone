import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from snapshot_io import publish_text

class SnapshotTests(unittest.TestCase):
    def test_busy_reader_retries_then_publishes(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'state.json'
            target.write_text('old', encoding='utf-8')
            original=Path.replace
            calls=[]
            def replace(source,destination):
                calls.append(1)
                if len(calls)<3:
                    raise PermissionError('sharing conflict')
                return original(source,destination)
            with patch.object(Path,'replace',replace):
                self.assertTrue(publish_text(target,'new',delay=0))
            self.assertEqual(target.read_text(encoding='utf-8'),'new')

    def test_persistent_lock_preserves_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'state.json'
            target.write_text('old',encoding='utf-8')
            with patch.object(Path,'replace',side_effect=PermissionError('busy')):
                self.assertFalse(publish_text(target,'new',attempts=2,delay=0))
            self.assertEqual(target.read_text(encoding='utf-8'),'old')

if __name__=='__main__':
    unittest.main()
