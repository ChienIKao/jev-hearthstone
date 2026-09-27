"""Bounded model requests and hierarchical selection of complete legal actions."""
import copy
import json
from strategy import compact_state, get_actions
from deck_profiles import strategy_context


def predict_choice(router, context, question):
    agent=router.load('multilingual')
    tok=agent.tok
    maximum=min(1024,int(agent.cfg.get('max_len',1024)))
    head=min(256,int(agent.cfg.get('head_max_len',256)))
    from laya.common import build_sequence
    q=question['move']
    internal=dict(t='choice',ins=q['instructions'],crit=q['criteria'])
    # Check the complete question with the installed encoder before allocating context.
    sequence,markers=build_sequence(tok,'',internal,maximum,head)
    if len(markers)!=len(q['criteria']):
        raise ValueError('選項超出模型預算，停止決策')
    room=maximum-len(sequence)
    value=copy.deepcopy(context)
    reductions=[]
    def encoded():
        return json.dumps(value,ensure_ascii=False,separators=(',',':'))
    def count():
        return len(tok(encoded(),add_special_tokens=False)['input_ids'])
    for limit in (96,48,24,12):
        if count()<=room:break
        def shorten(node,key=''):
            if isinstance(node,dict):
                if 'id' in node and 'name' in node and 'effect' in node:
                    return [node.get(k) for k in ('id','name','cost','atk','hp','armor','tags')]+[shorten(node['effect'],'effect'),node.get('printed_races',[])]
                return {k:shorten(v,k) for k,v in node.items() if k!='source_url'}
            if isinstance(node,list):return [shorten(item) for item in node]
            if isinstance(node,str) and key in ('effect','mulligan','game_plan','combos','meta_notes'):
                ids=tok(node,add_special_tokens=False)['input_ids']
                if len(ids)>limit:return tok.decode(ids[:limit],skip_special_tokens=True)+'…'
            return node
        value=shorten(copy.deepcopy(context))
        value['card_columns']=['id','name','cost','attack','health','armor','status','effect','printed_races']
        reductions.append('compact_cards_and_text_'+str(limit))
    if count()>room:
        raise ValueError('可見局面超出模型輸入預算，未截斷局面或候選')
    answer=router.predict(encoded(),question,model='multilingual',max_len=maximum,head_max_len=head)['answers']['move']
    if answer['choice'] not in q['criteria']:
        raise ValueError('模型輸出不在候選清單中')
    return answer,dict(context_tokens=count(),context_budget=room,max_len=maximum,
                       head_max_len=head,omitted=reductions)


def staged_action(state,cards,profile,choose):
    actions,_=get_actions(state,cards)
    remaining=list(actions.values())
    context=compact_state(state,cards)
    context['deck_strategy']=strategy_context(profile)
    trace=[]
    for stage,field in [('動作種類','kind'),('使用卡牌','entity_id'),('指定目標','target_id')]:
        groups={}
        for action in remaining:groups.setdefault(action.get(field),[]).append(action)
        if len(groups)==1:continue
        mapping={f'a{i}':group for i,group in enumerate(groups.values())}
        criteria={key:group[0]['description']+(f'（另有 {len(group)-1} 個合法選擇）' if len(group)>1 else '')
                  for key,group in mapping.items()}
        question={'move':dict(type='choice',instructions=f'選擇{stage}。考慮存活、斬殺、順序與資源；目標示例不是唯一目標。',criteria=criteria)}
        answer,budget=choose(context,question)
        if answer['choice'] not in mapping:raise ValueError('模型輸出不在本階段候選中')
        remaining=mapping[answer['choice']]
        context['selected_action']=remaining[0]['kind']
        context['selected_entity']=remaining[0].get('entity_id')
        trace.append(dict(stage=stage,answer=answer,budget=budget))
    if len(remaining)!=1:
        raise ValueError('動作仍有未解析的替代操作')
    return remaining[0],trace
