"""Read Android Power.log into a separate, device-bound state snapshot."""
import argparse
import copy
import json
from pathlib import Path
import re
import time

from android_device import AndroidDevice
from reader import State
from snapshot_io import publish_text

LOG_ROOT = '/sdcard/Android/data/com.blizzard.wtcg.hearthstone/files/Logs'


class AndroidReader:
    def __init__(self, device):
        self.device = device
        self.path = None
        self.offset = 0
        self.tail = b''
        self.pending = b''
        self.state = State()
        self.last_data = 0

    def _read_log(self, command, path):
        try:
            data=self.device.command('exec-out',*command,path)
        except RuntimeError as exc:
            if 'No such file or directory' in str(exc):
                return b''
            raise
        # Some Android adb exec-out versions return shell errors on stdout
        # with exit code zero. Never feed those bytes into the game parser.
        if data.startswith((command[0]+':').encode()):
            message=data.decode('utf-8',errors='replace')
            if 'No such file or directory' in message:
                return b''
            raise RuntimeError(message.strip())
        return data

    def check_logging_health(self):
        if not self.path:
            raise ValueError('尚未取得 Android 日誌來源，請先連線讀取局面')
        main_log=self.path.rsplit('/',1)[0]+'/Hearthstone.log'
        tail=self._read_log(('tail','-c','4096'),main_log)
        if b'Truncating log, which has reached the size limit' in tail:
            raise ValueError('爐石日誌已達檔案上限，不能開始新對局；請在目前對局結束後修復日誌設定並重啟遊戲。')

    def poll(self):
        names = self.device.command('shell', 'ls', LOG_ROOT).decode().splitlines()
        sessions = sorted(n.strip() for n in names if re.fullmatch(r'Hearthstone_[0-9_]+', n.strip()))
        if not sessions:
            raise ValueError('Android Hearthstone has no log session')
        path = LOG_ROOT + '/' + sessions[-1] + '/Power.log'
        if path != self.path:
            self.state=State()
            self.offset=0
            self.tail=self.pending=b''
            self.path=path
        command=('tail','-c',f'+{self.offset-len(self.tail)+1}') if self.offset else ('cat',)
        data=self._read_log(command,path)
        if self.offset and not data.startswith(self.tail):
            self.state = State()
            self.offset=0
            self.tail=self.pending=b''
            data=self._read_log(('cat',),path)
        added=data[len(self.tail):]
        self.offset+=len(added)
        self.tail=(self.tail+added)[-64:]
        if added:
            self.last_data = time.monotonic()
            lines = (self.pending + added).split(b'\n')
            self.pending = lines.pop()
            for line in lines:
                self.state.feed(line.decode('utf-8', errors='replace'))
        elif not self.pending and time.monotonic() - self.last_data >= .2:
            self.state.feed('')
        snapshot = self.state.snapshot()
        snapshot.update(source=path, device_serial=self.device.serial,
                        platform='android', bytes_read=self.offset, observed_at=time.time())
        if snapshot.get('game_serial') is not None:
            snapshot['game_serial'] = f'{self.device.serial}:{sessions[-1]}:{snapshot["game_serial"]}'
        return copy.deepcopy(snapshot)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--adb', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--output', type=Path, default=Path(__file__).parent/'android-state.json')
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    reader = AndroidReader(AndroidDevice(args.adb, args.serial))
    reader.device.connect()
    while True:
        snapshot = reader.poll()
        if not publish_text(args.output, json.dumps(snapshot, ensure_ascii=False, indent=2)):
            raise RuntimeError('Could not publish Android state')
        if not args.watch:
            print(json.dumps({'output': str(args.output), 'game_state': snapshot.get('game_state'),
                              'bytes_read': snapshot['bytes_read']}))
            return
        time.sleep(.2)


if __name__ == '__main__':
    main()
