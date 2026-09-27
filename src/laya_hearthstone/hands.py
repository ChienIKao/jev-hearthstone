"""Background game hands shared by the UI and command-line callers."""
from laya_hearthstone.paths import ROOT
import copy
import json
from pathlib import Path
import threading
import time
from laya_hearthstone.advisor import fingerprint, read_state
from laya_hearthstone.executor import DEFAULT_LAYOUT, validate, build_plan, action_succeeded, window_matches, pixel_plan
from laya_hearthstone.strategy import sides, get_actions
from laya_hearthstone.geometry import hand_points, resized_layout
from laya_hearthstone.background_input import BackgroundInput
from laya_hearthstone import win_input as win


class Hands:
    def __init__(self, root_path=None):
        self.root_path=Path(root_path or ROOT)
        self.cards={c['id']:c for c in read_state(self.root_path/'data/cards.zhTW.json')}
        self.layout=copy.deepcopy(DEFAULT_LAYOUT)
        if (self.root_path/'calibration.json').exists():
            self.layout.update(read_state(self.root_path/'calibration.json'))
        self.stop_event=threading.Event()
        self.test_results=[]
        self.notice=''
        self.last_pointer=None

    def run(self,continuous,background=True,method='window_preview',preferred=None,test_condition='未註記',test_minimized=False):
        backend=None
        preview=None
        hidden_window=None
        hwnd=None
        restore_minimized=False
        record={'test_id':str(time.time_ns()),'time':time.time(),'backend':method if background else 'sendinput','condition':test_condition,'sent':False,'confirmed':False}
        if isinstance(preferred,dict):record['action']=preferred
        try:
            if background and continuous:
                raise ValueError('背景輸入目前只開放單步驗證，請按「只做一步」')
            self.notice='3 秒後背景單步測試，不必切回爐石。' if background else '3 秒後開始，請切回爐石。F8 / Esc 隨時停止。'
            if self.stop_event.wait(3):
                return
            hwnd=win.find_game()
            restore_minimized=win.minimized(hwnd)
            if method=='window_preview':
                if restore_minimized or test_minimized:
                    raise ValueError('即時畫面模式請先還原遊戲視窗')
                from laya_hearthstone.window_preview import LiveWindowPreview
                preview=LiveWindowPreview(hwnd)
                record['presentation']='dwm_live_preview'
                record['preview_rect']=list(preview.rect)
                method='sendmessage_window'
            if background and method=='sendmessage_window':
                hidden_window=win.HiddenWindow(hwnd)
                record['hidden_alignment']=True
            if test_minimized:
                if not background or method not in ('anchored_touch','sendmessage_window','sendmessage','maa_postmessage'):
                    raise ValueError('最小化測試請選 MaaFramework 後端')
                restore_minimized=True
                win.minimize(hwnd)
            record['minimized_before']=win.minimized(hwnd)
            if background and method in ('anchored_touch','sendmessage_window','sendmessage','maa_postmessage'):
                from laya_hearthstone.maa_input import MaaTouchInput
                backend=MaaTouchInput(hwnd,method)
            else:
                backend=BackgroundInput(hwnd) if background else win
            if restore_minimized:
                if not hasattr(backend,'prepare_minimized'):
                    raise ValueError('此後端尚未支援最小化視窗')
                record['capture_size']=backend.prepare_minimized()
                if tuple(record['capture_size'])!=win.client_rect(hwnd)[2:]:
                    raise ValueError('擷取尺寸與客戶區不一致，未送出輸入')
                record['window_mode']='maa_pseudo_minimized'
            seen=None
            stable_since=time.monotonic()
            self.last_pointer=win.cursor()
            while not self.stop_event.is_set():
                if not background and not win.foreground(hwnd):
                    raise ValueError('爐石不在前景，已停止')
                pointer=win.cursor()
                if not background and self.last_pointer and max(abs(pointer[i]-self.last_pointer[i]) for i in (0,1))>18:
                    raise ValueError('偵測到手動移動滑鼠，已停止')
                state=read_state(self.root_path/'state.json')
                advice={} if preferred else read_state(self.root_path/'advice.json')
                if state.get('game_state')!='RUNNING':
                    raise ValueError('對局已結束，已停止')
                stamp=fingerprint(state)
                if preferred:
                    if isinstance(preferred,dict) and preferred.get('_game_serial')!=state.get('game_serial'):
                        raise ValueError('對局已變更，請重新選擇測試動作')
                    try:
                        legal,_=get_actions(state,self.cards)
                    except ValueError:
                        legal={}
                    if isinstance(preferred,dict):
                        matches=[a for a in legal.values() if all(a.get(k)==preferred.get(k) for k in ('kind','entity_id','target_id','key','replace_ids','opening_ids','choice_id'))]
                        if not matches:
                            raise ValueError('所選動作已失效；請重新讀取合法動作，不會改選其他卡牌')
                    else:
                        matches=[a for a in legal.values() if a['kind']==preferred and not a.get('target_id')]
                    advice={'status':'suggestion','state_fingerprint':stamp,'action':matches[0]} if len(matches)==1 else {'status':'waiting'}
                if stamp!=seen:
                    seen,stable_since=stamp,time.monotonic()
                if time.monotonic()-stable_since<0.3:
                    self.stop_event.wait(0.05)
                    continue
                if advice.get('status')=='waiting' and '未支援' in advice.get('message',''):
                    raise ValueError(advice['message'])
                if advice.get('status')!='suggestion' or advice.get('state_fingerprint')!=stamp:
                    self.notice='接手待命：等待我方回合與有效建議。'
                    self.stop_event.wait(0.1)
                    continue
                x,y,width,height=win.client_rect(hwnd)
                action=validate(state,advice,self.layout,width,height,self.cards)
                own,_=sides(state)
                if continuous and action['kind']=='play' and hand_points(len(own['hand']),self.layout)[1]!='calibrated':
                    raise ValueError(f"目前 {len(own['hand'])} 張手牌的座標尚未校準，請校準後再接手")
                if action['kind']=='play' and action['card_type']=='MINION' and action.get('target_id'):
                    # Playing a minion moves board centers before its battlecry target.
                    # Keep this multi-stage case manual until that UI is verified.
                    raise ValueError('指定目標戰吼需手動操作；普通出牌與法術已支援')
                self.notice='執行：'+action['description']
                current_layout=resized_layout(self.layout,width,height)
                plan=build_plan(state,action,current_layout)
                if background and method=='sendmessage_window':
                    from laya_hearthstone.maa_input import align_plan
                    record['alignment_start_rect']=list(win.client_rect(hwnd))
                    record['alignment_start_dpi']=win.U.GetDpiForWindow(hwnd)
                    rect,plan=align_plan(backend,lambda w,h:build_plan(state,action,resized_layout(self.layout,w,h)),lambda:win.client_rect(hwnd),self.stop_event)
                    x,y,width,height=rect
                    record['alignment_final_dpi']=win.U.GetDpiForWindow(hwnd)
                if fingerprint(read_state(self.root_path/'state.json'))!=stamp:
                    continue
                record.update(action=action,before_fingerprint=stamp,plan=plan,client_rect=[x,y,width,height],cursor_before=list(win.cursor()),foreground_before=win.foreground(hwnd),hand_position_source=hand_points(len(own['hand']),self.layout)[1])
                follows_window=background and method=='sendmessage_window'
                if follows_window:
                    backend.set_coordinate_space(width,height,lambda:win.client_rect(hwnd)[2:])
                cursor_samples=[]
                button_samples=[]
                def check():
                    if self.stop_event.is_set() or win.stop_pressed():
                        raise ValueError('已停止')
                    if not background and not win.foreground(hwnd):
                        raise ValueError('遊戲失去焦點，已停止')
                    current_rect=win.client_rect(hwnd)
                    cursor_samples.append(list(win.cursor()))
                    button_samples.append([bool(win.U.GetAsyncKeyState(key)&0x8000) for key in (1,2)])
                    expected_rect=(x,y,width,height)
                    if not follows_window and not window_matches(current_rect,expected_rect,background):
                        record['unexpected_client_rect']=list(current_rect)
                        raise ValueError('操作途中遊戲尺寸改變，已停止；請保持游標在同一螢幕')
                commands=pixel_plan(plan,width,height,(0,0) if background else (x,y))
                evidence=self.root_path/'data'/'input-evidence'
                evidence.mkdir(parents=True,exist_ok=True)
                before_path=evidence/(record['test_id']+'.before.json')
                before_path.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
                record['before_state']=str(before_path)
                record['pixel_plan']=commands
                for command in commands:
                    check()
                    if command['op']=='wait':
                        if self.stop_event.wait(command['seconds']):
                            raise ValueError('已停止')
                    elif command['op']=='click':
                        backend.click(command['point'],check)
                    elif command['op']=='drag':
                        backend.drag(command['from'],command['to'],check)
                self.last_pointer=win.cursor()
                record['input_cursor_samples']=cursor_samples[:]
                record['input_button_samples']=button_samples[:]
                record['cursor_motion_segments']=sum(a!=b for a,b in zip(cursor_samples,cursor_samples[1:]))
                record.update(sent=True,cursor_after=list(self.last_pointer),foreground_after=win.foreground(hwnd),client_rect_after=list(win.client_rect(hwnd)))
                self.notice='輸入已送出；等待遊戲日誌確認。'
                deadline=time.monotonic()+4
                confirmed=False
                while time.monotonic()<deadline:
                    check()
                    after=read_state(self.root_path/'state.json')
                    if action_succeeded(state,after,action):
                        confirmed=True
                        break
                    self.stop_event.wait(0.1)
                record.update(confirmed=confirmed)
                after_path=evidence/(record['test_id']+'.after.json')
                after_path.write_text(json.dumps(after,ensure_ascii=False,indent=2),encoding='utf-8')
                record['after_state']=str(after_path)
                with (self.root_path/'execution.jsonl').open('a',encoding='utf-8') as stream:
                    stream.write(json.dumps(record,ensure_ascii=False)+'\n')
                if not confirmed:
                    raise ValueError('日誌未確認操作成功，已停止；請檢查遊戲畫面')
                if not continuous:
                    self.notice='單步完成，日誌已確認；目前只觀察。'
                    break
                self.notice='操作已確認，等待結算與下一步建議。'
                seen=None
                self.stop_event.wait(0.6)
        except Exception as exc:
            self.notice=str(exc)
            record['error']=str(exc)
        finally:
            self.stop_event.set()
            if backend is not None and hasattr(backend,'close'):
                try:
                    backend.close()
                except Exception as exc:
                    self.notice=f'輸入清理失敗：{exc}'
                    record['cleanup_error']=str(exc)
            if hwnd is not None:
                try:
                    if restore_minimized:
                        win.minimize(hwnd)
                    record['minimized_after']=win.minimized(hwnd)
                    record['client_rect_final']=list(win.client_rect(hwnd))
                except Exception as exc:
                    record['window_cleanup_error']=str(exc)
            if hidden_window is not None:
                try:
                    hidden_window.close(restore_minimized)
                    record['client_rect_final']=list(win.client_rect(hwnd))
                    record['foreground_final']=win.foreground(hwnd)
                    record['cursor_final']=list(win.cursor())
                except Exception as exc:
                    record['window_cleanup_error']=str(exc)
            if preview is not None:
                try:
                    preview.close()
                except Exception as exc:
                    record['preview_cleanup_error']=str(exc)
            if not record['sent'] and 'error' not in record:
                record['error']='測試已取消，未完成送出'
            record['finished_at']=time.time()
            with (self.root_path/'input-tests.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(record,ensure_ascii=False)+'\n')
            self.test_results.append(record)


def main():
    import argparse
    parser=argparse.ArgumentParser(description='Laya background hands; inspection is the default.')
    parser.add_argument('--action', help='Exact current action key; omitted lists actions without input')
    parser.add_argument('--execute', action='store_true', help='Execute the selected action once')
    parser.add_argument('--backend', choices=('window_preview','anchored_touch','sendmessage','maa_postmessage','postmessage'), default='window_preview')
    args=parser.parse_args()
    hands=Hands()
    state=read_state(hands.root_path/'state.json')
    actions,_=get_actions(state,hands.cards)
    if not args.action:
        if args.execute:parser.error('--execute requires --action')
        print(json.dumps(list(actions.values()),ensure_ascii=True,indent=2))
        return
    if args.action not in actions:parser.error('Action is no longer available')
    action=actions[args.action]
    hwnd=win.find_game()
    _,_,w,h=win.client_rect(hwnd)
    advice=dict(status='suggestion',state_fingerprint=fingerprint(state),action=action)
    validate(state,advice,hands.layout,w,h,hands.cards)
    if not args.execute:
        print(json.dumps(build_plan(state,action,resized_layout(hands.layout,w,h)),ensure_ascii=True,indent=2))
        return
    action=dict(action,_game_serial=state.get('game_serial'))
    hands.run(False,True,args.backend,action,'CLI background single step')
    result=hands.test_results[-1]
    print(json.dumps(result,ensure_ascii=True,indent=2))
    if not result.get('confirmed'):raise SystemExit(1)


if __name__=='__main__':main()
