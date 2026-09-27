"""Execute one verified game action through Android-local touch input."""
from laya_hearthstone.paths import ROOT
import argparse
import json
from pathlib import Path
import time

from laya_hearthstone.advisor import fingerprint
from laya_hearthstone.android_device import AndroidDevice
from laya_hearthstone.android_reader import AndroidReader
from laya_hearthstone.android_layout import default_layout
from laya_hearthstone.executor import build_plan, validate, action_succeeded
from laya_hearthstone.geometry import resized_layout, board_points
from laya_hearthstone.strategy import get_actions, sides
from laya_hearthstone.device_lease import device_lease


class StateChanged(ValueError):
    """A decision expired before any input was sent."""


def android_plan(state, action, layout):
    plan=build_plan(state,action,layout)
    if action['kind']=='play' and action.get('card_type')=='MINION' and action.get('target_id'):
        own,_=sides(state)
        slots=board_points(len(own['board'])+1,'me',layout)
        plan[0]['to']=slots[-1]
        plan[1]['seconds']=2.5
        for index,entity in enumerate(own['board']):
            if entity['id']==action['target_id']:
                plan[-1]['point']=slots[index]
                break
    if action['kind']=='location' and action.get('target_id'):
        # Android locations use the same press-and-drag targeting gesture as
        # attacks. Desktop click-then-click leaves the location unused.
        return [{'op':'drag','from':plan[0]['point'],'to':plan[-1]['point']}]
    return plan


