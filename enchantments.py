"""Classify observed enchantments before forecasting visible game effects."""
from strategy import entity_map,number,text_of


ORIGIN_TEXT={
    'JAIL_430':'你的起始生命值改為40。你的牌堆有20張牌，加上敵方牌堆的20張複製品。戰吼：抽牌，直到塞滿你的手牌',
    'CORE_REV_990':'對一個手下造成1點傷害並賦予它+2攻擊力',
    'EDR_100t8':'+4/+5將這張牌放到你牌堆的最上方',
}
STATIC_EFFECTS={
    'JAIL_430e1':('複製品提示','JAIL_430','marker'),
    'TLC_835e':('生命值提高','JAIL_430','hero_health'),
    'REV_990e':('+2攻擊力','CORE_REV_990','attack'),
    'EDR_100t8e1':('+4/+5','EDR_100t8','stats'),
}


def enchantment_boundary(state,cards):
    entities=entity_map(state)
    for enchantment in state.get('enchantments',[]):
        tags=enchantment.get('tags',{})
        if tags.get('ZONE') in ('GRAVEYARD','REMOVEDFROMGAME'):continue
        cid=enchantment.get('card_id')
        if tags.get('ZONE') not in ('PLAY','SETASIDE') or number(enchantment,'ATTACHED')<=0:
            return f'附魔區域或附著目標未知 {cid}'
        expected=STATIC_EFFECTS.get(cid)
        if expected is None:return f'未建模附魔 {cid}'
        text,origin,kind=expected
        definition=cards.get(origin,{})
        if (''.join(text_of(enchantment,cards).split())!=text
                or ''.join(text_of(dict(card_id=origin),cards).split())!=ORIGIN_TEXT[origin]
                or definition.get('dbfId') is None
                or str(tags.get('CREATOR_DBID'))!=str(definition['dbfId'])):
            return f'附魔卡文或來源未核對 {cid}'
        target=entities.get(number(enchantment,'ATTACHED',-1))
        if kind=='marker':continue
        if kind=='hero_health':
            if (target is None or target['tags'].get('CARDTYPE')!='HERO'
                    or number(enchantment,'TAG_SCRIPT_DATA_NUM_1')<=0
                    or number(target,'HEALTH')<number(enchantment,'TAG_SCRIPT_DATA_NUM_1')):
                return '英雄生命值附魔尚未反映於可見數值'
        elif target is not None:
            required=('ATK','HEALTH') if kind=='stats' else ('ATK',)
            if target['tags'].get('CARDTYPE')!='MINION' or any(k not in target['tags'] for k in required):
                return f'靜態附魔數值未知 {cid}'
        # An absent target is outside the visible simulated zones. These exact
        # stat modifiers carry no triggers; drawing/revealing that card requires
        # a new real observation, not an invented entity in the rollout.
    return None
