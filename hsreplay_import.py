"""Import the visible text of an HSReplay deck's public mulligan table."""
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit
import copy


def correct_mulligan(reference, opening, cards, chosen, actions):
    """Correct only extreme, inexpensive keeps and expensive low-keep cards."""
    if not reference or not reference.get('guard_mulligan') or (reference.get('sample_size') or 0)<1000:
        return chosen
    rows={r['name']:r for r in reference['cards']}
    replaced=set(chosen['replace_ids'])
    for entity in opening:
        card=cards.get(entity['card_id'],{})
        row=rows.get(card.get('name'))
        cost=card.get('cost')
        if row is None or not isinstance(cost,(int,float)):
            continue
        if cost<=2 and row['keep_percentage']>=85:
            replaced.discard(entity['id'])
        elif cost>=5 and row['keep_percentage']<=5:
            replaced.add(entity['id'])
    return next((a for a in actions.values() if set(a['replace_ids'])==replaced),chosen)


def validate_reference(value):
    def require(condition):
        if not condition:
            raise ValueError()
    try:
        source=urlsplit(value['source_url'])
        require(source.scheme=='https' and source.hostname=='hsreplay.net')
        require(not source.username and not source.password)
        require(re.fullmatch(r'/(?:zh-hant/)?decks/[A-Za-z0-9]+/?',source.path))
        require(value['mode'] in ('standard','wild'))
        require(isinstance(value.get('guard_mulligan',False),bool))
        datetime.fromisoformat(value['imported_at'])
        require(all(isinstance(value[k],str) and 0<len(value[k])<=200 for k in ('rank_range','time_range')))
        require(0<len(value['cards'])<=60)
        require(sum(r['count'] for r in value['cards']) in (30,40))
        for row in value['cards']:
            require(isinstance(row['name'],str) and 0<len(row['name'])<=100)
            require(isinstance(row['count'],int) and 1<=row['count']<=40)
            for key in ('mulligan_winrate','keep_percentage','drawn_winrate','played_winrate','turns_held'):
                require(isinstance(row[key],(int,float)) and 0<=row[key]<=100)
    except (AssertionError,KeyError,ValueError,TypeError):
        raise ValueError('HSReplay 參考資料不完整或格式錯誤') from None
    return copy.deepcopy(value)


def parse_deck_page(text, url, rank_range, time_range, mode, cards):
    source = urlsplit(url.strip())
    if (source.scheme != 'https' or source.hostname != 'hsreplay.net'
            or source.username or source.password
            or not re.fullmatch(r'/(?:zh-hant/)?decks/[A-Za-z0-9]+/?', source.path)):
        raise ValueError('請填寫 HSReplay 單一牌組頁面的 https 網址')
    if mode not in ('standard', 'wild') or not rank_range.strip() or not time_range.strip():
        raise ValueError('請填寫網站實際選取的模式、分段與時間範圍')
    if len(text) > 200_000:
        raise ValueError('貼上的內容過長，請只複製牌組頁面')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    try:
        start = lines.index('Avg. Turns Held')
    except ValueError:
        raise ValueError('找不到留牌統計表，請切換到單一牌組的「留牌指南」再複製整頁文字') from None
    pct = re.compile(r'[▲▼]?([0-9]+(?:\.[0-9]+)?)%')
    first = next((i for i in range(start+1, len(lines)) if pct.fullmatch(lines[i])), None)
    if first is None:
        raise ValueError('頁面沒有可讀取的留牌數據')
    # The site's table copies the card column first, then five statistics per row.
    header = lines[start+1:first]
    rows = []
    for i in range(len(header)-2):
        if header[i].isdigit() and (header[i+1].isdigit() or header[i+1]=='★'):
            if not header[i+2].isdigit() and header[i+2]!='★':
                rows.append(dict(name=header[i+2], cost=int(header[i]),
                                 count=1 if header[i+1]=='★' else int(header[i+1])))
    if not rows or len(rows)>60 or sum(r['count'] for r in rows) not in (30, 40):
        raise ValueError('牌表不完整；請複製整頁，包括所有卡牌與數據')
    for index, row in enumerate(rows):
        values=lines[first+index*5:first+(index+1)*5]
        if len(values)!=5 or not all(pct.fullmatch(v) for v in values[:4]):
            raise ValueError('留牌統計列數不完整，未匯入任何資料')
        numbers=[float(pct.fullmatch(v)[1]) for v in values[:4]]
        if any(v<0 or v>100 for v in numbers):
            raise ValueError('統計百分比超出範圍')
        row.update(zip(('mulligan_winrate','keep_percentage','drawn_winrate','played_winrate'),numbers))
        try:
            row['turns_held']=float(values[4])
        except ValueError:
            raise ValueError('平均持牌回合格式不正確') from None
        if not 0<=row['turns_held']<=100:
            raise ValueError('平均持牌回合超出範圍')
    sample=re.search(r'樣本數\s*([\d,]+)\s*場',text)
    known={c.get('name') for c in cards.values()}
    return dict(source_url=url.strip(), imported_at=datetime.now(timezone.utc).isoformat(),
                rank_range=rank_range.strip(), time_range=time_range.strip(), mode=mode,
                sample_size=int(sample[1].replace(',','')) if sample else None,
                cards=rows, unknown_cards=[r['name'] for r in rows if r['name'] not in known],
                scope='reference_deck', method='copied_public_page')


def decision_reference(reference, names):
    """Keep the model's context small and relevant to the current visible cards."""
    if not reference:
        return None
    rows=[r for r in reference['cards'] if r['name'] in names]
    if not rows:
        return None
    return dict(source_url=reference['source_url'], imported_at=reference['imported_at'],
                rank_range=reference['rank_range'], time_range=reference['time_range'],
                cards=[{k:r[k] for k in ('name','mulligan_winrate','keep_percentage')} for r in rows],
                interpretation='參考牌表的觀察統計，未確認與目前牌組完全相同；留牌率不是必留指令，勝率不是因果效果。依先後手、費用曲線與當前局面判斷。')


def parse_meta_page(text, rank_range, time_range):
    if not rank_range.strip() or not time_range.strip():
        raise ValueError('請填寫網站選取的分段、伺服器與時間範圍')
    if len(text)>200_000:
        raise ValueError('貼上的內容過長')
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    try:start=lines.index('Core Cards')+1
    except ValueError:raise ValueError('找不到環境強度列表，請複製 HSReplay 環境榜整頁文字') from None
    rows=[];tier=None;i=start
    while i<len(lines):
        if lines[i] in ('A','B','C','D'):
            tier=lines[i];i+=1;continue
        if lines[i]=='HSReplay.net':break
        if i+3>=len(lines) or not tier or lines[i+3]!='View Stats':
            raise ValueError('環境榜內容不完整或格式已變更')
        try:
            if not re.fullmatch(r'\d+(?:\.\d+)?%',lines[i+1]):raise ValueError()
            winrate=float(lines[i+1][:-1]);matches=int(lines[i+2].replace(',',''))
            if not 0<=winrate<=100 or matches<1:raise ValueError()
        except ValueError:raise ValueError('環境榜數字格式錯誤') from None
        rows.append(dict(name=lines[i],tier=tier,winrate=winrate,matches=matches));i+=4
    if not rows:raise ValueError('環境榜尚未載入')
    return dict(source_url='https://hsreplay.net/zh-hant/meta/',
                imported_at=datetime.now(timezone.utc).isoformat(),rank_range=rank_range.strip(),
                time_range=time_range.strip(),rows=rows,method='copied_public_page')
