"""Preserve and update Android Hearthstone's session logging configuration."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import tempfile

FILES='/sdcard/Android/data/com.blizzard.wtcg.hearthstone/files'


def unlimited_log_config(original):
    newline='\r\n' if '\r\n' in original else '\n'
    lines=original.splitlines()
    sections=[i for i,line in enumerate(lines) if re.fullmatch(r'\s*\[Log\]\s*',line,re.I)]
    if len(sections)>1:
        raise ValueError('client.config 有重複的 Log 區段，請先人工整理')
    if not sections:
        if lines and lines[-1].strip():lines.append('')
        lines.extend(['[Log]','FileSizeLimit.Int=-1'])
    else:
        start=sections[0]+1
        end=next((i for i in range(start,len(lines)) if re.match(r'\s*\[',lines[i])),len(lines))
        keys=[i for i in range(start,end) if re.match(r'\s*FileSizeLimit\.Int\s*=',lines[i],re.I)]
        if keys:
            lines[keys[0]]='FileSizeLimit.Int=-1'
            for index in reversed(keys[1:]):del lines[index]
        else:lines.insert(end,'FileSizeLimit.Int=-1')
    return newline.join(lines)+newline


def configure_logging(device, backup_directory):
    from laya_hearthstone.device_lease import device_lease
    with device_lease(device.serial):
        path=FILES+'/client.config'
        existed=True
        try:
            # Check existence with shell exit status, then preserve raw newlines.
            device.command('shell','ls',path)
            original=device.command('exec-out','cat',path)
            if original.startswith(('cat: '+path+':').encode()):
                raise RuntimeError(original.decode(errors='replace').strip())
        except RuntimeError as exc:
            if 'No such file or directory' not in str(exc):raise
            original=b'';existed=False
        updated=unlimited_log_config(original.decode('utf-8-sig')).encode('utf-8')
        if original==updated:
            return dict(changed=False,restart_required=True)
        backup=Path(backup_directory)/('client-config-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        backup.parent.mkdir(parents=True,exist_ok=True)
        backup.write_text(json.dumps(dict(serial=device.serial,path=path,existed=existed,
                                         original=original.decode('utf-8-sig')),ensure_ascii=False,indent=2),encoding='utf-8')
        with tempfile.TemporaryDirectory() as folder:
            local=Path(folder)/'client.config'
            local.write_bytes(updated)
            remote=FILES+'/client.config.assistant-tmp'
            device.command('push',str(local),remote)
            if device.command('exec-out','cat',remote)!=updated:
                raise ValueError('日誌設定傳輸校驗失敗，原設定未變更')
            device.command('shell','mv',remote,path)
        return dict(changed=True,restart_required=True,backup=str(backup))