class AndroidHands:
    def __init__(self, device, layout, cards, evidence):
        self.device = device
        self.reader = AndroidReader(device)
        self.layout = layout
        self.cards = cards
        self.evidence = Path(evidence)
        self.action_interval = 2.5
        self._cooldown_until = None

    def observe(self):
        first=self.reader.poll()
        if first.get('options_fresh') or first.get('game_state')=='COMPLETE' or any(
                p.get('complete') for p in first.get('choices',{}).values()):
            return first
        time.sleep(.25)
        return self.reader.poll()

    def run(self, action, before, stop=lambda: False):
        with device_lease(self.device.serial):
            started=time.perf_counter()
            def wait():
                while self._cooldown_until is not None and time.perf_counter()<self._cooldown_until:
                    if stop():raise ValueError('Stopped')
                    time.sleep(min(.05,max(0,self._cooldown_until-time.perf_counter())))
                if stop():raise ValueError('Stopped')
            def attempt(state):
                try:
                    return self._run(action,state,stop)
                finally:
                    self._cooldown_until=time.perf_counter()+self.action_interval
            wait()
            result=attempt(before)
            attempts=[result['id']]
            if not result['confirmed']:
                wait()
                latest=self.observe()
                if action_succeeded(before,latest,action):
                    result=dict(result,confirmed=True,late_confirmation=True)
                    result.pop('error',None)
                elif fingerprint(latest)!=fingerprint(before):
                    result['retry_skipped']='局面已變更，不重複送出原操作'
                elif action['kind']=='mulligan' or len(result['plan'])!=1:
                    result['retry_skipped']='多步或可切換選取的操作，需確認目前選取狀態'
                else:
                    legal,_=get_actions(latest,self.cards)
                    if legal.get(action['key'])==action:
                        result=attempt(latest)
                        attempts.append(result['id'])
                    else:
                        result['retry_skipped']='原動作已不合法'
            result=dict(result,attempts=attempts)
            result['timings']=dict(result['timings'],total=round(time.perf_counter()-started,4))
            self.evidence.mkdir(parents=True,exist_ok=True)
            (self.evidence/(attempts[0]+'.operation.json')).write_text(
                json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            return result

    def _run(self, action, before, stop=lambda: False):
        started=time.perf_counter()
        def check():
            if stop():
                raise ValueError('Stopped')
        last_state_check=[time.monotonic()]
        def check_waiting():
            check()
            if time.monotonic()-last_state_check[0]>=.5:
                latest=self.observe()
                last_state_check[0]=time.monotonic()
                if latest.get('game_serial')!=before.get('game_serial') or fingerprint(latest)!=fingerprint(before):
                    raise StateChanged('Game state changed while waiting for the screen')
        def ready(frame):
            height,width=frame.shape[:2]
            layout=resized_layout(self.layout,width,height)
            if action['kind']=='mulligan':
                return self.device.mulligan_ready(frame,layout['mulligan_confirm'])
            return self.device.turn_ready(frame,layout['end_turn'],opening=str(before.get('turn')) in ('1','2'))
        settled = self.device.wait_stable(check_waiting,ready=ready if action['kind']!='choice' else None)
        observed_at=time.perf_counter()
        current = self.observe()
        if current['game_serial'] != before['game_serial'] or fingerprint(current) != fingerprint(before):
            raise StateChanged('Game state changed; select an action again')
        frame=self.device.last_frame
        size=(frame.shape[1],frame.shape[0])
        advice = dict(status='suggestion', state_fingerprint=fingerprint(current), action=action)
        validate(current, advice, self.layout, *size, self.cards)
        plan = android_plan(current, action, resized_layout(self.layout, *size))
        record = dict(id=str(time.time_ns()), platform='android', serial=self.device.serial,
                      action=action, plan=plan, size=size, settle_seconds=round(settled,3), sent=False, confirmed=False)
        self.evidence.mkdir(parents=True, exist_ok=True)
        prefix = self.evidence / record['id']
        def save(suffix, value):
            Path(str(prefix)+suffix).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        save('.before.json', current)
        try:
            import cv2
            cv2.imwrite(str(prefix)+'.before.png',frame[:,:,::-1])
            input_at=time.perf_counter()
            self.device.execute(plan, check, size=size)
            sent_at=time.perf_counter()
            record['sent'] = True
            deadline = time.monotonic()+12
            while time.monotonic() < deadline:
                check()
                after = self.reader.poll()
                save('.after.json', after)
                if action_succeeded(current, after, action):
                    record['confirmed'] = True
                    break
                time.sleep(.25)
            if not record['confirmed']:
                record['error'] = 'No matching game log confirmation'
        except Exception as exc:
            record['error'] = str(exc)
            raise
        finally:
            finished=time.perf_counter()
            record['timings']={'total':round(finished-started,4),'settle':round(settled,4),
                               'observe_plan_evidence':round(locals().get('input_at',finished)-observed_at,4),
                               'input':round(locals().get('sent_at',finished)-locals().get('input_at',finished),4),
                               'confirmation':round(finished-locals().get('sent_at',finished),4)}
            save('.result.json', record)
        return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--adb', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--layout', type=Path, default=Path('android-calibration.json'))
    parser.add_argument('--action')
    parser.add_argument('--decide', action='store_true', help='Ask Laya/rules to select the current action')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    root = ROOT
    cards = {c['id']: c for c in json.loads((root/'data/cards.zhTW.json').read_text(encoding='utf-8'))}
    layout = json.loads(args.layout.read_text(encoding='utf-8')) if args.layout.exists() else default_layout()
    hands = AndroidHands(AndroidDevice(args.adb,args.serial),layout,cards,root/'data/android-evidence')
    hands.device.connect()
    state = hands.observe()
    actions,_ = get_actions(state,cards)
    if args.action and args.decide:
        parser.error('Use either --action or --decide')
    if args.execute and not (args.action or args.decide):
        parser.error('--execute requires --action or --decide')
    if not args.action and not args.decide:
        print(json.dumps(actions,ensure_ascii=True,indent=2))
        return
    if args.decide:
        from laya_hearthstone.advisor import Decider
        decision = Decider(cards).decide(state)
        # The strategy annotates ranked actions; execution uses the legal packet.
        action = actions[decision['action']['key']]
    elif args.action not in actions:
        parser.error('Action is not currently legal')
    else:
        action = actions[args.action]
    if args.execute:
        result = hands.run(action,state)
        print(json.dumps(result,ensure_ascii=True,indent=2))
        if not result['confirmed']:
            raise SystemExit(1)
    else:
        latest = hands.observe()
        if latest['game_serial'] != state['game_serial'] or fingerprint(latest) != fingerprint(state):
            raise ValueError('Game state changed while deciding; request a new decision')
        state = latest
        size = hands.device.capture()
        validate(state,dict(status='suggestion',state_fingerprint=fingerprint(state),action=action),layout,*size,cards)
        print(json.dumps(android_plan(state,action,resized_layout(layout,*size)),indent=2))


if __name__ == '__main__':
    main()
