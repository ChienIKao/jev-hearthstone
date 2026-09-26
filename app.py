"""Local desktop control panel. Starts in observation mode on every launch."""
import copy
import json
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from advisor import fingerprint, read_state
from executor import DEFAULT_LAYOUT, point_for, validate, build_plan, action_succeeded
from strategy import sides, entity_map, name_of
from geometry import hand_points
from background_input import BackgroundInput
import win_input as win

ROOT=Path(__file__).parent


class Panel:
    def __init__(self):
        self.root=tk.Tk()
        self.root.title('Laya 爐石助手 — 觀察模式')
        self.root.geometry('790x680')
        self.root.minsize(720,580)
        style=ttk.Style(self.root)
        style.configure('TLabel',font=('Microsoft JhengHei',11))
        style.configure('TButton',font=('Microsoft JhengHei',11),padding=6)
        style.configure('Treeview',font=('Microsoft JhengHei',11),rowheight=28)
        style.configure('Treeview.Heading',font=('Microsoft JhengHei',11,'bold'))
        self.cards={c['id']:c for c in json.loads((ROOT/'data/cards.zhTW.json').read_text(encoding='utf-8'))}
        self.layout=copy.deepcopy(DEFAULT_LAYOUT)
        if (ROOT/'calibration.json').exists():
            self.layout.update(read_state(ROOT/'calibration.json'))
        self.stop_event=threading.Event()
        self.stop_event.set()
        self.worker=None
        self.notice='觀察中；不會操作滑鼠。請先校準，再測試單步。'
        self.state=None
        self.advice={}
        self.last_pointer=None
        self.busy=False
        self.calibrating=False
        self.status=tk.StringVar(value=self.notice)
        self.game=tk.StringVar(value='等待局面')
        self.suggestion=tk.StringVar(value='等待 Laya')
        self.detail=tk.StringVar(value='')
        self.method=tk.StringVar(value='')
        self.background=tk.BooleanVar(value=True)
        self._ui()
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.root.after(150,self.tick)

    def _ui(self):
        frame=ttk.Frame(self.root,padding=18)
        frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Laya 爐石助手',font=('Microsoft JhengHei',20,'bold')).pack(anchor='w')
        ttk.Label(frame,textvariable=self.status,wraplength=740,foreground='#97410b').pack(anchor='w',pady=(8,12))
        ttk.Label(frame,textvariable=self.game,font=('Microsoft JhengHei',11)).pack(anchor='w')
        ttk.Separator(frame).pack(fill='x',pady=12)
        ttk.Label(frame,textvariable=self.suggestion,font=('Microsoft JhengHei',15,'bold'),wraplength=730).pack(anchor='w')
        ttk.Label(frame,textvariable=self.method,wraplength=730).pack(anchor='w',pady=5)
        ttk.Label(frame,textvariable=self.detail,wraplength=730).pack(anchor='w')
        row=ttk.Frame(frame)
        ttk.Checkbutton(frame,text='背景輸入實驗（PostMessage，不移動滑鼠；先用單步測試）',variable=self.background).pack(anchor='w')
        row.pack(fill='x',pady=15)
        ttk.Button(row,text='校準座標',command=self.calibrate).pack(side='left',padx=(0,8))
        ttk.Button(row,text='只做一步',command=lambda:self.arm(False)).pack(side='left',padx=8)
        ttk.Button(row,text='開始連續接手',command=lambda:self.arm(True)).pack(side='left',padx=8)
        ttk.Button(row,text='停止（F8 / Esc）',command=self.stop).pack(side='right')
        ttk.Label(frame,text='啟動後有 3 秒切回爐石；切換視窗或移動滑鼠會停止連續操作。',wraplength=730).pack(anchor='w')
        ttk.Label(frame,text='手牌支援 1～10 張弧形定位；推估位置可單步測試，連續接手需校準。',wraplength=730).pack(anchor='w',pady=(2,10))
        self.table=ttk.Treeview(frame,columns=('zone','name','value'),show='headings',height=12)
        for key,label,width in [('zone','位置',80),('name','卡牌',380),('value','狀態',220)]:
            self.table.heading(key,text=label)
            self.table.column(key,width=width,anchor='w')
        self.table.pack(fill='both',expand=True)
        self.last_table=None

    def tick(self):
        if win.stop_pressed():
            self.stop()
        try:
            if self.stop_event.is_set() and not self.calibrating and (ROOT/'calibration.json').exists():
                layout=copy.deepcopy(DEFAULT_LAYOUT)
                layout.update(read_state(ROOT/'calibration.json'))
                self.layout=layout
            state=read_state(ROOT/'state.json')
            advice=read_state(ROOT/'advice.json')
            self.state,self.advice=state,advice
            own,enemy=sides(state)
            who='我方' if own.get('current_player')=='1' else '對手'
            self.game.set(f"第 {state.get('games_seen')} 場 ｜ 回合計數 {state.get('turn')} ｜ {who}回合 ｜ 法力 {own.get('mana')} ｜ {state.get('game_state')}")
            valid=advice.get('status')=='suggestion' and advice.get('state_fingerprint')==fingerprint(state) and time.time()-state.get('observed_at',0)<2
            if valid:
                self.suggestion.set(advice['action']['description'])
                labels={'laya':'Laya 選擇','rules_lethal':'簡單戰鬥斬殺搜尋','rules_tiebreak':'規則處理模糊選擇','rules_single':'唯一已支援動作'}
                self.method.set(f"{labels.get(advice.get('method'),advice.get('method',''))} ｜ {advice.get('seconds','?')} 秒 ｜ {advice.get('device','')}")
                self.detail.set('；'.join(advice['action'].get('reasons',[])))
            else:
                self.suggestion.set(advice.get('message') or '局面變動，等待新建議')
                self.method.set('')
                self.detail.set('')
            signature=json.dumps(state['players'],sort_keys=True)
            if signature!=self.last_table:
                self.table.delete(*self.table.get_children())
                for zone,label in [('hand','手牌'),('board','我方場上')]:
                    for e in own[zone]:
                        t=e['tags']
                        detail=f"{t.get('COST','?')}費" if zone=='hand' else f"{t.get('ATK','0')}/{int(t.get('HEALTH',0))-int(t.get('DAMAGE',0))}"
                        self.table.insert('',tk.END,values=(label,name_of(e,self.cards),detail))
                for e in enemy['board']:
                    t=e['tags']
                    self.table.insert('',tk.END,values=('敵方場上',name_of(e,self.cards),f"{t.get('ATK','0')}/{int(t.get('HEALTH',0))-int(t.get('DAMAGE',0))}"))
                self.last_table=signature
        except (ValueError,FileNotFoundError,PermissionError) as exc:
            self.game.set(str(exc))
        self.status.set(self.notice)
        self.root.after(150,self.tick)

    def stop(self):
        self.stop_event.set()
        self.notice='已停止；目前只觀察局面。'

    def close(self):
        self.stop_event.set()
        self.root.destroy()

    def arm(self,continuous):
        if self.worker and self.worker.is_alive():
            return
        if not self.layout.get('confirmed'):
            messagebox.showinfo('先校準','先按「校準座標」，檢查標記落在卡牌與按鈕中心。')
            return
        self.stop_event.clear()
        self.worker=threading.Thread(target=self.run,args=(continuous,self.background.get()),daemon=True)
        self.worker.start()

    def run(self,continuous,background=False):
        try:
            if background and continuous:
                raise ValueError('背景輸入目前只開放單步驗證，請按「只做一步」')
            self.notice='3 秒後背景單步測試，不必切回爐石。' if background else '3 秒後開始，請切回爐石。F8 / Esc 隨時停止。'
            if self.stop_event.wait(3):
                return
            hwnd=win.find_game()
            backend=BackgroundInput(hwnd) if background else win
            seen=None
            stable_since=time.monotonic()
            self.last_pointer=win.cursor()
            while not self.stop_event.is_set():
                if not background and not win.foreground(hwnd):
                    raise ValueError('爐石不在前景，已停止')
                pointer=win.cursor()
                if not background and self.last_pointer and max(abs(pointer[i]-self.last_pointer[i]) for i in (0,1))>18:
                    raise ValueError('偵測到手動移動滑鼠，已停止')
                state=read_state(ROOT/'state.json')
                advice=read_state(ROOT/'advice.json')
                if state.get('game_state')!='RUNNING':
                    raise ValueError('對局已結束，已停止')
                stamp=fingerprint(state)
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
                plan=build_plan(state,action,self.layout)
                if fingerprint(read_state(ROOT/'state.json'))!=stamp:
                    continue
                def check():
                    if self.stop_event.is_set() or win.stop_pressed():
                        raise ValueError('已停止')
                    if not background and not win.foreground(hwnd):
                        raise ValueError('遊戲失去焦點，已停止')
                    if win.client_rect(hwnd)!=(x,y,width,height):
                        raise ValueError('遊戲視窗移動或尺寸改變，已停止')
                def pixel(point):
                    if not point or not all(0.01<=v<=0.99 for v in point):
                        raise ValueError('座標超出遊戲範圍')
                    return round((0 if background else x)+point[0]*width),round((0 if background else y)+point[1]*height)
                for command in plan:
                    check()
                    if command['op']=='wait':
                        if self.stop_event.wait(command['seconds']):
                            raise ValueError('已停止')
                    elif command['op']=='click':
                        backend.click(pixel(command['point']),check)
                    elif command['op']=='drag':
                        backend.drag(pixel(command['from']),pixel(command['to']),check)
                self.last_pointer=win.cursor()
                deadline=time.monotonic()+4
                confirmed=False
                while time.monotonic()<deadline:
                    check()
                    after=read_state(ROOT/'state.json')
                    if action_succeeded(state,after,action):
                        confirmed=True
                        break
                    self.stop_event.wait(0.1)
                record={'time':time.time(),'backend':'postmessage' if background else 'sendinput','action':action,'confirmed':confirmed,'before_fingerprint':stamp}
                with (ROOT/'execution.jsonl').open('a',encoding='utf-8') as stream:
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
        finally:
            self.stop_event.set()

    def calibrate(self):
        self.stop()
        try:
            state=read_state(ROOT/'state.json')
            own,enemy=sides(state)
            hwnd=win.find_game()
            x,y,w,h=win.client_rect(hwnd)
        except Exception as exc:
            messagebox.showerror('無法校準',str(exc))
            return
        overlay=tk.Toplevel(self.root)
        self.calibrating=True
        overlay.overrideredirect(True)
        overlay.geometry(f'{w}x{h}+{x}+{y}')
        overlay.attributes('-topmost',True)
        overlay.attributes('-alpha',0.72)
        self.root.iconify()
        win.show_game(hwnd)
        overlay.lift()
        canvas=tk.Canvas(overlay,bg='#121820',highlightthickness=0)
        canvas.pack(fill='both',expand=True)
        markers={}
        points={}
        def marker(key,label,point,color):
            px,py=point[0]*w,point[1]*h
            circle=canvas.create_oval(px-13,py-13,px+13,py+13,fill=color,outline='white',width=2,tags=(key,))
            text=canvas.create_text(px,py-25,text=label,fill='white',font=('Microsoft JhengHei',11,'bold'),tags=(key,))
            markers[key]=(circle,text)
            points[key]=list(point)
        for key,label in [('hero_me','我方英雄'),('hero_enemy','敵方英雄'),('power_me','英雄能力'),('end_turn','結束回合'),('play_area','出牌落點')]:
            marker(key,label,self.layout[key],'#d39136')
        for side,player in [('me',own),('enemy',enemy)]:
            for i,e in enumerate(player['board']):
                marker(f'board:{side}:{i}',f'{side}場上 {i+1}',point_for(e['id'],state,self.layout),'#4998db')
        for i,e in enumerate(own['hand']):
            marker(f'hand:{i}',f'手牌 {i+1}',point_for(e['id'],state,self.layout),'#4ec895')
        source=hand_points(len(own['hand']),self.layout)[1]
        label='已校準' if source=='calibrated' else '弧形推估，需核對'
        canvas.create_text(w/2,35,text=f'{len(own["hand"])} 張手牌：{label}。拖動圓點至露出的可點擊處。Enter 儲存，Esc 取消。',fill='white',font=('Microsoft JhengHei',16,'bold'))
        dragged=[None]
        def press(event):
            nearest=canvas.find_closest(event.x,event.y)
            tags=canvas.gettags(nearest)
            dragged[0]=next((k for k in tags if k in markers),None)
        def motion(event):
            key=dragged[0]
            if key:
                px=max(20,min(w-20,event.x))
                py=max(20,min(h-20,event.y))
                circle,text=markers[key]
                canvas.coords(circle,px-13,py-13,px+13,py+13)
                canvas.coords(text,px,py-25)
                points[key]=[px/w,py/h]
        def save(_=None):
            latest=read_state(ROOT/'state.json')
            latest_own,latest_enemy=sides(latest)
            def positions(player,zone):
                return [(e['id'],e['tags'].get('ZONE_POSITION')) for e in player[zone]]
            if (latest.get('game_serial')!=state.get('game_serial') or
                positions(own,'hand')!=positions(latest_own,'hand') or
                positions(own,'board')!=positions(latest_own,'board') or
                positions(enemy,'board')!=positions(latest_enemy,'board')):
                self.calibrating=False
                overlay.destroy()
                self.root.deiconify()
                self.notice='校準期間卡牌位置已改變，請重新開啟校準。'
                return
            for key in ('hero_me','hero_enemy','power_me','end_turn','play_area'):
                self.layout[key]=points[key]
            if own['hand']:
                hand=[points[f'hand:{i}'] for i in range(len(own['hand']))]
                self.layout['hand_overrides'][str(len(hand))]=hand
            for side,player in [('me',own),('enemy',enemy)]:
                if player['board']:
                    board=[points[f'board:{side}:{i}'] for i in range(len(player['board']))]
                    self.layout['board_overrides'][side+':'+str(len(board))]=board
                    self.layout['board_'+side+'_y']=sum(p[1] for p in board)/len(board)
                    if len(board)>1:
                        self.layout['board_step']=(board[-1][0]-board[0][0])/(len(board)-1)
                        self.layout['board_center']=(board[0][0]+board[-1][0])/2
            self.layout.update(confirmed=True,width=w,height=h)
            (ROOT/'calibration.json').write_text(json.dumps(self.layout,ensure_ascii=False,indent=2),encoding='utf-8')
            overlay.destroy()
            self.calibrating=False
            self.root.deiconify()
            self.notice=f"校準已儲存（{len(own['hand'])} 張手牌）。建議先做一步測試。"
        canvas.bind('<Button-1>',press)
        canvas.bind('<B1-Motion>',motion)
        overlay.bind('<Return>',save)
        def cancel(_):
            overlay.destroy()
            self.calibrating=False
            self.root.deiconify()
        overlay.bind('<Escape>',cancel)
        overlay.focus_force()


if __name__=='__main__':
    Panel().root.mainloop()
