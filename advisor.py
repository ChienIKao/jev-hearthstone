"""Persistent Laya adviser with rules and stale-state rejection."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from snapshot_io import publish_text
from strategy import compact_state, rank_actions
from deck_profiles import strategy_context
from hsreplay_import import decision_reference, correct_mulligan

ROOT = Path(__file__).parent
os.environ.setdefault('HF_HOME', str(ROOT / '.cache' / 'huggingface'))
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
os.environ.setdefault('HF_HUB_OFFLINE', '1')


def reference_for_state(profile, state, cards):
    if not profile or not profile.get('reference_data'):
        return None
    from strategy import sides
    own,_=sides(state)
    names={cards.get(e.get('card_id'),{}).get('name') for e in own.get('hand',[])}
    return decision_reference(profile['reference_data'],names)


def fingerprint(state):
    fields = ('game_serial','games_seen','turn','step','game_state','players','options','option_set','options_fresh','local_controller','unresolved_events','revision','choices','sent_choice')
    return hashlib.sha256(json.dumps({k:state.get(k) for k in fields},sort_keys=True).encode()).hexdigest()


def read_state(path):
    for _ in range(5):
        try:
            return json.loads(path.read_text(encoding='utf-8-sig'))
        except (PermissionError, json.JSONDecodeError):
            time.sleep(0.03)
    raise ValueError('局面檔案暫時無法讀取')


def build_request(state, cards, profile=None):
    evaluation = rank_actions(state, cards)
    shortlist = evaluation['ranked'] if profile else evaluation['ranked'][:6]
    if not shortlist:
        raise ValueError('目前動作尚未支援，需要手動操作')
    actions = {a['key']:a for a in shortlist}
    context = compact_state(state,cards)
    if profile:
        context = {'deck_strategy': strategy_context(profile), **context}
        reference=reference_for_state(profile,state,cards)
        if reference:
            context['mulligan_reference']=reference
    context['visible_enemy_attack'] = evaluation['visible_enemy_attack']
    context['danger_estimate'] = evaluation['danger_estimate']
    question = {'move': {'type':'choice','instructions':'選擇最有利的爐石戰記下一步。先考慮斬殺及存活，再考慮有效交換、卡牌效果與費用組合。規則分數只是參考。不要猜未知手牌。', 'criteria':{k:a['description']+'；'+','.join(a['reasons']) for k,a in actions.items()}}}
    if profile:
        question['move']['instructions'] += '依照 deck_strategy 的牌組邏輯與 combo 安排順序、保留關鍵資源；只有目前合法的動作可以選擇。'
    return context, question, actions


class Decider:
    def __init__(self, cards, device='auto', profile=None):
        self.cards=cards
        self.device=device
        self.router=None
        self.profile=profile

    def load(self):
        if self.router is None:
            import torch
            from laya import Router
            if self.device=='auto':
                self.device='cuda' if torch.cuda.is_available() else 'cpu'
            if self.device=='cpu':
                torch.set_num_threads(min(4,os.cpu_count() or 1))
            self.router=Router(device=self.device)
            self.router.load('multilingual')

    def decide(self,state):
        start=time.monotonic()
        from strategy import sides, get_actions, name_of, text_of
        from decision_pipeline import predict_choice, staged_action
        own, _ = sides(state)
        from choices import pending_choice
        packet = pending_choice(state)
        if packet is not None:
            actions, _ = get_actions(state, self.cards)
            self.load()
            context = {'players': compact_state(state,self.cards), 'count_min':packet['count_min'], 'count_max':packet['count_max'], 'candidates': [
                {'id':e['id'],'name':name_of(e,self.cards),'effect':text_of(e,self.cards)} for e in packet['cards']]}
            context = {'deck_strategy': strategy_context(self.profile), **context}
            question = {'move': {'type':'choice', 'instructions':'根據目前局面選擇最合適的發現牌、選項或選牌組合，考慮卡牌效果、附加效果與可用法力，配合 deck_strategy 的牌組邏輯與 combo。',
                                'criteria':{k:a['description'] for k,a in actions.items()}}}
            answer,budget = predict_choice(self.router,context,question)
            if answer['choice'] not in actions:
                raise ValueError('模型輸出不在候選選牌清單中')
            return dict(action=actions[answer['choice']],method='laya',model_answer=answer,
                        device=self.device,seconds=round(time.monotonic()-start,3))
        if own.get('player_tags', {}).get('MULLIGAN_STATE') == 'INPUT':
            actions, _ = get_actions(state, self.cards)
            self.load()
            from mulligan import opening_cards
            opening, _ = opening_cards(state)
            context = {'opening_hand': [{'id': e['id'], 'name': name_of(e,self.cards),
                        'effect': text_of(e,self.cards)} for e in opening]}
            context = {'deck_strategy': strategy_context(self.profile), 'players': compact_state(state,self.cards), **context}
            reference=reference_for_state(self.profile,state,self.cards)
            if reference:
                context['mulligan_reference']=reference
            question = {'move': {'type':'choice', 'instructions':'依照 deck_strategy 的起手換牌思路、牌組邏輯與目前起手牌，選擇要換掉的組合。未提供思路時保留適合前期使用的卡牌。',
                                'criteria':{k:a['description'] for k,a in actions.items()}}}
            answer,budget = predict_choice(self.router,context,question)
            if answer['choice'] not in actions:
                raise ValueError('模型输出不在起手選牌清單中')
            chosen=actions[answer['choice']]
            corrected=correct_mulligan((self.profile or {}).get('reference_data'),opening,self.cards,chosen,actions)
            return dict(action=corrected,method='reference_mulligan' if corrected['key']!=chosen['key'] else 'laya',model_answer=answer,
                        device=self.device,seconds=round(time.monotonic()-start,3))
        evaluation=rank_actions(state,self.cards)
        ranked=evaluation['ranked']
        if not ranked:
            raise ValueError('目前動作尚未支援，需要手動操作')
        result={'evaluation':evaluation,'model_answer':None,'device':self.device}
        from turn_search import combat_plans
        from card_simulator import card_plans
        plans=combat_plans(state,self.cards,limit=3)+card_plans(state,self.cards)
        result['search_plans']=plans
        if evaluation['lethal']:
            chosen=evaluation['lethal']['action']
            method='rules_lethal'
        elif len(get_actions(state,self.cards)[0])==1:
            chosen=next(iter(get_actions(state,self.cards)[0].values()))
            method='rules_single'
        else:
            self.load()
            selected_plan=None
            if plans:
                plan_options={f'p{i}':p['summary'] for i,p in enumerate(plans)}
                plan_options['other']='改選出牌、技能或其他合法動作'
                context=compact_state(state,self.cards)
                context['deck_strategy']=strategy_context(self.profile)
                answer,budget=predict_choice(self.router,context,{'move':dict(type='choice',
                    instructions='比較已建模的動作結果；這些不是完整回合。也可選其他動作。',criteria=plan_options)})
                result['plan_selection']=dict(answer=answer,budget=budget)
                if answer['choice']!='other':selected_plan=plans[int(answer['choice'][1:])]
            if selected_plan:
                chosen,trace=selected_plan['action'],[]
            else:
                chosen,trace=staged_action(state,self.cards,self.profile,
                                          lambda context,question:predict_choice(self.router,context,question))
            result['stages']=trace
            result['device']=self.device
            method='laya_search' if selected_plan else 'laya_staged'
        if chosen['kind']=='end_turn' and evaluation['unsupported_options']:
            raise ValueError('還有未支援的合法操作，請手動處理後再結束回合')
        result.update(action=chosen,method=method,seconds=round(time.monotonic()-start,3))
        return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--state',type=Path,default=ROOT/'state.json')
    parser.add_argument('--output',type=Path,default=ROOT/'advice.json')
    parser.add_argument('--watch',action='store_true')
    parser.add_argument('--replay',action='store_true')
    parser.add_argument('--device',default='auto',choices=('auto','cpu','cuda'))
    args=parser.parse_args()
    cards={c['id']:c for c in json.loads((ROOT/'data/cards.zhTW.json').read_text(encoding='utf-8'))}
    decider=Decider(cards,args.device)
    last=None
    if args.watch:
        publish_text(args.output,json.dumps({'status':'loading','message':'正在載入本機 Laya'}))
        decider.load()
        print('Model ready: '+decider.device,flush=True)
    while True:
        try:
            state=read_state(args.state)
            stamp=fingerprint(state)
            expired=not args.replay and time.time()-state.get('observed_at',0)>2
            if stamp==last and not expired:
                if not args.watch:
                    return
                time.sleep(0.1)
                continue
            if expired:
                raise ValueError('局面監看資料已過期')
            last=stamp
            publish_text(args.output,json.dumps({'status':'thinking','message':'正在比較動作','state_fingerprint':stamp}))
            result=decider.decide(state)
            latest=read_state(args.state)
            stale=not args.replay and (fingerprint(latest)!=stamp or time.time()-latest.get('observed_at',0)>2)
            result.update(status='historical_test' if args.replay else ('stale' if stale else 'suggestion'),turn=state['turn'],state_fingerprint=stamp,generated_at=time.time(),automatic_execution=False)
            if stale:
                last=None
        except (ValueError,FileNotFoundError,PermissionError) as exc:
            result={'status':'waiting','message':str(exc),'automatic_execution':False}
        except Exception as exc:
            result={'status':'error','message':f'{type(exc).__name__}: {exc}','automatic_execution':False}
            last=None
        if not publish_text(args.output,json.dumps(result,ensure_ascii=False,indent=2)):
            last=None
        print(json.dumps({k:result[k] for k in ('status','turn','method','seconds','message','action') if k in result},ensure_ascii=True),flush=True)
        if not args.watch:
            return
        time.sleep(0.2 if result['status']!='error' else 2)


if __name__=='__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
