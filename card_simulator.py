"""Explicit deterministic card adapters. Unmodelled effects stop a rollout."""
import copy
from dataclasses import dataclass
from strategy import sides, entity_map, card_cost, number, hp, text_of, vanilla, get_actions
from turn_search import combat_inert, COMBAT_INERT

PLAIN_BODIES={'CORE_NEW1_023':'飄渺',
              'END_033':'飄渺若你手中有其他龍類，消耗減少(3)'}


@dataclass
class Transition:
    state: dict | None
    boundary: str | None = None


def simulate_card(state,action,cards):
    """Consume an already legal action; never infer random cards or deck order."""
    own,enemy=sides(state)
    if state.get('enchantments') or any(p.get('secret_count',0) or p.get('weapons') for p in (own,enemy)):
        return Transition(None,'秘密、武器或附魔效果尚未模擬')
    if any(not combat_inert(e,cards) for p in (own,enemy) for e in p['board']):
        return Transition(None,'場上有尚未建模的觸發效果')
    entities=entity_map(state)
    source=entities.get(action.get('entity_id'))
    if source is None:return Transition(None,'來源不在目前局面')
    if source['tags'].get('CONTROLLER')!=own['controller']:
        return Transition(None,'不是我方來源')
    if action['kind']=='hero_power' and number(source,'EXHAUSTED'):
        return Transition(None,'英雄能力已耗用')
    definition=cards.get(source.get('card_id'),{})
    text=''.join(text_of(source,cards).split())
    adapter=None
    if action['kind']=='play':
        if source['tags'].get('ZONE')!='HAND':return Transition(None,'卡牌已不在手中')
        if source['tags'].get('CARDTYPE')=='MINION':
            if len(own['board'])>=7:return Transition(None,'場面已滿')
            if source['card_id']=='TLC_600' and text==COMBAT_INERT['TLC_600']:
                adapter='damage5_armor5'
            elif (vanilla(source,cards) or PLAIN_BODIES.get(source['card_id'])==text) and not action.get('target_id'):
                adapter='minion'
        elif source['card_id']=='GAME_005' and text=='本回合獲得1顆法力水晶':
            adapter='coin'
    elif action['kind']=='hero_power' and text in ('獲得2點護甲值','英雄能力獲得$d2點護甲值') and not action.get('target_id'):
        adapter='armor2'
    if adapter is None:
        return Transition(None,'未建模、隨機或需要選牌的卡牌效果')
    cost=card_cost(source,cards)
    if cost is None or own.get('mana') is None or cost>own['mana']:
        return Transition(None,'費用未知或法力不足')
    if adapter=='damage5_armor5':
        target=entities.get(action.get('target_id'))
        if target is None or target['tags'].get('ZONE')!='PLAY' or target['tags'].get('CARDTYPE') not in ('MINION','HERO'):
            return Transition(None,'戰吼目標已失效')
        if any(number(target,t) for t in ('IMMUNE','CANT_BE_DAMAGED','DORMANT')):
            return Transition(None,'目標有尚未建模的保護效果')
    after=copy.deepcopy(state)
    me,foe=sides(after)
    src=entity_map(after)[source['id']]
    me['mana']-=cost
    if adapter=='armor2':
        src['tags']['EXHAUSTED']='1'
        hero=me['heroes'][0]
        hero['tags']['ARMOR']=str(number(hero,'ARMOR')+2)
    elif adapter=='coin':
        me['hand']=[e for e in me['hand'] if e['id']!=src['id']]
        me['mana']=min(10,me['mana']+1)
    else:
        me['hand']=[e for e in me['hand'] if e['id']!=src['id']]
        src['tags'].update(ZONE='PLAY',EXHAUSTED='1',NUM_TURNS_IN_PLAY='0',NUM_ATTACKS_THIS_TURN='0')
        for tag,key in [('ATK','attack'),('HEALTH','health')]:
            if tag not in src['tags'] and key in definition:src['tags'][tag]=str(definition[key])
        if not all(tag in src['tags'] for tag in ('ATK','HEALTH')):
            return Transition(None,'手下數值未知')
        me['board'].append(src)
        if adapter=='damage5_armor5':
            target=entity_map(after)[action['target_id']]
            if number(target,'DIVINE_SHIELD'):
                target['tags']['DIVINE_SHIELD']='0'
            else:
                absorbed=min(5,number(target,'ARMOR'))
                target['tags']['ARMOR']=str(number(target,'ARMOR')-absorbed)
                target['tags']['DAMAGE']=str(number(target,'DAMAGE')+5-absorbed)
            hero=me['heroes'][0]
            hero['tags']['ARMOR']=str(number(hero,'ARMOR')+5)
            for player in (me,foe):player['board']=[e for e in player['board'] if hp(e)>0]
    for player in (me,foe):
        for zone in ('hand','board'):
            for index,e in enumerate(player[zone],1):e['tags']['ZONE_POSITION']=str(index)
    # No invented legal-option packet: a search layer must regenerate its own moves.
    after['options']=[]
    after['options_fresh']=False
    return Transition(after)


def card_plans(state,cards,limit=2):
    actions,_=get_actions(state,cards)
    results=[]
    for action in actions.values():
        if action['kind'] not in ('play','hero_power'):continue
        transition=simulate_card(state,action,cards)
        if transition.state is None:continue
        own,enemy=sides(transition.state)
        health=hp(enemy['heroes'][0])+number(enemy['heroes'][0],'ARMOR')
        friendly=','.join(f"{number(e,'ATK')}/{hp(e)}" for e in own['board']) or '空'
        hostile=','.join(f"{number(e,'ATK')}/{hp(e)}" for e in enemy['board']) or '空'
        score=sum(number(e,'ATK')*1.3+hp(e)*.5 for e in own['board'])-sum(number(e,'ATK')*1.3+hp(e)*.5 for e in enemy['board'])-health*.8+number(own['heroes'][0],'ARMOR')*.2
        results.append(dict(action=action,sequence=[action['key']],score=score,
            summary=f"{action['description']}：敵英雄 {health}；我方 {friendly}；敵方 {hostile}；剩餘法力 {own['mana']}",
            lethal=health<=0,scope='single_card_effect',complete_turn=False))
    return sorted(results,key=lambda p:p['score'],reverse=True)[:limit]
