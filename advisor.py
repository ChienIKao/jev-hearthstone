"""Persistent Laya adviser with rules and stale-state rejection."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from snapshot_io import publish_text
from strategy import compact_state, rank_actions

ROOT = Path(__file__).parent
os.environ.setdefault('HF_HOME', str(ROOT / '.cache' / 'huggingface'))
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
os.environ.setdefault('HF_HUB_OFFLINE', '1')


def fingerprint(state):
    fields = ('game_serial','games_seen','turn','game_state','players','options','option_set','options_fresh','local_controller','unresolved_events','revision')
    return hashlib.sha256(json.dumps({k:state.get(k) for k in fields},sort_keys=True).encode()).hexdigest()


def read_state(path):
    for _ in range(5):
        try:
            return json.loads(path.read_text(encoding='utf-8-sig'))
        except (PermissionError, json.JSONDecodeError):
            time.sleep(0.03)
    raise ValueError('局面檔案暫時無法讀取')


def build_request(state, cards):
    evaluation = rank_actions(state, cards)
    shortlist = evaluation['ranked'][:6]
    if not shortlist:
        raise ValueError('目前動作尚未支援，需要手動操作')
    actions = {a['key']:a for a in shortlist}
    context = compact_state(state,cards)
    context['visible_enemy_attack'] = evaluation['visible_enemy_attack']
    context['danger_estimate'] = evaluation['danger_estimate']
    question = {'move': {'type':'choice','instructions':'選擇最有利的爐石戰記下一步。先考慮斬殺及存活，再考慮有效交換、卡牌效果與費用組合。規則分數只是參考。不要猜未知手牌。', 'criteria':{k:a['description']+'；'+','.join(a['reasons']) for k,a in actions.items()}}}
    return context, question, actions


class Decider:
    def __init__(self, cards, device='auto'):
        self.cards=cards
        self.device=device
        self.router=None

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
        evaluation=rank_actions(state,self.cards)
        ranked=evaluation['ranked']
        if not ranked:
            raise ValueError('目前動作尚未支援，需要手動操作')
        result={'evaluation':evaluation,'model_answer':None,'device':self.device}
        if evaluation['lethal']:
            chosen=evaluation['lethal']['action']
            method='rules_lethal'
        elif len(ranked)==1:
            chosen=ranked[0]
            method='rules_single'
        else:
            context,question,actions=build_request(state,self.cards)
            self.load()
            (ROOT/'last-request.json').write_text(json.dumps({'state':context,'questions':question},ensure_ascii=False,indent=2),encoding='utf-8')
            response=self.router.predict(json.dumps(context,ensure_ascii=False),question,model='multilingual',max_len=4096,head_max_len=1024)
            answer=response['answers']['move']
            result['model_answer']=answer
            result['device']=self.device
            choice=answer['choice']
            if choice not in actions:
                raise ValueError('模型輸出不在候選動作中')
            probabilities=sorted(answer.get('probabilities',{}).values(),reverse=True)
            margin=probabilities[0]-probabilities[1] if len(probabilities)>1 else 1
            chosen=actions[choice]
            # Operational tie-break, not a calibrated probability of winning.
            if margin < 0.08 or chosen['rule_score'] < ranked[0]['rule_score']-8:
                chosen=ranked[0]
                method='rules_tiebreak'
            else:
                method='laya'
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
