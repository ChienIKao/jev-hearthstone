"""Bounded reachability of lethal using only the opponent's visible minions."""
import copy
import time
from strategy import sides,number,hp
from turn_search import combat_inert,passive_weapons_known
from enchantments import enchantment_boundary


def visible_attack_threat(state,cards,time_budget=.008):
    from card_simulator import simulate_card
    own,enemy=sides(state)
    scope='visible_minion_attacks_only'
    def result(value,reason=None):return dict(lethal=value,scope=scope,reason=reason)
    if hp(own['heroes'][0])<=0:return result(True)
    if hp(enemy['heroes'][0])<=0:return result(False)
    if enchantment_boundary(state,cards) or any(p.get('secret_count',0) for p in (own,enemy)) or not passive_weapons_known(state,cards):
        return result(None,'未建模的秘密、武器或附魔')
    if any(not combat_inert(e,cards) for p in (own,enemy) for e in p['board']):
        return result(None,'未建模的場上觸發')
    forbidden=('DORMANT','IMMUNE','CANT_BE_DAMAGED','CANT_BE_ATTACKED','STEALTH','DEATHRATTLE','REBORN','CANT_ATTACK','CANT_ATTACK_HEROES')
    if any(number(e,t) for p in (own,enemy) for e in p['board']+p['heroes'] for t in forbidden):
        return result(None,'未建模的攻擊限制或觸發')
    prepared=copy.deepcopy(state)
    prepared['local_controller']=enemy['controller']
    attacker,defender=sides(prepared)
    for player in (attacker,defender):
        player['hand']=[];player['hero_powers']=[]
    for entity in attacker['board']:
        entity['tags'].update(EXHAUSTED='1' if number(entity,'FROZEN') else '0',
                              NUM_ATTACKS_THIS_TURN='0',NUM_TURNS_IN_PLAY='1')
    deadline=time.monotonic()+time_budget
    visited=set()
    def search(snapshot):
        attacking,defending=sides(snapshot)
        hero=defending['heroes'][0]
        if hp(hero)<=0:return True
        sources=[e for e in attacking['board'] if e['tags'].get('CARDTYPE')=='MINION'
                 and e['tags'].get('EXHAUSTED')=='0' and number(e,'ATK')>0]
        upper=sum(number(e,'ATK')*((2-number(e,'NUM_ATTACKS_THIS_TURN')) if number(e,'WINDFURY') else 1) for e in sources)
        if upper<hp(hero)+number(hero,'ARMOR'):return False
        if time.monotonic()>=deadline:return None
        key=tuple((e['id'],hp(e),number(e,'DIVINE_SHIELD'),number(e,'EXHAUSTED'),number(e,'NUM_ATTACKS_THIS_TURN'),number(e,'ARMOR'))
                  for p in (attacking,defending) for e in p['board']+p['heroes'])
        if key in visited:return False
        visited.add(key)
        targets=[e for e in defending['board'] if e['tags'].get('CARDTYPE')=='MINION' and number(e,'TAUNT')]
        if not targets:targets=[hero]+[e for e in defending['board'] if e['tags'].get('CARDTYPE')=='MINION']
        unknown=False
        for source in sources:
            for target in targets:
                transition=simulate_card(snapshot,dict(kind='attack',entity_id=source['id'],target_id=target['id']),cards)
                if transition.state is None:
                    unknown=True;continue
                answer=search(transition.state)
                if answer is True:return True
                if answer is None:unknown=True
        return None if unknown else False
    answer=search(prepared)
    return result(answer,'搜尋預算或效果邊界' if answer is None else None)


def end_turn_threat(ending,cards,time_budget=.008):
    if ending.boundary:return dict(lethal_probability=None,scope='visible_minion_attacks_only',reason=ending.boundary)
    deadline=time.monotonic()+time_budget
    probability=0.0
    for weight,snapshot in ending.outcomes:
        result=visible_attack_threat(snapshot,cards,max(0,deadline-time.monotonic()))
        if result['lethal'] is None:
            return dict(lethal_probability=None,scope=result['scope'],reason=result['reason'])
        if result['lethal']:probability+=weight
    return dict(lethal_probability=probability,scope='visible_minion_attacks_only',reason=None)
