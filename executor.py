"""Pure coordinate planning and execution checks. No input is sent here."""
import time
from geometry import hand_points, board_points
from advisor import fingerprint
from strategy import entity_map, get_actions, sides


def window_matches(current,expected,allow_translation=False):
    return current[2:]==expected[2:] if allow_translation else current==expected

DEFAULT_LAYOUT = {
    'confirmed':False, 'width':0, 'height':0,
    'hero_me':[0.50,0.765], 'hero_enemy':[0.50,0.20],
    'power_me':[0.59,0.77], 'end_turn':[0.798,0.455],
    'board_me_y':0.55, 'board_enemy_y':0.365,
    'board_center':0.5, 'board_step':0.067,
    'hand_center':0.48, 'hand_y':0.955, 'hand_step':0.046,
    'hand_max_span':0.34, 'play_area':[0.56,0.565],
    'hand_overrides':{}, 'board_overrides':{},
}


def point_for(entity_id,state,layout):
    own,enemy=sides(state)
    for side,player in [('me',own),('enemy',enemy)]:
        if any(e['id']==entity_id for e in player['heroes']):
            return layout['hero_'+side]
        if side=='me' and any(e['id']==entity_id for e in player['hero_powers']):
            return layout['power_me']
        board=player['board']
        for i,e in enumerate(board):
            if e['id']==entity_id:
                return board_points(len(board),side,layout)[i]
    for i,e in enumerate(own['hand']):
        if e['id']==entity_id:
            count=len(own['hand'])
            return hand_points(count,layout)[0][i]
    raise ValueError('找不到動作實體的螢幕位置')


def validate(state,advice,layout,width,height,cards,now=None):
    now=time.time() if now is None else now
    if not layout.get('confirmed'):
        raise ValueError('請先校準座標')
    if (width,height)!=(layout.get('width'),layout.get('height')):
        raise ValueError('遊戲視窗尺寸改變，請重新校準')
    if now-state.get('observed_at',0)>2:
        raise ValueError('局面資料過期')
    if advice.get('status')!='suggestion' or advice.get('state_fingerprint')!=fingerprint(state):
        raise ValueError('建議已過期，等待重新計算')
    actions,unsupported=get_actions(state,cards)
    own,enemy=sides(state)
    for player in (own,enemy):
        positions=[int(e['tags'].get('ZONE_POSITION',0)) for e in player['board']]
        if positions!=list(range(1,len(positions)+1)):
            raise ValueError('場面位置仍在更新，等待穩定')
    chosen=actions.get(advice['action']['key'])
    if chosen is None:
        raise ValueError('動作已不在目前合法清單')
    if chosen['kind']=='play':
        positions=[int(e['tags'].get('ZONE_POSITION',0)) for e in own['hand']]
        if positions!=list(range(1,len(positions)+1)):
            raise ValueError('手牌位置仍在更新，等待穩定')
    if chosen['kind']=='end_turn' and unsupported:
        raise ValueError('仍有未支援操作，不能自動結束回合')
    for field in ('entity_id','target_id','kind','option_index'):
        if chosen.get(field)!=advice['action'].get(field):
            raise ValueError('建議與目前動作不一致')
    return chosen


def build_plan(state,action,layout):
    kind=action['kind']
    if kind=='end_turn':
        return [{'op':'click','point':layout['end_turn']}]
    source=point_for(action['entity_id'],state,layout)
    target=point_for(action['target_id'],state,layout) if action.get('target_id') else None
    if kind=='attack':
        return [{'op':'drag','from':source,'to':target}]
    if kind=='play':
        if action['card_type']=='MINION' and target:
            return [{'op':'drag','from':source,'to':layout['play_area']},{'op':'wait','seconds':0.7},{'op':'click','point':target,'target_id':action['target_id']}]
        return [{'op':'drag','from':source,'to':target or layout['play_area']}]
    if kind in ('hero_power','location'):
        plan=[{'op':'click','point':source}]
        if target:
            plan.extend([{'op':'wait','seconds':0.2},{'op':'click','point':target,'target_id':action['target_id']}])
        return plan
    raise ValueError('此類操作尚未支援')


def action_succeeded(before,after,action):
    if before.get('game_serial')!=after.get('game_serial'):
        return False
    if after.get('game_state')=='COMPLETE':
        return True
    old_me,_=sides(before)
    new_me,_=sides(after)
    if action['kind']=='end_turn':
        return new_me.get('current_player')!='1'
    old=entity_map(before)
    new=entity_map(after)
    source_id=action.get('entity_id')
    if action['kind']=='play':
        return all(e['id']!=source_id for e in new_me['hand'])
    if source_id not in new:
        return True
    previous=old[source_id]['tags']
    current=new[source_id]['tags']
    if action['kind']=='attack':
        if int(current.get('NUM_ATTACKS_THIS_TURN',0))>int(previous.get('NUM_ATTACKS_THIS_TURN',0)):
            return True
        if current.get('EXHAUSTED')=='1' and previous.get('EXHAUSTED')!='1':
            return True
        target=action['target_id']
        return target not in new or new[target]['tags'].get('DAMAGE')!=old[target]['tags'].get('DAMAGE')
    if action['kind']=='hero_power':
        return current.get('EXHAUSTED')=='1' and previous.get('EXHAUSTED')!='1' or new_me['mana']!=old_me['mana']
    if action['kind']=='location':
        return current.get('DURABILITY')!=previous.get('DURABILITY') or current.get('EXHAUSTED')!=previous.get('EXHAUSTED')
    return False
