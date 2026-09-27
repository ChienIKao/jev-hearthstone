"""Pure coordinate planning and execution checks. No input is sent here."""
import time
import math
from geometry import hand_points, board_points, mulligan_points, choice_points
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
    'mulligan_overrides':{}, 'mulligan_confirm':[0.5,0.78],
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
    base_w,base_h=layout.get('width',0),layout.get('height',0)
    if min(width,height,base_w,base_h)<=0:
        raise ValueError('遊戲視窗尺寸無效')
    if now-state.get('observed_at',0)>2:
        raise ValueError('局面資料過期')
    if advice.get('status')!='suggestion' or advice.get('state_fingerprint')!=fingerprint(state):
        raise ValueError('建議已過期，等待重新計算')
    actions,unsupported=get_actions(state,cards)
    if advice['action'].get('kind') == 'choice':
        chosen = actions.get(advice['action']['key'])
        if chosen is None or chosen != advice['action']:
            raise ValueError('候選選項已變更')
        choice_points(len(chosen['choice_ids']),layout,chosen.get('choice_card_ids'))
        if chosen.get('requires_confirm') and not layout.get('choice_confirm'):
            raise ValueError('請先校準多選的確認按鈕')
        return chosen
    if advice['action'].get('kind') == 'mulligan':
        chosen = actions.get(advice['action']['key'])
        if chosen is None or any(chosen.get(k) != advice['action'].get(k) for k in ('replace_ids','opening_ids','choice_id','kind')):
            raise ValueError('起手選牌指令已失效')
        mulligan_points(len(chosen['opening_ids']), layout)
        return chosen
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
    if kind=='choice':
        points=choice_points(len(action['choice_ids']),layout,action.get('choice_card_ids'))
        plan=[]
        for i in action['choice_indices']:
            plan.append({'op':'click','point':points[i]})
            if action['requires_confirm']:
                plan.append({'op':'wait','seconds':.2})
        if action['requires_confirm']:
            if not layout.get('choice_confirm'):
                raise ValueError('請先校準多選的確認按鈕')
            plan.append({'op':'click','point':layout['choice_confirm']})
        return plan
    if kind=='mulligan':
        points=mulligan_points(len(action['opening_ids']),layout)
        selected=set(action['replace_ids'])
        plan=[]
        for entity_id,point in zip(action['opening_ids'],points):
            if entity_id in selected:
                plan.extend([{'op':'click','point':point},{'op':'wait','seconds':0.2}])
        plan.append({'op':'click','point':layout['mulligan_confirm']})
        return plan
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


def pixel_plan(plan, width, height, origin=(0, 0)):
    """Validate the whole plan before sending the first press."""
    result=[]
    def pixel(point):
        if (not isinstance(point,(list,tuple)) or len(point)!=2 or
            not all(isinstance(v,(int,float)) and math.isfinite(v) and .01<=v<=.99 for v in point)):
            raise ValueError('座標超出遊戲範圍')
        return (round(origin[0]+point[0]*width),round(origin[1]+point[1]*height))
    for command in plan:
        item=dict(command)
        if item['op']=='click':
            item['point']=pixel(item['point'])
        elif item['op']=='drag':
            item['from'],item['to']=pixel(item['from']),pixel(item['to'])
        elif item['op']!='wait':
            raise ValueError('未知輸入操作')
        result.append(item)
    return result


def action_succeeded(before,after,action):
    if before.get('game_serial')!=after.get('game_serial'):
        return False
    if action['kind']=='choice':
        sent=after.get('sent_choice') or {}
        return (sent.get('complete') is True and sent.get('type')==action['choice_type'] and
                sent.get('id')==action['choice_id'] and sorted(sent.get('entities',[]))==sorted(action['selected_ids']) and
                sent!=before.get('sent_choice'))
    if action['kind']=='mulligan':
        sent=after.get('sent_choice') or {}
        kept=[e for e in action['opening_ids'] if e not in action['replace_ids']]
        return (sent.get('complete') is True and sent.get('type')=='MULLIGAN' and
                sent.get('id')==action['choice_id'] and
                sorted(sent.get('entities',[]))==sorted(kept) and
                sent != before.get('sent_choice'))
    if 'sent_option' in after:
        sent=after.get('sent_option') or {}
        if (sent==before.get('sent_option') or sent.get('option_index')!=action.get('option_index')
                or sent.get('target_id')!=action.get('target_id',0)):
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
