"""Bounded combat search. Unknown triggers produce no simulated forecast."""
import copy
import time
from strategy import sides, number, hp, vanilla, get_actions, text_of


# These printed effects resolve when played, not during minion combat.
# Exact text checks make a card-data update fall back to unknown effects.
COMBAT_INERT={
    'CORE_NEW1_023':'飄渺',
    'END_033':'飄渺若你手中有其他龍類，消耗減少(3)',
    'CATA_556':'戰吼：獲得一個消耗為(3)以下的隨機龍類',
    'CAP_107':'戰吼：獲得一個1/1砲手，它會在回合結束時對一個隨機敵人造成1點傷害',
    'EDR_456':'戰吼：若你手中有龍類，發現一個有黑暗贈禮的龍類',
    'TLC_600':'戰吼：造成5點傷害並獲得5點護甲值同類：消耗減少(3)',
    'TIME_034':'倒轉戰吼：雙方裝備一把隨機武器，賦予你的武器+1/+1',
}


def combat_inert(entity,cards):
    if vanilla(entity,cards):return True
    expected=COMBAT_INERT.get(entity.get('card_id'))
    return expected is not None and ''.join(text_of(entity,cards).split())==expected


def combat_plans(state,cards,limit=5,beam_width=32,time_budget=.04):
    own,enemy=sides(state)
    actions,unsupported=get_actions(state,cards)
    if unsupported or state.get('enchantments'):
        return []
    if any(p.get('secret_count',0) or p.get('weapons') for p in (own,enemy)):
        return []
    if any(not combat_inert(e,cards) for e in own['board']+enemy['board']):
        return []
    forbidden=('STEALTH','IMMUNE','CANT_BE_DAMAGED','CANT_BE_ATTACKED','DORMANT','REBORN','DEATHRATTLE','LIFESTEAL')
    if any(number(e,t) for p in (own,enemy) for e in p['board']+p['heroes'] for t in forbidden):
        return []
    attacks=[a for a in actions.values() if a['kind']=='attack' and a['card_type']=='MINION']
    if not attacks:return []
    hero=enemy['heroes'][0]
    if number(hero,'DIVINE_SHIELD'):
        return []
    initial_health=hp(hero)+number(hero,'ARMOR')
    def unit(e):
        eligible=any(a['entity_id']==e['id'] for a in attacks)
        return dict(id=e['id'],atk=number(e,'ATK'),hp=hp(e),shield=bool(number(e,'DIVINE_SHIELD')),
                    taunt=bool(number(e,'TAUNT')),poison=bool(number(e,'POISONOUS')),
                    remaining=(max(0,2-number(e,'NUM_ATTACKS_THIS_TURN')) if number(e,'WINDFURY') else 1) if eligible else 0,
                    face=not number(e,'RUSH') or any(a['entity_id']==e['id'] and a['target_id']==hero['id'] for a in attacks))
    start=dict(friendly=[unit(e) for e in own['board']],enemy=[unit(e) for e in enemy['board']],health=initial_health,steps=[])
    deadline=time.monotonic()+time_budget
    def score(node):
        if node['health']<=0:return 100000
        def value(units):return sum(u['atk']*1.3+u['hp']*.5+int(u['shield'])*2 for u in units if u['hp']>0)
        pressure=sum(u['atk'] for u in node['enemy'] if u['hp']>0)
        danger=pressure>=hp(own['heroes'][0])+number(own['heroes'][0],'ARMOR')
        return value(node['friendly'])-value(node['enemy'])+(initial_health-node['health'])*.8-(20 if danger else 0)
    frontier=[start];ends=[]
    for _ in range(14):
        children=[]
        for node in frontier:
            if time.monotonic()>=deadline:break
            if node['steps']:ends.append(node)
            if node['health']<=0:continue
            taunts=[u['id'] for u in node['enemy'] if u['hp']>0 and u['taunt']]
            for attacker in node['friendly']:
                if attacker['hp']<=0 or attacker['remaining']<=0:continue
                targets=taunts or [u['id'] for u in node['enemy'] if u['hp']>0]+([hero['id']] if attacker['face'] else [])
                for target in targets:
                    first=next((a for a in attacks if a['entity_id']==attacker['id'] and a['target_id']==target),None)
                    if not node['steps'] and first is None:continue
                    child=copy.deepcopy(node)
                    source=next(u for u in child['friendly'] if u['id']==attacker['id'])
                    source['remaining']-=1
                    if target==hero['id']:child['health']-=source['atk']
                    else:
                        victim=next(u for u in child['enemy'] if u['id']==target)
                        def damage(unit,amount,poison):
                            if amount<=0:return
                            if unit['shield']:unit['shield']=False
                            else:unit['hp']=0 if poison else unit['hp']-amount
                        damage(victim,source['atk'],source['poison'])
                        damage(source,victim['atk'],victim['poison'])
                    child['steps'].append((source['id'],target))
                    children.append(child)
        if not children:break
        frontier=sorted(children,key=score,reverse=True)[:beam_width]
        if time.monotonic()>=deadline:break
    ends.extend(frontier)
    # Preserve different opening actions instead of returning reordered copies.
    plans=[];seen=set()
    for node in sorted(ends,key=score,reverse=True):
        if not node['steps'] or tuple(node['steps'][0]) in seen:continue
        seen.add(tuple(node['steps'][0]))
        first=next(a for a in attacks if (a['entity_id'],a['target_id'])==tuple(node['steps'][0]))
        summary=f"敵方英雄有效生命 {max(0,node['health'])}；我方 " + ','.join(f"{u['atk']}/{u['hp']}" for u in node['friendly'] if u['hp']>0)
        summary+='；敵方 '+','.join(f"{u['atk']}/{u['hp']}" for u in node['enemy'] if u['hp']>0)
        plans.append(dict(action=first,sequence=node['steps'],score=score(node),summary=summary,
                          lethal=node['health']<=0,scope='attack_prefix_only',complete_turn=False))
        if len(plans)>=limit:break
    return plans
