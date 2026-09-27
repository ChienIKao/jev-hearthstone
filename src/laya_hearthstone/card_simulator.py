"""Explicit deterministic card adapters. Unmodelled effects stop a rollout."""
import copy
import time
from dataclasses import dataclass
from laya_hearthstone.strategy import sides, entity_map, card_cost, number, hp, text_of, vanilla, get_actions, name_of
from laya_hearthstone.turn_search import combat_inert, COMBAT_INERT, passive_weapons_known
from laya_hearthstone.enchantments import enchantment_boundary

PLAIN_BODIES={'CORE_NEW1_023':'飄渺',
              'TIME_056':'生命竊取聖盾術',
              'END_033':'飄渺若你手中有其他龍類，消耗減少(3)'}


@dataclass
class Transition:
    state: dict | None
    boundary: str | None = None


def simulate_card(state,action,cards):
    """Consume an already legal action; never infer random cards or deck order."""
    own,enemy=sides(state)
    if enchantment_boundary(state,cards) or any(p.get('secret_count',0) for p in (own,enemy)) or not passive_weapons_known(state,cards):
        return Transition(None,'秘密、武器或附魔效果尚未模擬')
    if any(not combat_inert(e,cards) for p in (own,enemy) for e in p['board']):
        return Transition(None,'場上有尚未建模的觸發效果')
    entities=entity_map(state)
    source=entities.get(action.get('entity_id'))
    if source is None:return Transition(None,'來源不在目前局面')
    if source['tags'].get('CONTROLLER')!=own['controller']:
        return Transition(None,'不是我方來源')
    if action['kind']=='attack':
        return simulate_attack(state,action)
    if action['kind']=='hero_power' and number(source,'EXHAUSTED'):
        return Transition(None,'英雄能力已耗用')
    definition=cards.get(source.get('card_id'),{})
    text=''.join(text_of(source,cards).split())
    adapter=None
    if action['kind']=='play':
        if any(e.get('card_id')=='TIME_063' and number(e,'DORMANT') and not number(e,'SILENCED') for e in own['board']):
            return Transition(None,'出牌可能使休眠龍提早甦醒')
        if source['tags'].get('ZONE')!='HAND':return Transition(None,'卡牌已不在手中')
        if source['tags'].get('CARDTYPE')=='MINION':
            if len(own['board'])>=7:return Transition(None,'場面已滿')
            if source['card_id']=='TLC_600' and text==COMBAT_INERT['TLC_600']:
                adapter='damage5_armor5'
            elif source['card_id']=='EDR_492' and text==COMBAT_INERT['EDR_492'] and not action.get('target_id'):
                token=cards.get('EDR_492t',{})
                if ''.join(text_of({'card_id':'EDR_492t'},cards).split())!='衝刺' or token.get('attack')!=1 or token.get('health')!=1:
                    return Transition(None,'小鴨子卡牌資料未知或已改動')
                adapter='ducklings'
            elif (vanilla(source,cards) or PLAIN_BODIES.get(source['card_id'])==text) and not action.get('target_id'):
                if source['card_id']=='TIME_056' and not all(number(source,t) for t in ('LIFESTEAL','DIVINE_SHIELD')):
                    return Transition(None,'青銅幼龍關鍵字狀態尚未確認')
                adapter='minion'
        elif source['card_id']=='GAME_005' and text=='本回合獲得1顆法力水晶':
            adapter='coin'
        elif source['card_id']=='CORE_REV_990' and text==COMBAT_INERT['CORE_REV_990'] and len(own['board'])<7:
            adapter='location_body'
    elif action['kind']=='location' and source.get('card_id')=='CORE_REV_990' and text==COMBAT_INERT['CORE_REV_990']:
        if source not in own['board'] or number(source,'EXHAUSTED') or number(source,'LOCATION_ACTION_COOLDOWN') or hp(source)<=0:
            return Transition(None,'地標不可使用')
        target=entities.get(action.get('target_id'))
        if target is None or target not in own['board']+enemy['board'] or target['tags'].get('CARDTYPE')!='MINION':
            return Transition(None,'地標目標已失效')
        if any(number(target,t) for t in ('IMMUNE','CANT_BE_DAMAGED','DORMANT','DEATHRATTLE','REBORN')):
            return Transition(None,'地標目標有未建模效果')
        if number(target,'STEALTH') and target['tags'].get('CONTROLLER')!=own['controller']:
            return Transition(None,'敵方目標潛行')
        adapter='damage1_attack2'
    elif action['kind']=='hero_power' and text in ('獲得2點護甲值','英雄能力獲得$d2點護甲值') and not action.get('target_id'):
        adapter='armor2'
    if adapter is None:
        return Transition(None,'未建模、隨機或需要選牌的卡牌效果')
    cost=0 if adapter=='damage1_attack2' else card_cost(source,cards)
    if cost is None or own.get('mana') is None or cost>own['mana']:
        return Transition(None,'費用未知或法力不足')
    if adapter=='damage5_armor5':
        target=entities.get(action.get('target_id'))
        if target is None or target['tags'].get('ZONE')!='PLAY' or target['tags'].get('CARDTYPE') not in ('MINION','HERO'):
            return Transition(None,'戰吼目標已失效')
        if any(number(target,t) for t in ('IMMUNE','CANT_BE_DAMAGED','DORMANT')) or (number(target,'STEALTH') and target['tags'].get('CONTROLLER')!=own['controller']):
            return Transition(None,'目標有尚未建模的保護效果')
    after=copy.deepcopy(state)
    me,foe=sides(after)
    src=entity_map(after)[source['id']]
    me['mana']-=cost
    if adapter=='damage1_attack2':
        target=entity_map(after)[action['target_id']]
        if number(target,'DIVINE_SHIELD'):target['tags']['DIVINE_SHIELD']='0'
        else:target['tags']['DAMAGE']=str(number(target,'DAMAGE')+1)
        target['tags']['ATK']=str(number(target,'ATK')+2)
        src['tags'].update(EXHAUSTED='1',LOCATION_ACTION_COOLDOWN='1',DAMAGE=str(number(src,'DAMAGE')+1))
        for player in (me,foe):
            player['board']=[e for e in player['board'] if not ((e['tags'].get('CARDTYPE')=='MINION' or e['id']==src['id']) and hp(e)<=0)]
    elif adapter=='armor2':
        src['tags']['EXHAUSTED']='1'
        hero=me['heroes'][0]
        hero['tags']['ARMOR']=str(number(hero,'ARMOR')+2)
    elif adapter=='coin':
        me['hand']=[e for e in me['hand'] if e['id']!=src['id']]
        me['mana']=min(10,me['mana']+1)
    else:
        me['hand']=[e for e in me['hand'] if e['id']!=src['id']]
        src['tags'].update(ZONE='PLAY',EXHAUSTED='1',NUM_TURNS_IN_PLAY='0',NUM_ATTACKS_THIS_TURN='0')
        if number(src,'RUSH') or number(src,'CHARGE'):src['tags']['EXHAUSTED']='0'
        if adapter=='location_body':src['tags'].update(EXHAUSTED='0',LOCATION_ACTION_COOLDOWN='0',ATK='0')
        for tag,key in [('ATK','attack'),('HEALTH','health')]:
            if tag not in src['tags'] and key in definition:src['tags'][tag]=str(definition[key])
        if not all(tag in src['tags'] for tag in ('ATK','HEALTH')):
            return Transition(None,'手下數值未知')
        me['board'].append(src)
        if adapter=='ducklings':
            next_id=min([0]+list(entity_map(after)))-1
            for _ in range(min(3,7-len(me['board']))):
                me['board'].append(dict(id=next_id,card_id='EDR_492t',tags=dict(
                    CONTROLLER=me['controller'],CARDTYPE='MINION',ZONE='PLAY',
                    ATK='1',HEALTH='1',DAMAGE='0',RUSH='1',EXHAUSTED='0',
                    NUM_TURNS_IN_PLAY='0',NUM_ATTACKS_THIS_TURN='0')))
                next_id-=1
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
            for player in (me,foe):player['board']=[e for e in player['board'] if e['tags'].get('CARDTYPE')!='MINION' or number(e,'DORMANT') or hp(e)>0]
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


