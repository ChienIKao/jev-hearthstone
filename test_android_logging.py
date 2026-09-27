import unittest
from unittest.mock import Mock
from pathlib import Path
import tempfile
import json
from android_logging import unlimited_log_config,configure_logging


class LoggingConfigTests(unittest.TestCase):
    def test_missing_original_is_backed_up_as_absent_and_only_settings_are_written(self):
        device=Mock(serial='config-test')
        pushed=[]
        def command(*args):
            if args[:2]==('shell','ls'):raise RuntimeError('No such file or directory')
            if args[0]=='push':pushed.append(Path(args[1]).read_bytes());return b''
            if args[:2]==('exec-out','cat'):return pushed[-1]
            return b''
        device.command.side_effect=command
        with tempfile.TemporaryDirectory() as directory:
            result=configure_logging(device,directory)
            backup=json.loads(Path(result['backup']).read_text(encoding='utf-8'))
            self.assertFalse(backup['existed'])
            self.assertEqual(backup['original'],'')
            self.assertEqual(pushed,[b'[Log]\nFileSizeLimit.Int=-1\n'])

    def test_add_section_preserves_other_settings(self):
        old='[Config]\r\nVersion=3\r\n[Localization]\r\nLocale=zhTW\r\n'
        result=unlimited_log_config(old)
        self.assertTrue(result.startswith(old))
        self.assertIn('[Log]\r\nFileSizeLimit.Int=-1\r\n',result)
        self.assertEqual(unlimited_log_config(result),result)

    def test_updates_only_log_section_and_rejects_duplicate_sections(self):
        old='[Other]\nFileSizeLimit.Int=8\n[Log]\nFileSizeLimit.Int=10000\n# note\n[Last]\nEnabled=True\n'
        result=unlimited_log_config(old)
        self.assertIn('[Other]\nFileSizeLimit.Int=8',result)
        self.assertIn('[Log]\nFileSizeLimit.Int=-1\n# note\n[Last]',result)
        with self.assertRaises(ValueError):unlimited_log_config('[Log]\n[Log]\n')


if __name__=='__main__':unittest.main()
