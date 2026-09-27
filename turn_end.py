"""Resolve supported end-of-turn effects without sampling hidden information."""
import copy
from dataclasses import dataclass
from strategy import sides,number,hp
from turn_search import combat_inert,passive_weapons_known
from enchantments import enchantment_boundary


@dataclass
class TurnEnd:
    outcomes: list
    boundary: str | None = None


def finish_turn(state,cards,max_outcomes=128):
    own,enemy=sides(state)
    if enchantment_boundary(state,cards) or any(p.get('secret_count',0) for p in (own,enemy)) or not passive_weapons_known(state,cards):
        return TurnEnd([],'未建模的秘密、武器或附魔結算')
    if any(not combat_inert(e,cards) for p in (own,enemy) for e in p['board']):
        return TurnEnd([],'未建模的回合結束效果')
    if any(number(e,t) for p in (own,enemy) for e in p['board']+p['heroes']
           for t in ('DORMANT','FROZEN','DEATHRATTLE','REBORN','IMMUNE','CANT_BE_DAMAGED')):
        return TurnEnd([],'未建模的回合結束狀態或死亡效果')
    if any(e.get('card_id')=='CAP_107t' and number(e,'LIFESTEAL') and not number(e,'SILENCED') for e in own['board']):
        return TurnEnd([],'尚未建模的生命竊取砲擊')
    shots=sum(e.get('card_id')=='CAP_107t' and not number(e,'SILENCED') for e in own['board'])
    targets=[e for e in enemy['board'] if e['tags'].get('CARDTYPE')=='MINION']+enemy['heroes']
    if max(1,len(targets))**shots>max_outcomes:
        return TurnEnd([],'隨機結算超出分支預算')
    outcomes=[(1.0,copy.deepcopy(state))]
    for _ in range(shots):
        children=[]
        for probability,snapshot in outcomes:
            me,foe=sides(snapshot)
            if hp(foe['heroes'][0])<=0:
                children.append((probability,snapshot));continue
            targets=[e for e in foe['board'] if e['tags'].get('CARDTYPE')=='MINION']+foe['heroes']
            for target in targets:
                after=copy.deepcopy(snapshot);_,opponent=sides(after)
                victim=next(e for e in opponent['board']+opponent['heroes'] if e['id']==target['id'])
                if number(victim,'DIVINE_SHIELD'):victim['tags']['DIVINE_SHIELD']='0'
                elif number(victim,'ARMOR'):victim['tags']['ARMOR']=str(number(victim,'ARMOR')-1)
                else:victim['tags']['DAMAGE']=str(number(victim,'DAMAGE')+1)
                opponent['board']=[e for e in opponent['board'] if e['tags'].get('CARDTYPE')!='MINION' or hp(e)>0]
                for i,e in enumerate(opponent['board'],1):e['tags']['ZONE_POSITION']=str(i)
                children.append((probability/len(targets),after))
        outcomes=children
    for _,snapshot in outcomes:
        snapshot['options']=[];snapshot['options_fresh']=False
        snapshot['forecast_turn_ended']=True
    return TurnEnd(outcomes)
