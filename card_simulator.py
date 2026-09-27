"""Explicit deterministic card adapters. Unmodelled effects stop a rollout."""
import copy
import time
from dataclasses import dataclass
from strategy import sides, entity_map, card_cost, number, hp, text_of, vanilla, get_actions, name_of
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
    def holds_dragon(hand,exclude):
        def races(e):
            card=cards.get(e.get('card_id'),{})
            return card.get('races') or [card.get('race')]
        return any(e['id']!=exclude and set(races(e)) & {'DRAGON','ALL'} for e in hand)
    for entity in me['hand']:
        if entity.get('card_id')!='END_033':continue
        base=cards.get('END_033',{}).get('cost')
        if not isinstance(base,int):return Transition(None,'龍族減費基礎費用未知')
        previous=max(0,base-3) if holds_dragon(own['hand'],entity['id']) else base
        if card_cost(entity,cards)!=previous:
            return Transition(None,'龍族手牌另有未建模費用修正')
        entity['tags']['COST']=str(max(0,base-3) if holds_dragon(me['hand'],entity['id']) else base)
    # No invented legal-option packet: a search layer must regenerate its own moves.
    after['options']=[]
    after['options_fresh']=False
    return Transition(after)


def rollout_actions(state,cards):
    """Internal proposals only; simulate_card validates each supported transition."""
    own,enemy=sides(state)
    for zone,kind in [('hand','play'),('hero_powers','hero_power')]:
        for entity in own.get(zone,[]):
            targets=[None]
            if entity.get('card_id')=='TLC_600':
                targets=[e['id'] for p in (own,enemy) for e in p['board']+p['heroes']]
            for target in targets:
                action=dict(key=f"sim:{entity['id']}:{target}",kind=kind,entity_id=entity['id'],
                            description=name_of(entity,cards),cost=card_cost(entity,cards))
                if target is not None:action['target_id']=target
                yield action


def card_plans(state,cards,limit=2,max_depth=3,beam_width=16,time_budget=.04):
    actions,_=get_actions(state,cards)
    results=[];frontier=[]
    deadline=time.monotonic()+time_budget
    for action in actions.values():
        if action['kind'] not in ('play','hero_power'):continue
        transition=simulate_card(state,action,cards)
        if transition.state is None:continue
        frontier.append((transition.state,action,[action['description']]))
    def evaluate(snapshot,action,sequence):
        own,enemy=sides(snapshot)
        health=hp(enemy['heroes'][0])+number(enemy['heroes'][0],'ARMOR')
        friendly=','.join(f"{number(e,'ATK')}/{hp(e)}" for e in own['board']) or '空'
        hostile=','.join(f"{number(e,'ATK')}/{hp(e)}" for e in enemy['board']) or '空'
        score=sum(number(e,'ATK')*1.3+hp(e)*.5 for e in own['board'])-sum(number(e,'ATK')*1.3+hp(e)*.5 for e in enemy['board'])-health*.8+number(own['heroes'][0],'ARMOR')*.2
        if hp(own['heroes'][0])<=0:score=-100000
        elif health<=0:score=100000
        return dict(action=action,sequence=sequence,score=score,
            summary=f"{len(sequence)}步：敵英雄 {health}；我方 {friendly}；敵方 {hostile}；剩餘法力 {own['mana']}",
            lethal=health<=0 and hp(own['heroes'][0])>0,scope='known_card_prefix',complete_turn=False)
    for depth in range(max_depth):
        frontier=sorted(frontier,key=lambda n:evaluate(*n)['score'],reverse=True)[:beam_width]
        children=[]
        for snapshot,first,sequence in frontier:
            outcome=evaluate(snapshot,first,sequence);results.append(outcome)
            if outcome['lethal'] or outcome['score']==-100000 or depth+1==max_depth:continue
            for action in rollout_actions(snapshot,cards):
                if time.monotonic()>=deadline:break
                transition=simulate_card(snapshot,action,cards)
                if transition.state is not None:
                    children.append((transition.state,first,sequence+[action['description']]))
        if not children:break
        frontier=children
    seen=set();selected=[]
    for plan in sorted(results,key=lambda p:p['score'],reverse=True):
        if plan['action']['key'] in seen:continue
        seen.add(plan['action']['key']);selected.append(plan)
        if len(selected)>=limit:break
    return selected
