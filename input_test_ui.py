"""User-operated input comparison panel. Opening it never sends game input."""
import json
import time
import tkinter as tk
from tkinter import ttk
from strategy import get_actions
from advisor import read_state

METHODS={
    '即時畫面背景操作':('window_preview','原位置顯示 Windows 即時遊戲投影；底層視窗在背景對齊，完成後還原。'),
    'Maa SendMessage（不移動視窗）':('sendmessage','MaaFramework 普通 SendMessage；不啟用游標或視窗位置對齊。'),
    'Maa PostMessage（不移動視窗）':('maa_postmessage','MaaFramework 普通 PostMessage，含官方啟用訊息流程；不啟用位置對齊。'),
    'PostMessage（背景訊息）':('postmessage','不移動游標。先前未確認成功，仍可重新測試。'),
    'AnchoredTouch（背景觸控）':('anchored_touch','不移動游標；可能閃爍。先前未確認成功，仍可重新測試。'),
    '視窗對齊 SendMessage':('sendmessage_window','操作期間暫時隱藏遊戲，復位後才顯示；不移動游標。跨螢幕縮放穩定後才出手。'),
    'SendInput（前景對照）':('sendinput','會操作實體滑鼠；倒數後需切回爐石。'),
}

class InputTestWindow:
    def __init__(self,panel):
        self.panel=panel
        self.root=tk.Toplevel(panel.root)
        self.root.title('輸入測試台 — 手動單步比較')
        self.root.geometry('940x830')
        self.root.minsize(860,800)
        frame=ttk.Frame(self.root,padding=16)
        frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='輸入測試台',font=('Microsoft JhengHei',19,'bold')).pack(anchor='w')
        ttk.Label(frame,text='每次只測一個動作。先保持滑鼠靜止；之後再測手動移動是否影響結果。',wraplength=880).pack(anchor='w',pady=6)
        self.method=tk.StringVar(value='即時畫面背景操作')
        chooser=ttk.Combobox(frame,textvariable=self.method,values=list(METHODS),state='readonly',width=45)
        chooser.pack(anchor='w')
        self.description=tk.StringVar()
        ttk.Label(frame,textvariable=self.description,wraplength=880).pack(anchor='w',pady=6)
        chooser.bind('<<ComboboxSelected>>',lambda _:self.describe())
        self.describe()
        self.condition=tk.StringVar(value='滑鼠靜止／遊戲在背景')
        ttk.Combobox(frame,textvariable=self.condition,values=('滑鼠靜止／遊戲在背景','滑鼠移動／遊戲在背景','滑鼠靜止／遊戲在前景','自行描述於備註'),state='readonly',width=45).pack(anchor='w')
        self.minimized=tk.BooleanVar(value=False)
        ttk.Checkbutton(frame,text='最小化測試（實驗）：透明還原後操作，完成時再次最小化',variable=self.minimized).pack(anchor='w',pady=4)
        ttk.Label(frame,text='選一個目前合法動作；出牌／英雄能力會實際消耗資源。局面變更時不會改選另一張牌。',wraplength=880).pack(anchor='w',pady=(12,5))
        self.action=tk.StringVar()
        self.actions={}
        self.action_box=ttk.Combobox(frame,textvariable=self.action,state='readonly',width=90)
        self.action_box.pack(fill='x')
        row=ttk.Frame(frame)
        row.pack(fill='x',pady=8)
        ttk.Button(row,text='重新讀取合法動作',command=self.refresh).pack(side='left')
        ttk.Button(row,text='開始測試（3 秒後）',command=self.start).pack(side='left',padx=8)
        ttk.Button(row,text='停止／F8',command=panel.stop).pack(side='left')
        ttk.Button(row,text='遊戲視窗復位',command=panel.restore_game_window).pack(side='left',padx=8)
        self.status=tk.StringVar(value='尚未開始；開啟此視窗不會操作遊戲。')
        ttk.Label(frame,textvariable=self.status,wraplength=880,foreground='#97410b').pack(anchor='w',pady=8)
        ttk.Label(frame,text='結果：API 已返回 ≠ 遊戲已執行。日誌確認與你目視的結果分開記錄。',wraplength=880).pack(anchor='w')
        self.results=ttk.Treeview(frame,columns=('time','backend','action','result'),show='headings',height=6)
        for key,title,width in [('time','時間',80),('backend','後端',150),('action','動作',310),('result','日誌／執行結果',280)]:
            self.results.heading(key,text=title)
            self.results.column(key,width=width)
        self.results.pack(fill='both',expand=True,pady=8)
        self.record_detail=tk.StringVar(value='選取紀錄可查看測試條件與輸入座標。')
        ttk.Label(frame,textvariable=self.record_detail,wraplength=880).pack(anchor='w',pady=4)
        self.results.bind('<<TreeviewSelect>>',lambda _:self.show_record())
        self.notes=tk.StringVar()
        ttk.Label(frame,text='備註（例如：滑鼠有移動、視窗跳動、點到別張牌）').pack(anchor='w')
        ttk.Entry(frame,textvariable=self.notes).pack(fill='x',pady=4)
        row=ttk.Frame(frame)
        row.pack(fill='x')
        for text in ('目視成功','目視無反應','點錯／不確定'):
            ttk.Button(row,text=text,command=lambda value=text:self.annotate(value)).pack(side='left',padx=(0,8))
        self.records={}
        self.seen=0
        self.refresh()
        self.root.after(200,self.tick)

    def describe(self):
        self.description.set(METHODS[self.method.get()][1])

    def refresh(self):
        try:
            state=read_state(self.panel.root_path/'state.json')
            actions,_=get_actions(state,self.panel.cards)
            self.actions={f'{a["description"]}  [{key}]':dict(a,_game_serial=state.get('game_serial')) for key,a in actions.items()
                          if not (a['kind']=='play' and a.get('card_type')=='MINION' and a.get('target_id'))}
            self.action_box['values']=list(self.actions)
            self.action.set(next(iter(self.actions),''))
            self.status.set('選好後端與動作後，按「開始測試」。' if self.actions else '目前沒有可測動作；等我方回合再重新讀取。')
        except Exception as exc:
            self.actions={}
            self.action_box['values']=()
            self.action.set('')
            self.status.set(str(exc))

    def start(self):
        action=self.actions.get(self.action.get())
        if action is None:
            self.status.set('請先重新讀取並選擇合法動作。')
            return
        if self.panel.worker and self.panel.worker.is_alive():
            self.status.set('已有測試執行中，請先停止或等它完成。')
            return
        method=METHODS[self.method.get()][0]
        started=self.panel.arm(False,dict(action),test_method=method,test_condition=self.condition.get(),test_minimized=self.minimized.get())
        self.status.set('倒數 3 秒；背景模式不必切回遊戲。F8 可停止。' if started else '測試尚未開始；請檢查校準或現有工作狀態。')

    def show_record(self):
        selected=self.results.selection()
        if not selected:return
        r=self.records[selected[0]]
        self.record_detail.set(f"條件：{r.get('condition','')} ｜ 前景：{r.get('foreground_before','?')} → {r.get('foreground_after','?')}\n游標：{r.get('cursor_before','?')} → {r.get('cursor_after','?')} ｜ 手牌定位：{r.get('hand_position_source','?')}\n尺寸：{r.get('client_rect',[])[2:]} ｜ 最小化：{r.get('minimized_before','?')} → {r.get('minimized_after','?')}\n操作：{r.get('plan',[])}")

    def tick(self):
        if not self.root.winfo_exists():return
        for record in self.panel.test_results[self.seen:]:
            key=record['test_id']
            self.records[key]=record
            result='日誌已確認' if record.get('confirmed') else ('已送出，日誌未確認' if record.get('sent') else '未完成送出')
            result+='；'+record.get('error','') if record.get('error') else ''
            self.results.insert('',0,iid=key,values=(time.strftime('%H:%M:%S',time.localtime(record['time'])),record['backend'],record.get('action',{}).get('description',''),result))
            self.results.selection_set(key)
            self.status.set(result)
        self.seen=len(self.panel.test_results)
        if self.panel.worker and self.panel.worker.is_alive():
            self.status.set(self.panel.notice)
        self.root.after(200,self.tick)

    def annotate(self,result):
        selected=self.results.selection()
        if not selected:
            self.status.set('請先選取一筆測試結果。')
            return
        record={'test_id':selected[0],'time':time.time(),'visual_result':result,'notes':self.notes.get()}
        with (self.panel.root_path/'test-observations.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(record,ensure_ascii=False)+'\n')
        self.status.set('目視結果已儲存：'+result)
