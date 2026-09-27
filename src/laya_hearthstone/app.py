"""Local desktop control panel. Starts in observation mode on every launch."""
import copy
import json
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from laya_hearthstone.advisor import fingerprint, read_state
from laya_hearthstone.executor import DEFAULT_LAYOUT, point_for
from laya_hearthstone.strategy import sides, name_of, card_cost
from laya_hearthstone.geometry import hand_points, resized_layout
from laya_hearthstone.hands import Hands
from laya_hearthstone import win_input as win

from laya_hearthstone.paths import ROOT


class Panel(Hands):
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
        self.root_path=ROOT
        self.test_results=[]
        if (ROOT/'input-tests.jsonl').exists():
            for line in (ROOT/'input-tests.jsonl').read_text(encoding='utf-8').splitlines()[-100:]:
                try:self.test_results.append(json.loads(line))
                except ValueError:pass
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
        self.background_method=tk.StringVar(value='window_preview')
        self._ui()
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.root.bind('<F6>',lambda _:self.calibrate())
        self.root.bind('<F7>',lambda _:self.arm(False))
        self.root.bind('<F9>',lambda _:self.arm(False,'hero_power'))
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
        ttk.Checkbutton(frame,text='背景輸入實驗（不移動滑鼠；先用單步測試）',variable=self.background).pack(anchor='w')
        ttk.Combobox(frame,textvariable=self.background_method,values=('window_preview','sendmessage','maa_postmessage','anchored_touch','postmessage'),state='readonly').pack(anchor='w')
        ttk.Button(frame,text='開啟輸入測試台（比較各模式）',command=self.open_test_window).pack(anchor='w')
        row.pack(fill='x',pady=15)
        ttk.Button(row,text='校準座標',command=self.calibrate).pack(side='left',padx=(0,8))
        ttk.Button(row,text='只做一步',command=lambda:self.arm(False)).pack(side='left',padx=8)
        ttk.Button(row,text='開始連續接手',command=lambda:self.arm(True)).pack(side='left',padx=8)
        ttk.Button(row,text='停止（F8 / Esc）',command=self.stop).pack(side='right')
        ttk.Label(frame,text='背景模式不需切回遊戲。前景模式才需切回爐石，且手動移動滑鼠會停止。',wraplength=730).pack(anchor='w')
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
            advice=read_state(ROOT/'advice.json') if (ROOT/'advice.json').exists() else {'message':'請開啟輸入測試台，選擇目前合法動作。'}
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
                        cost=card_cost(e,self.cards)
                        detail=f"{cost if cost is not None else '?'}費" if zone=='hand' else f"{t.get('ATK','0')}/{int(t.get('HEALTH',0))-int(t.get('DAMAGE',0))}"
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

    def open_test_window(self):
        if getattr(self,'test_window',None) and self.test_window.root.winfo_exists():
            self.test_window.root.lift()
            return
        from laya_hearthstone.input_test_ui import InputTestWindow
        self.test_window=InputTestWindow(self)

    def restore_game_window(self):
        if self.worker and self.worker.is_alive():
            self.notice='請先停止測試再還原視窗。'
            return
        try:
            win.U.ShowWindow(win.find_game(),3)
            self.notice='遊戲視窗已最大化復位。'
        except Exception as exc:self.notice=str(exc)

    def close(self):
        self.stop_event.set()
        if self.worker and self.worker.is_alive():
            self.notice='正在停止並還原遊戲視窗…'
            self.root.after(100,self.close)
            return
        self.root.destroy()

    def arm(self,continuous,preferred=None,test_method=None,test_condition='未註記',test_minimized=False):
        if self.worker and self.worker.is_alive():
            return False
        if not self.layout.get('confirmed'):
            messagebox.showinfo('先校準','先按「校準座標」，檢查標記落在卡牌與按鈕中心。')
            return False
        self.stop_event.clear()
        background=self.background.get() if test_method is None else test_method!='sendinput'
        method=self.background_method.get() if test_method is None else test_method
        self.worker=threading.Thread(target=self.run,args=(continuous,background,method,preferred,test_condition,test_minimized),daemon=True)
        self.worker.start()
        return True

    def calibrate(self):
        self.stop()
        if self.worker and self.worker.is_alive():
            self.notice='等待輸入停止並還原視窗後，再校準。'
            return
        try:
            state=read_state(ROOT/'state.json')
            own,enemy=sides(state)
            hwnd=win.find_game()
            x,y,w,h=win.client_rect(hwnd)
            current_layout=resized_layout(self.layout,w,h) if self.layout.get('confirmed') else copy.deepcopy(self.layout)
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
        opening=own.get('player_tags',{}).get('MULLIGAN_STATE')=='INPUT'
        if opening:
            from laya_hearthstone.mulligan import opening_cards
            try:
                opening_hand,_=opening_cards(state)
            except ValueError as exc:
                overlay.destroy()
                self.calibrating=False
                self.root.deiconify()
                self.notice=str(exc)
                return
            count=len(opening_hand)
            guessed=[[.5+(i-(count-1)/2)*.16,.46] for i in range(count)]
            saved=current_layout.get('mulligan_overrides',{}).get(str(count),guessed)
            for i,point in enumerate(saved):
                marker(f'mulligan:{i}',f'起手牌 {i+1}',point,'#4ec895')
            marker('mulligan_confirm','確認',current_layout['mulligan_confirm'],'#d39136')
        for key,label in ([] if opening else [('hero_me','我方英雄'),('hero_enemy','敵方英雄'),('power_me','英雄能力'),('end_turn','結束回合'),('play_area','出牌落點')]):
            marker(key,label,current_layout[key],'#d39136')
        for side,player in ([] if opening else [('me',own),('enemy',enemy)]):
            for i,e in enumerate(player['board']):
                marker(f'board:{side}:{i}',f'{side}場上 {i+1}',point_for(e['id'],state,current_layout),'#4998db')
        for i,e in enumerate([] if opening else own['hand']):
            marker(f'hand:{i}',f'手牌 {i+1}',point_for(e['id'],state,current_layout),'#4ec895')
        source=hand_points(len(own['hand']),self.layout)[1]
        label='已校準' if source=='calibrated' else '弧形推估，需核對'
        title=f'{count} 張起手牌與確認按鈕' if opening else f'{len(own["hand"])} 張手牌：{label}'
        canvas.create_text(w/2,35,text=title+'。拖動圓點至可點擊處。Enter 儲存，Esc 取消。',fill='white',font=('Microsoft JhengHei',16,'bold'))
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
                win.client_rect(hwnd)!=(x,y,w,h) or
                latest_own.get('player_tags',{}).get('MULLIGAN_STATE')!=own.get('player_tags',{}).get('MULLIGAN_STATE') or
                positions(own,'hand')!=positions(latest_own,'hand') or
                positions(own,'board')!=positions(latest_own,'board') or
                positions(enemy,'board')!=positions(latest_enemy,'board')):
                self.calibrating=False
                overlay.destroy()
                self.root.deiconify()
                self.notice='校準期間卡牌位置已改變，請重新開啟校準。'
                return
            self.layout=current_layout
            if opening:
                self.layout['mulligan_overrides'][str(count)]=[points[f'mulligan:{i}'] for i in range(count)]
                self.layout['mulligan_confirm']=points['mulligan_confirm']
            for key in (() if opening else ('hero_me','hero_enemy','power_me','end_turn','play_area')):
                self.layout[key]=points[key]
            if own['hand'] and not opening:
                hand=[points[f'hand:{i}'] for i in range(len(own['hand']))]
                self.layout['hand_overrides'][str(len(hand))]=hand
            for side,player in ([] if opening else [('me',own),('enemy',enemy)]):
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
    import sys
    panel=Panel()
    if '--test-ui' in sys.argv:
        panel.root.after(300,panel.open_test_window)
    panel.root.mainloop()
