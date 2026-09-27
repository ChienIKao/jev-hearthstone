"""Human-readable inspection of the observed friendly cards, without inference."""
from strategy import card_cost, name_of, text_of
from choices import pending_choice
from datetime import datetime


def observed_stats(entity):
    tags=entity.get('tags',{})
    parts=[]
    for key,label in [('ATK','攻擊'),('HEALTH','生命上限'),('DAMAGE','已受傷害'),
                      ('ARMOR','護甲'),('DURABILITY','耐久上限')]:
        if key in tags:parts.append(f'{label} {tags[key]}')
    for key,label in [('TAUNT','嘲諷'),('DIVINE_SHIELD','聖盾'),('SILENCED','沉默'),
                      ('FROZEN','凍結'),('EXHAUSTED','已耗用'),('STEALTH','潛行'),
                      ('IMMUNE','免疫'),('POISONOUS','致命劇毒'),('LIFESTEAL','吸血')]:
        if tags.get(key) not in (None,'0',0):parts.append(label)
    return ' · '.join(parts)


def describe_observation(state, cards):
    own=next((p for p in state.get('players',[]) if p['controller']==state.get('local_controller')),None)
    if own is None:
        return '尚未辨識我方玩家。請連線並更新畫面。'
    status='已結束對局的最後紀錄' if state.get('game_state')=='COMPLETE' else '目前讀取的局面'
    lines=[f"{status}\n回合 {state.get('turn')} · {state.get('game_state')}\n原始卡文來自資料庫；數值及狀態來自日誌。附魔生效狀態仍需判讀。"]
    observed_at=state.get('observed_at')
    if isinstance(observed_at,(int,float)):
        lines.insert(1,'快照讀取時間：'+datetime.fromtimestamp(observed_at).strftime('%Y-%m-%d %H:%M:%S'))
    lines.insert(2,'此欄為快照；按「更新預覽」重新讀取。')
    enchantments=state.get('enchantments',[])
    groups=[]
    packet=pending_choice(state) if state.get('game_state')=='RUNNING' else None
    if packet:
        complete='清單完整' if packet.get('complete') else '清單仍在更新'
        minimum,maximum=packet.get('count_min','?'),packet.get('count_max','?')
        groups.append((f'待選候選 · 選 {minimum}–{maximum} 張 · {complete}',packet.get('cards',[])))
    groups.extend((title,own.get(zone,[])) for zone,title in [
        ('hand','我方手牌'),('board','我方場面'),('heroes','我方英雄'),('weapons','武器'),('hero_powers','英雄能力')])
    for title,entities in groups:
        lines.append(f'\n{title} · {len(entities)}')
        for index,e in enumerate(entities,1):
            cost=card_cost(e,cards)
            lines.append(f"{index}. {name_of(e,cards)} · 費用 {cost if cost is not None else '未知'}")
            lines.append(f"   {e.get('card_id') or '卡牌 ID 未知'} · 實體 {e['id']}")
            stats=observed_stats(e)
            if stats:lines.append('   '+stats)
            definition=cards.get(e.get('card_id'))
            lines.append('   '+(text_of(e,cards) or ('無原始效果文字' if definition is not None else '資料庫未收錄，效果未知')))
            for effect in enchantments:
                if str(effect.get('tags',{}).get('ATTACHED'))!=str(e['id']):
                    continue
                tags=effect['tags']
                lines.append(f"   附魔：{name_of(effect,cards)} [{tags.get('ZONE','區域未知')}]（生效狀態待判讀）")
                lines.append('     '+(text_of(effect,cards) or '效果文字未知'))
                params={k:v for k,v in tags.items() if k.startswith('TAG_SCRIPT_DATA')}
                if params:lines.append('     '+str(params))
    return '\n'.join(lines)