def simulate_attack(state,action):
    own,enemy=sides(state)
    entities=entity_map(state)
    source=entities.get(action.get('entity_id'));target=entities.get(action.get('target_id'))
    if source is None or target is None:return Transition(None,'攻擊來源或目標已不存在')
    if source not in own['board'] or source['tags'].get('CARDTYPE')!='MINION' or target not in enemy['board']+enemy['heroes'] or target['tags'].get('CARDTYPE') not in ('MINION','HERO'):
        return Transition(None,'只模擬我方手下攻擊敵方角色')
    if number(source,'DORMANT') or number(target,'DORMANT'):return Transition(None,'休眠手下不參與戰鬥')
    blocked=('IMMUNE','CANT_BE_DAMAGED','CANT_BE_ATTACKED','STEALTH',
             'DEATHRATTLE','REBORN','CANT_ATTACK','CANT_ATTACK_HEROES')
    if any(number(e,t) for p in (own,enemy) for e in p['board']+p['heroes'] for t in blocked):
        return Transition(None,'尚未建模的攻擊限制或觸發')
    if any(number(e,'LIFESTEAL') for e in (source,target)) and any(
            int(p.get('player_tags',{}).get('HEALING_DOES_DAMAGE',0)) for p in (own,enemy)):
        return Transition(None,'尚未建模的治療轉傷害效果')
    if source['tags'].get('EXHAUSTED')!='0' or number(source,'FROZEN') or number(source,'ATK')<=0:
        return Transition(None,'攻擊者未確認可攻擊')
    taunts=[e for e in enemy['board'] if number(e,'TAUNT') and not number(e,'DORMANT')]
    if taunts and target not in taunts:return Transition(None,'仍有嘲諷')
    hero_target=target['tags'].get('CARDTYPE')=='HERO'
    if hero_target and number(source,'RUSH') and number(source,'NUM_TURNS_IN_PLAY')==0 and not number(source,'CHARGE'):
        return Transition(None,'新進場衝刺手下不能攻擊英雄')
    after=copy.deepcopy(state);me,foe=sides(after)
    src=entity_map(after)[source['id']];dst=entity_map(after)[target['id']]
    def damage(entity,amount,poison=False):
        if amount<=0:return 0
        if number(entity,'DIVINE_SHIELD'):entity['tags']['DIVINE_SHIELD']='0';return 0
        armor=min(amount,number(entity,'ARMOR'))
        entity['tags']['ARMOR']=str(number(entity,'ARMOR')-armor)
        entity['tags']['DAMAGE']=str(number(entity,'HEALTH') if poison and amount>armor else number(entity,'DAMAGE')+amount-armor)
        # Overkill and armor count as damage; poison destruction adds no healing.
        return amount
    dealt=damage(dst,number(src,'ATK'),bool(number(src,'POISONOUS')) and not hero_target)
    returned=damage(src,number(dst,'ATK'),bool(number(dst,'POISONOUS'))) if not hero_target else 0
    for player,minion,amount in ((me,src,dealt),(foe,dst,returned)):
        if number(minion,'LIFESTEAL') and amount:
            hero=player['heroes'][0]
            hero['tags']['DAMAGE']=str(max(0,number(hero,'DAMAGE')-amount))
    attacks=number(src,'NUM_ATTACKS_THIS_TURN')+1
    src['tags']['NUM_ATTACKS_THIS_TURN']=str(attacks)
    src['tags']['EXHAUSTED']='1' if attacks>=(2 if number(src,'WINDFURY') else 1) else '0'
    for player in (me,foe):
        player['board']=[e for e in player['board'] if e['tags'].get('CARDTYPE')!='MINION' or number(e,'DORMANT') or hp(e)>0]
        for index,e in enumerate(player['board'],1):e['tags']['ZONE_POSITION']=str(index)
    after['options']=[];after['options_fresh']=False
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
    for source in own['board']:
        if source.get('card_id')=='CORE_REV_990' and not number(source,'EXHAUSTED') and not number(source,'LOCATION_ACTION_COOLDOWN'):
            for target in own['board']+enemy['board']:
                if target['tags'].get('CARDTYPE')=='MINION':
                    yield dict(key=f"sim:location:{source['id']}:{target['id']}",kind='location',entity_id=source['id'],
                               target_id=target['id'],cost=0,description=f"{name_of(source,cards)} → {name_of(target,cards)}")
        if source['tags'].get('EXHAUSTED')!='0':continue
        for target in enemy['board']+enemy['heroes']:
            yield dict(key=f"sim:attack:{source['id']}:{target['id']}",kind='attack',
                       entity_id=source['id'],target_id=target['id'],cost=0,
                       description=f"{name_of(source,cards)} → {name_of(target,cards)}")


