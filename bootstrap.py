"""Download the card database and multilingual checkpoint for offline runtime."""
import argparse
import json
import os
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parent
CARD_URL='https://api.hearthstonejson.com/v1/253216/zhTW/cards.json'


def prepare(offline=False):
    os.environ['HF_HOME']=str(ROOT/'.cache'/'huggingface')
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    os.environ['HF_HUB_OFFLINE']='1' if offline else '0'
    target=ROOT/'data'/'cards.zhTW.json'
    if not target.exists():
        if offline:raise FileNotFoundError('Card database missing; run setup.cmd online first.')
        print('Downloading Traditional Chinese card database...',flush=True)
        with urlopen(CARD_URL,timeout=90) as response:raw=response.read()
        cards=json.loads(raw)
        if not isinstance(cards,list) or not cards or not all(isinstance(c,dict) and 'id' in c for c in cards):
            raise ValueError('Invalid card database response')
        target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_suffix('.download')
        temporary.write_bytes(raw);temporary.replace(target)
    else:
        cards=json.loads(target.read_text(encoding='utf-8'))
        if not isinstance(cards,list) or not cards:raise ValueError('Invalid local card database')
    from huggingface_hub import snapshot_download
    print('Checking multilingual model cache...' if offline else 'Downloading multilingual model (first setup may take several minutes)...',flush=True)
    snapshot_download('convaiinnovations/laya',allow_patterns=['multilingual/*'],local_files_only=offline)
    from laya import Router
    router=Router(device='cpu');router.load('multilingual')
    print('Ready: card database and multilingual model loaded successfully.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--offline',action='store_true',help='Verify existing local files without downloading')
    prepare(parser.parse_args().offline)
