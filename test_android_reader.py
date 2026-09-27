import unittest
from unittest.mock import patch, Mock

from android_reader import AndroidReader


class Device:
    serial='test'
    session='Hearthstone_2026_09_27_13_43_27'
    data=b''

    def command(self,*args):
        if args[0]=='shell':
            return self.session.encode()
        if args[1]=='tail':
            return self.data[int(args[3][1:])-1:]
        return self.data


class AndroidReaderTests(unittest.TestCase):
    def test_adb_missing_file_stdout_is_not_counted_as_game_data(self):
        device=Device()
        path='/sdcard/Android/data/com.blizzard.wtcg.hearthstone/files/Logs/'+device.session+'/Power.log'
        device.data=('cat: '+path+': No such file or directory\n').encode()
        reader=AndroidReader(device)
        self.assertEqual(reader.poll()['bytes_read'],0)
        self.assertEqual(reader.pending,b'')
        device.data=b'new data\n'
        self.assertEqual(reader.poll()['bytes_read'],len(device.data))

    def test_log_cap_check_reads_current_session_and_rejects_known_truncation(self):
        device=Mock()
        reader=AndroidReader(device)
        reader.path='/logs/Hearthstone_session/Power.log'
        device.command.return_value=b'Truncating log, which has reached the size limit of 10000KB'
        with self.assertRaisesRegex(ValueError,'上限'):
            reader.check_logging_health()
        device.command.assert_called_once_with('exec-out','tail','-c','4096','/logs/Hearthstone_session/Hearthstone.log')
        device.command.return_value=b'ordinary log line'
        reader.check_logging_health()

    def test_log_health_does_not_hide_transport_errors(self):
        device=Mock()
        reader=AndroidReader(device)
        with self.assertRaises(ValueError):reader.check_logging_health()
        reader.path='/logs/session/Power.log'
        device.command.side_effect=RuntimeError('device offline')
        with self.assertRaisesRegex(RuntimeError,'offline'):reader.check_logging_health()
        device.command.side_effect=RuntimeError('No such file or directory')
        reader.check_logging_health()

    def test_incremental_utf8_lines_and_replaced_log(self):
        device=Device()
        with patch('android_reader.State') as factory:
            factory.return_value.snapshot.return_value={}
            reader=AndroidReader(device)
            device.data=('x'*80+'\n龍').encode()[:-1]
            reader.poll()
            parser=reader.state
            parser.feed.assert_called_once_with('x'*80)
            device.data=('x'*80+'\n龍戰\n').encode()
            snapshot=reader.poll()
            parser.feed.assert_called_with('龍戰')
            self.assertEqual(snapshot['bytes_read'],len(device.data))
            device.data=b'new game\n'
            reader.poll()
            self.assertEqual(factory.call_count,3)
            reader.state.feed.assert_called_with('new game')
            self.assertEqual(reader.offset,len(device.data))

    def test_new_empty_session_drops_previous_bytes(self):
        device=Device();device.data=b'old\n'
        reader=AndroidReader(device)
        reader.poll()
        device.session='Hearthstone_2026_09_27_14_00_00'
        device.data=b''
        snapshot=reader.poll()
        self.assertEqual(snapshot['bytes_read'],0)
        self.assertEqual(snapshot['players'],[])


if __name__=='__main__':
    unittest.main()
