"""Bounded model requests and hierarchical selection of complete legal actions."""
import copy
import json
import math
from strategy import compact_state, get_actions, entity_map, name_of, number, hp
from deck_profiles import strategy_context


class ContextBudgetError(ValueError):
    pass


HEURISTIC_LOG_WEIGHT=2.5


def predict_choice(router, context, question):
    agent=router.load('multilingual')
    tok=agent.tok
    maximum=min(1024,int(agent.cfg.get('max_len',1024)))
    head=min(256,int(agent.cfg.get('head_max_len',256)))
    criteria=question['move']['criteria']
    if not criteria:raise ValueError('沒有候選選項')
    # Tournament batches preserve full option text within the SDK's shared head.
    # Long descriptions live in state; the head contains an explicit reference.
    def tokens(text):
        return tok(text.replace(tok.mask_token,' '),add_special_tokens=False)['input_ids']
    instructions=question['move']['instructions']
    brief=instructions if len(tokens('choice question: '+instructions))<=64 else '依照 decision_instructions 選擇最佳選項。'
    def description(key,value):
        return value if len(tokens(' '+key+': '+value))<=48 else '詳見 candidate_details '+key
    def batches(items):
        reserve=max(16,len(tokens('choice question: '+brief)))
        groups=[];group=[];size=reserve
        for key,value in items:
            cost=1+len(tokens(' '+key+': '+description(key,value)))
            if group and size+cost>head:
                groups.append(group);group=[];size=reserve
            if size+cost>head:raise ValueError('單一選項超出模型問題預算')
            group.append((key,value));size+=cost
        if group:groups.append(group)
        return groups
    pending=list(criteria.items());calls=[]
    while True:
        groups=batches(pending)
        winners=[]
        if len(groups)==len(pending) and len(pending)>1:
            raise ValueError('模型問題預算不足以比較兩個選項')
        for group in groups:
            if len(group)==1 and len(groups)>1:
                winners.extend(group);continue
            payload=copy.deepcopy(context)
            if brief!=instructions:payload['decision_instructions']=instructions
            details={k:v for k,v in group if description(k,v)!=v}
            if details:payload['candidate_details']=details
            request={'move':dict(type='choice',instructions=brief,
                                criteria={k:description(k,v) for k,v in group})}
            try:
                answer,budget=_predict_batch(router,agent,payload,request,maximum,head)
            except ContextBudgetError:
                if len(group)<=2:raise
                # Long plans consume context as well as head tokens. Reduce the
                # comparison width before sacrificing any candidate description.
                finalists=[]
                for start in range(0,len(group),2):
                    pair=group[start:start+2]
                    if len(pair)==1:finalists.extend(pair);continue
                    sub_answer,sub_budget=predict_choice(router,context,{'move':dict(type='choice',instructions=instructions,criteria=dict(pair))})
                    calls.extend(sub_budget['comparisons'])
                    finalists.append((sub_answer['choice'],criteria[sub_answer['choice']]))
                sub_answer,sub_budget=predict_choice(router,context,{'move':dict(type='choice',instructions=instructions,criteria=dict(finalists))})
                calls.extend(sub_budget['comparisons'])
                winners.append((sub_answer['choice'],criteria[sub_answer['choice']]))
                continue
            calls.append(dict(choices=[k for k,_ in group],answer=answer,budget=budget))
            winners.append((answer['choice'],criteria[answer['choice']]))
        if len(winners)==1:
            budget=dict(calls[-1]['budget'],comparison_calls=len(calls),comparisons=calls)
            return calls[-1]['answer'],budget
        pending=winners