def card_plans(state,cards,limit=2,max_depth=3,beam_width=16,time_budget=.04):
    from laya_hearthstone.turn_end import finish_turn
    from laya_hearthstone.survival import end_turn_threat
    actions,_=get_actions(state,cards)
    results=[];frontier=[]
    deadline=time.monotonic()+time_budget
    for action in actions.values():
        if action['kind']=='end_turn':
            frontier.append((state,action,[]));continue
        if action['kind'] not in ('play','hero_power','attack','location'):continue
        transition=simulate_card(state,action,cards)
        if transition.state is None:continue
        frontier.append((transition.state,action,[action['description']]))
    def locations(player):return [e for e in player['board'] if e['tags'].get('CARDTYPE')=='LOCATION']
    def location_value(player):
        return sum(max(0,hp(e))*.5 for e in locations(player) if e.get('card_id')=='CORE_REV_990')
    def location_summary(player):
        return ','.join(f"{name_of(e,cards)} {max(0,hp(e))}次"+
                        ('冷卻' if number(e,'EXHAUSTED') or number(e,'LOCATION_ACTION_COOLDOWN') else '可用')
                        for e in locations(player)) or '無'
    def resources(snapshot):
        own,enemy=sides(snapshot)
        return (f"；地標我 {location_summary(own)}／敵 {location_summary(enemy)}"
                if locations(own) or locations(enemy) else '')
    def evaluate(snapshot,action,sequence):
        own,enemy=sides(snapshot)
        health=hp(enemy['heroes'][0])+number(enemy['heroes'][0],'ARMOR')
        def active(player):return [e for e in player['board'] if e['tags'].get('CARDTYPE')=='MINION' and not number(e,'DORMANT')]
        friendly=','.join(f"{number(e,'ATK')}/{hp(e)}" for e in active(own)) or '空'
        hostile=','.join(f"{number(e,'ATK')}/{hp(e)}" for e in active(enemy)) or '空'
        score=sum(number(e,'ATK')*1.3+hp(e)*.5 for e in active(own))-sum(number(e,'ATK')*1.3+hp(e)*.5 for e in active(enemy))-health*.8+(hp(own['heroes'][0])+number(own['heroes'][0],'ARMOR'))*.2
        score+=location_value(own)-location_value(enemy)
        if hp(own['heroes'][0])<=0:score=-100000
        elif health<=0:score=100000
        return dict(action=action,sequence=sequence,score=score,
            summary=f"{len(sequence)}步：敵英雄 {health}；我英雄 {hp(own['heroes'][0])}+{number(own['heroes'][0],'ARMOR')}甲；我方 {friendly}；敵方 {hostile}；剩餘法力 {own['mana']}"+resources(snapshot),
            lethal=health<=0 and hp(own['heroes'][0])>0,scope='known_card_prefix',complete_turn=False)
    def completed(snapshot,first,sequence,prefix):
        if prefix['lethal']:
            return dict(prefix,scope='game_ending_sequence',complete_turn=True)
        ending=finish_turn(snapshot,cards)
        if ending.boundary:
            return dict(prefix,boundary=ending.boundary)
        evaluated=[(p,evaluate(s,first,sequence)) for p,s in ending.outcomes]
        result=dict(prefix,score=sum(p*r['score'] for p,r in evaluated),
                    sequence=sequence+['結束回合'],complete_turn=True,scope='own_turn_end',
                    lethal=all(r['lethal'] for _,r in evaluated),
                    lethal_probability=sum(p for p,r in evaluated if r['lethal']),
                    outcome_count=len(evaluated))
        if len(evaluated)==1:
            result['summary']='回合結束：'+evaluated[0][1]['summary']
        else:
            health=[];counts=[];pressure=[]
            for _,s in ending.outcomes:
                _,foe=sides(s)
                health.append(max(0,hp(foe['heroes'][0])+number(foe['heroes'][0],'ARMOR')))
                minions=[e for e in foe['board'] if e['tags'].get('CARDTYPE')=='MINION']
                counts.append(len(minions));pressure.append(sum(number(e,'ATK') for e in minions))
            result['summary']=(f"回合結束（隨機結算）：敵英雄 {min(health)}–{max(health)}；"
                f"敵手下 {min(counts)}–{max(counts)}；敵場攻擊 {min(pressure)}–{max(pressure)}；"
                f"斬殺率 {result['lethal_probability']:.0%}")+resources(snapshot)
        threat=end_turn_threat(ending,cards,min(.004,max(0,deadline-time.monotonic())))
        result['counterattack']=threat
        probability=threat['lethal_probability']
        if probability is not None:
            result['score']-=100*probability
            result['summary']+=f'；可見手下反擊致命率 {probability:.0%}'
        return result
    for depth in range(max_depth):
        frontier=sorted(frontier,key=lambda n:evaluate(*n)['score'],reverse=True)[:beam_width]
        children=[]
        for snapshot,first,sequence in frontier:
            outcome=evaluate(snapshot,first,sequence)
            plan=completed(snapshot,first,sequence,outcome)
            if first['kind']!='end_turn' or plan['complete_turn']:results.append(plan)
            if first['kind']=='end_turn' or outcome['lethal'] or outcome['score']==-100000 or depth+1==max_depth:continue
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
