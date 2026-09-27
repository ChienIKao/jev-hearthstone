"""Continuous ranked matches with a fixed deck strategy for each run."""
import copy
import json
import time

from choices import pending_choice
from android_hands import StateChanged
from menu_navigation import RankedNavigator
from strategy import get_actions, sides
from device_lease import device_lease


def deadline_action(state, actions, elapsed):
    own,_=sides(state)
    if pending_choice(state) or own.get('player_tags',{}).get('MULLIGAN_STATE')=='INPUT':
        return None
    try:
        timeout=float(own.get('player_tags',{}).get('TIMEOUT',0))
    except (ValueError,TypeError):
        return None
    if timeout>0 and elapsed>=max(0,timeout-8):
        return next((a for a in actions.values() if a['kind']=='end_turn'),None)
    return None


class RankedSession:
    def __init__(self, hands, decider, profile, stop, progress, max_games=0):
        if not profile:
            raise ValueError('請先新增並選擇牌組')
        self.hands,self.decider,self.profile=hands,decider,copy.deepcopy(profile)
        self.stop,self.progress,self.max_games=stop,progress,max_games
        self.completed=0
        self.results=[]

    def run(self):
        with device_lease(self.hands.device.serial):
            return self._run()

    def _run(self):
        self.decider.profile=copy.deepcopy(self.profile)
        initial=self.hands.observe()
        if initial.get('game_state')=='RUNNING':
            raise ValueError('連續爬牌請從主選單或牌組畫面開始，以確認牌組與模式；目前對局可用「連續接手本局」')
        self.hands.reader.check_logging_health()
        self.progress('載入 Laya，完成後開始排隊…')
        self.decider.load()
        if self.stop.is_set():
            return '已停止，未開始排隊'
        navigator=RankedNavigator(self.hands.device,self.progress,self.stop)
        previous=None
        while not self.stop.is_set() and (not self.max_games or self.completed<self.max_games):
            self.hands.reader.check_logging_health()
            state=navigator.enter_game(self.hands,self.profile,previous)
            if state is None:
                break
            game=state['game_serial']
            turn_marker=None
            turn_started=None
            self.progress(f'第 {self.completed+1} 局：{self.profile["name"]}')
            while not self.stop.is_set():
                state=self.hands.observe()
                if state.get('game_serial')!=game:
                    raise ValueError('對局識別碼意外變更，已停止')
                if state.get('game_state')=='COMPLETE':
                    self.completed+=1
                    own,_=sides(state)
                    result=dict(game_serial=game,deck=self.profile['name'],mode=self.profile['mode'],
                                result=own.get('player_tags',{}).get('PLAYSTATE','UNKNOWN'),finished_at=time.time())
                    self.results.append(result)
                    with (self.hands.evidence.parent/'ranked-results.jsonl').open('a',encoding='utf-8') as output:
                        output.write(json.dumps(result,ensure_ascii=False)+'\n')
                    self.progress(f'已完成 {self.completed} 局：{result["result"]}')
                    previous=game
                    break
                if len(state.get('players',[]))<2 or not state.get('local_controller'):
                    self.stop.wait(.5)
                    continue
                own,_=sides(state)
                choosing=pending_choice(state) or own.get('player_tags',{}).get('MULLIGAN_STATE')=='INPUT'
                if choosing and not state.get('choices',{}).get(state['local_controller'],{}).get('complete'):
                    self.stop.wait(.5)
                    continue
                if not choosing and (own.get('current_player')!='1' or not state.get('options_fresh')):
                    self.stop.wait(.5)
                    continue
                actions,_=get_actions(state,self.hands.cards)
                if not choosing and turn_marker!=state.get('turn'):
                    turn_marker=state.get('turn')
                    turn_started=time.monotonic()
                self.progress('Laya 決策中：'+self.profile['name'])
                closing=deadline_action(state,actions,time.monotonic()-turn_started) if turn_started is not None else None
                decision=dict(action=closing,method='turn_deadline',seconds=0) if closing else self.decider.decide(state)
                if self.stop.is_set():
                    break
                action=actions[decision['action']['key']]
                try:
                    result=self.hands.run(action,state,self.stop.is_set)
                except StateChanged:
                    self.progress('局面已變更，重新決策')
                    continue
                with (self.hands.evidence.parent/'ranked-decisions.jsonl').open('a',encoding='utf-8') as output:
                    output.write(json.dumps(dict(game_serial=game,action=action['key'],
                                                 turn=state.get('turn'),revision=state.get('revision'),
                                                 description=action['description'],confirmed=result['confirmed'],
                                                 decision_seconds=decision.get('seconds'),
                                                 method=decision.get('method'),decision=decision,
                                                 execution=result['timings']),ensure_ascii=False)+'\n')
                if not result['confirmed']:
                    raise ValueError('操作未確認，停止爬牌：'+action['description'])
                self.progress('已確認：'+action['description']+
                              f'（決策 {decision.get("seconds",0):.2f} 秒，操作 {result["timings"]["total"]:.2f} 秒）')
                self.stop.wait(.05)
        return f'連續爬牌已停止，完成 {self.completed} 局'