def _predict_batch(router,agent,context,question,maximum,head):
    tok=agent.tok
    from laya.common import build_sequence
    q=question['move']
    internal=dict(t='choice',ins=q['instructions'],crit=q['criteria'])
    # Check the complete question with the installed encoder before allocating context.
    sequence,markers=build_sequence(tok,'',internal,maximum,head)
    if len(markers)!=len(q['criteria']):
        raise ValueError('選項超出模型預算，停止決策')
    for index,(key,value) in enumerate(q['criteria'].items()):
        expected=tok((' '+key+': '+value).replace(tok.mask_token,' '),add_special_tokens=False)['input_ids']
        end=markers[index+1] if index+1<len(markers) else markers[index]+1+len(expected)
        if sequence[markers[index]+1:end]!=expected:
            raise ValueError('模型編碼器截斷選項，停止決策')
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
        raise ContextBudgetError('可見局面超出模型輸入預算，未截斷局面或候選')
    answer=router.predict(encoded(),question,model='multilingual',max_len=maximum,head_max_len=head)['answers']['move']
    if answer['choice'] not in q['criteria']:
        raise ValueError('模型輸出不在候選清單中')
    return answer,dict(context_tokens=count(),context_budget=room,max_len=maximum,
                       head_max_len=head,omitted=reductions)


def staged_action(state,cards,profile,choose,action_scores=None,survival_required=False):
    actions,_=get_actions(state,cards)
    remaining=list(actions.values())
    context=compact_state(state,cards)
    context['deck_strategy']=strategy_context(profile)
    if survival_required:context['priority']='保命：若現在結束回合，對手可用可見手下攻擊致命。'
    trace=[]
    entities=entity_map(state)
    kind_names={'play':'出牌','attack':'攻擊','hero_power':'英雄能力','end_turn':'結束回合'}
    for stage,field in [('動作與卡牌','source'),('指定目標','target_id')]:
        groups={}
        for action in remaining:
            value=(action['kind'],action.get('entity_id')) if field=='source' else action.get(field)
            groups.setdefault(value,[]).append(action)
        if len(groups)==1:continue
        mapping={f'a{i}':group for i,group in enumerate(groups.values())}
        def describe(group):
            first=group[0]
            if field=='source':
                if first['kind']=='end_turn':return f"結束回合；剩餘法力 {context['mana']}"
                source=entities.get(first.get('entity_id'))
                name=name_of(source,cards) if source else first['description']
                targets=[str(a['target_id']) for a in group if a.get('target_id') is not None]
                stats=f"；{number(source,'ATK')}/{hp(source)}" if source and source['tags'].get('CARDTYPE') in ('MINION','HERO') else ''
                return kind_names.get(first['kind'],first['kind'])+'：'+name+f"；費用 {first.get('cost',0)}"+stats+('；可選目標 '+','.join(targets) if targets else '')
            return first['description']
        criteria={key:describe(group) for key,group in mapping.items()}
        instructions=('選下一步動作或卡牌。根據卡牌效果、牌組計畫、場面與法力決定；之後再選目標。'
                      if field=='source' else '選擇指定目標。考慮存活、斬殺、順序與資源。')
        question={'move':dict(type='choice',instructions=instructions,criteria=criteria)}
        answer,budget=choose(context,question)
        if answer['choice'] not in mapping:raise ValueError('模型輸出不在本階段候選中')
        selected=answer['choice']
        prior={}
        probabilities=answer.get('probabilities',{})
        if action_scores and all(key in probabilities for key in mapping):
            prior={key:max(action_scores.get(a['key'],0) for a in group) for key,group in mapping.items()}
            lo,hi=min(prior.values()),max(prior.values())
            if hi>lo:
                # A bounded soft preference, never a legality filter: a strong
                # model preference can outweigh the entire heuristic range.
                combined={key:math.log(max(float(probabilities[key]),1e-9))+HEURISTIC_LOG_WEIGHT*(score-lo)/(hi-lo)
                          for key,score in prior.items()}
                selected=max(combined,key=combined.get)
        remaining=mapping[selected]
        context['selected_action']=remaining[0]['kind']
        sources={a.get('entity_id') for a in remaining}
        if len(sources)==1:context['selected_entity']=next(iter(sources))
        trace.append(dict(stage=stage,answer=answer,budget=budget,selected_choice=selected,
                          heuristic_scores=prior,heuristic_adjusted=selected!=answer['choice']))
    if len(remaining)!=1:
        raise ValueError('動作仍有未解析的替代操作')
    return remaining[0],trace
