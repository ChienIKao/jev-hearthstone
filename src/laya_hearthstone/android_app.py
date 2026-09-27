"""MuMu control panel. Game input runs only after an explicit action button."""
import copy
import json
import math
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk

from laya_hearthstone.advisor import Decider, fingerprint
from laya_hearthstone.android_device import AndroidDevice
from laya_hearthstone.android_hands import AndroidHands, StateChanged
from laya_hearthstone.android_layout import default_layout
from laya_hearthstone.choices import pending_choice
from laya_hearthstone.executor import DEFAULT_LAYOUT
from laya_hearthstone.deck_profiles import DeckProfiles, new_profile
from laya_hearthstone.geometry import resized_layout
from laya_hearthstone.mulligan import opening_cards
from laya_hearthstone.strategy import get_actions, sides
from laya_hearthstone.ranked_session import RankedSession

from laya_hearthstone.paths import ROOT


class AndroidPanel:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Laya 爐石助手 — MuMu')
        self.root.geometry('1000x900')
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.busy = False
        self.closing = False
        self.hands = None
        self.state = None
        self.actions = {}
        self.cards = {c['id']: c for c in json.loads((ROOT/'data/cards.zhTW.json').read_text(encoding='utf-8'))}
        self.profiles = DeckProfiles(ROOT/'deck-profiles.json')
        self.decider = Decider(self.cards, profile=self.profiles.selected())
        self.adb = tk.StringVar(value='D:/MuMu Player 12/nx_main/adb.exe')
        self.serial = tk.StringVar(value='127.0.0.1:16384')
        self.status = tk.StringVar(value='觀察模式。連線與更新畫面不會操作遊戲。')
        self.status.trace_add('write', self.log_status)
        self.summary = tk.StringVar(value='尚未連線')
        from laya_hearthstone.panel_view import build_panel
        build_panel(self)
        self.root.bind('<Escape>', lambda _: self.cancel())
        self.root.bind('<F8>', lambda _: self.cancel())
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.after(100, self.tick)

    def log_status(self, *_):
        if not hasattr(self, 'run_log'):
            return
        from datetime import datetime
        message=self.status.get()
        if message==getattr(self,'last_log_message',None):
            return
        self.last_log_message=message
        self.run_log.configure(state='normal')
        self.run_log.insert('end',datetime.now().strftime('%H:%M:%S')+'  '+message+'\n')
        if int(self.run_log.index('end-1c').split('.')[0])>300:
            self.run_log.delete('1.0','2.0')
        self.run_log.see('end')
        self.run_log.configure(state='disabled')

    def update_deck_picker(self):
        self.deck_picker['values'] = [p['name']+' · '+('標準' if p['mode']=='standard' else '開放') for p in self.profiles.profiles]
        for index,profile in enumerate(self.profiles.profiles):
            if profile['id']==self.profiles.selected_id:
                self.deck_picker.current(index)
                break

    def select_deck(self, event=None):
        if self.busy:
            self.update_deck_picker()
            return
        index=self.deck_picker.current()
        if index>=0:
            self.profiles.select(self.profiles.profiles[index]['id'])
            self.decider.profile=self.profiles.selected()
            self.status.set('已選擇牌組；Laya 將使用這套牌組的換牌、打法與 combo 思路。')

    def import_reference(self, meta=False):
        if self.busy:
            return
        profile=self.profiles.selected()
        if not profile:
            self.status.set('請先新增並選擇牌組。')
            return
        from laya_hearthstone.hsreplay_import import parse_deck_page, parse_meta_page
        popup=tk.Toplevel(self.root)
        popup.title('匯入 HSReplay 環境榜' if meta else '匯入 HSReplay 留牌參考')
        body=ttk.Frame(popup,padding=16)
        body.pack(fill='both',expand=True)
        instructions='在 HSReplay 環境榜的「強度列表」全選、複製，再貼到下方。' if meta else '在單一牌組頁的「留牌指南」全選、複製，再貼到下方。'
        ttk.Label(body,text=instructions+'\n請填寫網站實際選取的篩選範圍；匯入前會顯示摘要。').pack(anchor='w')
        if not meta:
            ttk.Label(body,text='參考模式：'+('標準' if profile['mode']=='standard' else '開放')+'，請確認來源牌組模式相同。').pack(anchor='w')
        fields={}
        for key,label,default in [('url','來源網址','https://hsreplay.net/zh-hant/meta/' if meta else profile.get('source_url','')),
                                  ('rank','分段／伺服器（例如：青銅到黃金／所有伺服器）',''),
                                  ('period','時間範圍（例如：過去 30 天）','')]:
            ttk.Label(body,text=label).pack(anchor='w',pady=(8,0))
            fields[key]=tk.StringVar(value=default)
            ttk.Entry(body,textvariable=fields[key],width=80,state='readonly' if meta and key=='url' else 'normal').pack(fill='x')
        content=tk.Text(body,width=80,height=13,wrap='word',bg='#252525',fg='#dedede',insertbackground='#dedede')
        content.pack(fill='both',expand=True,pady=12)
        guard=tk.BooleanVar(value=True)
        if not meta:
            ttk.Checkbutton(body,text='校正明顯留牌：高留牌率低費牌保留、低留牌率高費牌換掉',variable=guard).pack(anchor='w')
        notice=tk.StringVar()
        ttk.Label(body,textvariable=notice,wraplength=660).pack(anchor='w')
        parsed=[None]
        def invalidate(*_):
            parsed[0]=None
            apply.configure(state='disabled')
        for value in fields.values():value.trace_add('write',invalidate)
        guard.trace_add('write',invalidate)
        def text_changed(_):
            if content.edit_modified():
                invalidate()
                content.edit_modified(False)
        content.bind('<<Modified>>',text_changed)
        def preview():
            try:
                if meta:
                    data=parse_meta_page(content.get('1.0','end'),fields['rank'].get(),fields['period'].get())
                    parsed[0]=data
                    notice.set(f"辨識 {len(data['rows'])} 種環境牌型；{data['rank_range']}；{data['time_range']}。\n保存後可在環境榜快照查看。")
                    apply.configure(state='normal')
                    return
                data=parse_deck_page(content.get('1.0','end'),fields['url'].get(),fields['rank'].get(),fields['period'].get(),profile['mode'],self.cards)
                data['guard_mulligan']=guard.get()
                parsed[0]=data
                names='、'.join(r['name'] for r in sorted(data['cards'],key=lambda r:r['keep_percentage'],reverse=True)[:5])
                notice.set(f"辨識 {len(data['cards'])} 種、{sum(r['count'] for r in data['cards'])} 張牌。\n留牌率最高：{names}\n此為參考牌表；不會變更遊戲內牌組或覆蓋你的打法筆記。")
                apply.configure(state='normal')
            except ValueError as exc:
                parsed[0]=None
                apply.configure(state='disabled')
                notice.set(str(exc))
        def save():
            if parsed[0] is None:
                return
            try:
                if meta:
                    from laya_hearthstone.snapshot_io import publish_text
                    if not publish_text(ROOT/'data/hsreplay-meta.json',json.dumps(parsed[0],ensure_ascii=False,indent=2)):
                        raise ValueError('無法保存環境榜')
                    self.status.set('環境榜快照已保存。')
                    popup.destroy()
                    return
                self.profiles.save(dict(profile,reference_data=parsed[0],source_url=parsed[0]['source_url']))
            except (ValueError,OSError) as exc:
                notice.set(str(exc))
                return
            self.decider.profile=self.profiles.selected()
            self.status.set('HSReplay 留牌參考已保存；下次起手選牌會帶入相關卡牌統計。')
            popup.destroy()
        row=ttk.Frame(body);row.pack(fill='x',pady=(12,0))
        ttk.Button(row,text='解析與預覽',command=preview).pack(side='left')
        apply=ttk.Button(row,text='保存參考',command=save,state='disabled')
        apply.pack(side='right')
        popup.transient(self.root)
        popup.grab_set()

    def show_meta(self):
        path=ROOT/'data/hsreplay-meta.json'
        if not path.exists():
            self.status.set('尚未匯入環境榜快照。')
            return
        data=json.loads(path.read_text(encoding='utf-8'))
        popup=tk.Toplevel(self.root);popup.title('HSReplay 環境榜快照')
        body=ttk.Frame(popup,padding=16);body.pack(fill='both',expand=True)
        ttk.Label(body,text=f"{data['rank_range']} · {data['time_range']}\n匯入：{data['imported_at'][:19]} UTC · 保存快照，非即時更新\n{data['source_url']}").pack(anchor='w',pady=(0,12))
        table=ttk.Treeview(body,columns=('tier','name','win','matches'),show='headings',height=18)
        for key,label,width in [('tier','Tier',55),('name','牌型',220),('win','勝率',90),('matches','樣本',100)]:
            table.heading(key,text=label);table.column(key,width=width)
        for row in data['rows']:
            table.insert('','end',values=(row['tier'],row['name'],str(row['winrate'])+'%',f"{row['matches']:,}"))
        scroll=ttk.Scrollbar(body,orient='vertical',command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');table.pack(fill='both',expand=True)

    def show_reference(self):
        profile=self.profiles.selected() or {}
        reference=profile.get('reference_data')
        if not reference:
            self.status.set('目前牌組尚未匯入 HSReplay 留牌參考。')
            return
        popup=tk.Toplevel(self.root);popup.title('目前牌組的留牌參考')
        body=ttk.Frame(popup,padding=16);body.pack(fill='both',expand=True)
        ttk.Label(body,text=f"{profile['name']} · {reference['rank_range']} · {reference['time_range']}\n匯入：{reference['imported_at'][:19]} UTC\n{reference['source_url']}").pack(anchor='w',pady=(0,12))
        table=ttk.Treeview(body,columns=('name','keep','win'),show='headings',height=16)
        for key,label in [('name','卡牌'),('keep','留牌率'),('win','起手勝率')]:table.heading(key,text=label)
        for row in sorted(reference['cards'],key=lambda r:r['keep_percentage'],reverse=True):
            table.insert('','end',values=(row['name'],str(row['keep_percentage'])+'%',str(row['mulligan_winrate'])+'%'))
        table.pack(fill='both',expand=True)
        ttk.Label(body,text='參考牌表的觀察統計；未確認與遊戲內牌組完全相同。').pack(anchor='w',pady=8)
        guard=tk.BooleanVar(value=reference.get('guard_mulligan',False))
        def change_guard():
            if self.busy:return
            updated=dict(reference,guard_mulligan=guard.get())
            self.profiles.save(dict(profile,reference_data=updated))
            reference.update(updated)
            self.decider.profile=self.profiles.selected()
            self.status.set('留牌統計校正已'+('啟用' if guard.get() else '停用'))
        ttk.Checkbutton(body,text='統計校正（啟用時可覆蓋模型留牌；自訂策略可停用）',variable=guard,command=change_guard).pack(anchor='w')
        def remove():
            if self.busy:return
            self.profiles.save(dict(profile,reference_data=None))
            self.decider.profile=self.profiles.selected()
            self.status.set('已移除目前牌組的留牌參考。')
            popup.destroy()
        ttk.Button(body,text='移除這份參考',command=remove).pack(anchor='e')
        popup.transient(self.root)
        popup.grab_set()

    def edit_deck(self, create=False):
        if self.busy:
            return
        profile=new_profile() if create else self.profiles.selected()
        if profile is None:
            profile=new_profile()
        popup=tk.Toplevel(self.root)
        popup.title('牌組與打法')
        popup.geometry('760x640')
        popup.minsize(680,560)
        body=ttk.Frame(popup,padding=12)
        body.pack(fill='both',expand=True)
        values={}
        for key,label in [('name','遊戲內牌組名稱'),('deck_code','牌組代碼（選填，僅保存，不會自動匯入）'),('source_url','HSReplay 來源網址（選填）')]:
            ttk.Label(body,text=label).pack(anchor='w')
            values[key]=tk.StringVar(value=profile.get(key,''))
            ttk.Entry(body,textvariable=values[key],width=78).pack(fill='x',pady=(0,6))
        mode=tk.StringVar(value='標準' if profile['mode']=='standard' else '開放')
        ttk.Combobox(body,textvariable=mode,values=['標準','開放'],state='readonly').pack(anchor='w',pady=4)
        notes={}
        notebook=ttk.Notebook(body)
        notebook.pack(fill='both',expand=True,pady=(12,8))
        for key,title,label in [('mulligan','換牌','必留、必換、先後手或對手職業差異'),('game_plan','打法','勝利方式、前中後期打法、要保留的資源'),('combos','Combo','需要哪些牌、操作順序、觸發條件'),('meta_notes','環境','資料日期、分段、常見對手與對局策略')]:
            page=ttk.Frame(notebook,padding=10)
            notebook.add(page,text=title)
            ttk.Label(page,text=label).pack(anchor='w',pady=(0,8))
            text=tk.Text(page,width=60,height=10,wrap='word',undo=True,font=('Microsoft JhengHei UI',10),bg='#252525',fg='#dedede',insertbackground='#dedede',relief='flat',padx=10,pady=8)
            text.insert('1.0',profile.get(key,''))
            text.pack(fill='both',expand=True,pady=(0,6))
            notes[key]=text
        error=tk.StringVar()
        ttk.Label(body,textvariable=error,foreground='red').pack(anchor='w')
        def save():
            updated=dict(profile,**{k:v.get() for k,v in values.items()},
                         **{k:v.get('1.0','end-1c') for k,v in notes.items()},
                         mode='standard' if mode.get()=='標準' else 'wild')
            try:
                self.profiles.save(updated)
            except (ValueError,OSError) as exc:
                error.set(str(exc))
                return
            self.decider.profile=self.profiles.selected()
            self.update_deck_picker()
            self.status.set('牌組打法已儲存，下一次決策開始套用。')
            popup.destroy()
        ttk.Button(body,text='儲存並使用',command=save).pack(anchor='e')
        popup.transient(self.root)
        popup.grab_set()

    def job(self, description, work):
        if self.busy:
            return
        self.busy = True
        self.refresh_controls()
        self.stop.clear()
        self.status.set(description)
        serial=self.hands.device.serial if self.hands else self.serial.get()
        def run():
            try:
                from laya_hearthstone.device_lease import device_lease
                with device_lease(serial):
                    result=work()
                self.events.put(('done',result))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=run, daemon=True).start()

    def connect(self):
        adb, serial = self.adb.get(), self.serial.get()
        def work():
            layout_path = ROOT/'android-calibration.json'
            layout = json.loads(layout_path.read_text(encoding='utf-8')) if layout_path.exists() else default_layout()
            device = AndroidDevice(adb, serial)
            device.connect()
            self.hands = AndroidHands(device, layout, self.cards, ROOT/'data/android-evidence')
            return self.snapshot('已連線，觀察模式')
        self.job('連線並讀取局面…', work)

    def snapshot(self, message):
        state = self.hands.observe()
        try:
            actions, _ = get_actions(state, self.cards)
        except ValueError as exc:
            actions = {}
            message += '；'+str(exc)
        path = ROOT/'data/android-panel.png'
        size = self.hands.device.capture(path)
        return dict(state=state, actions=actions, path=path, size=size, message=message)

    def refresh(self):
        if self.hands:
            self.job('讀取局面…', lambda: self.snapshot('局面已更新'))

    def execute_selected(self):
        selected = self.table.selection()
        if not self.hands or not selected or self.busy:
            return
        action, before = copy.deepcopy(self.actions[selected[0]]), copy.deepcopy(self.state)
        def work():
            result = self.hands.run(action, before, self.stop.is_set)
            return self.snapshot('日誌已確認：'+action['description'] if result['confirmed'] else '未確認，已停止：'+result.get('error',''))
        self.job('執行所選動作…', work)

    def decide(self):
        if not self.hands:
            return
        def work():
            state = self.hands.observe()
            actions, _ = get_actions(state, self.cards)
            decision = self.decider.decide(state)
            if self.stop.is_set():
                raise ValueError('已停止，未送出模型決策')
            action = actions[decision['action']['key']]
            result = self.hands.run(action, state, self.stop.is_set)
            return self.snapshot('日誌已確認：'+action['description'] if result['confirmed'] else '未確認，已停止')
        self.job('Laya 思考中；首次載入較久…', work)

    def cancel(self):
        self.stop.set()
        self.status.set('已要求停止；等待目前指令返回。')

    def continuous(self):
        if not self.hands:
            return
        def work():
            first = self.hands.observe()
            game = first.get('game_serial')
            if first.get('game_state') != 'RUNNING':
                    raise ValueError('請先進入對局')
            while not self.stop.is_set():
                state = self.hands.observe()
                if state.get('game_serial') != game or state.get('game_state') != 'RUNNING':
                    return self.snapshot('本局已結束，停止接手')
                own, _ = sides(state)
                choosing = pending_choice(state) or own.get('player_tags',{}).get('MULLIGAN_STATE')=='INPUT'
                if not choosing and (own.get('current_player')!='1' or not state.get('options_fresh')):
                    self.events.put(('progress','等待回合與完整動作清單…'))
                    self.stop.wait(.5)
                    continue
                actions, _ = get_actions(state,self.cards)
                self.events.put(('progress','Laya 正在選擇下一步…'))
                decision = self.decider.decide(state)
                if self.stop.is_set():
                    break
                action = actions[decision['action']['key']]
                try:
                    result = self.hands.run(action,state,self.stop.is_set)
                except StateChanged:
                    continue
                if not result['confirmed']:
                    return self.snapshot('操作未確認，已停止：'+action['description'])
                self.events.put(('progress','已確認：'+action['description']))
                self.stop.wait(.05)
            return self.snapshot('已停止接手')
        self.job('開始接手目前對局…',work)

    def ranked(self):
        if self.busy:
            return
        if not self.hands:
            self.status.set('請先按「連線」，確認 MuMu 與遊戲畫面後開始爬排位。')
            return
        profile=self.profiles.selected()
        try:
            limit=int(self.game_limit.get())
            if limit<0 or profile is None:
                raise ValueError()
        except ValueError:
            self.status.set('請先選擇牌組，並填寫非負整數局數（0＝持續）')
            return
        def work():
            session=RankedSession(self.hands,self.decider,profile,self.stop,
                                  lambda message:self.events.put(('progress',message)),limit)
            return self.snapshot(session.run())
        self.job('啟動連續爬牌：'+profile['name'],work)

    def tick(self):
        try:
            kind, result = self.events.get_nowait()
            if kind == 'progress':
                if not self.stop.is_set():
                    self.status.set(result)
                self.root.after(100,self.tick)
                return
            self.busy = False
            self.refresh_controls()
            if self.closing:
                self.root.destroy()
                return
            if kind == 'error':
                self.status.set(result)
            else:
                self.state, self.actions = result['state'], result['actions']
                from laya_hearthstone.perception import describe_observation
                self.observation_text.configure(state='normal')
                self.observation_text.delete('1.0','end')
                self.observation_text.insert('1.0',describe_observation(self.state,self.cards))
                self.observation_text.configure(state='disabled')
                self.size = result['size']
                self.status.set(result['message'])
                self.summary.set(f"回合 {self.state.get('turn')} · {self.state.get('step')} · 裝置 {self.hands.device.serial}")
                self.table.delete(*self.table.get_children())
                for key, action in self.actions.items():
                    self.table.insert('', 'end', iid=key, values=(action['description'],))
                from PIL import Image
                with Image.open(result['path']) as raw:
                    self.preview_image=raw.copy()
                self.render_preview()
        except queue.Empty:
            pass
        self.root.after(100, self.tick)

    def render_preview(self, event=None):
        if not hasattr(self,'preview_image'):
            return
        width,height=self.canvas.winfo_width(),self.canvas.winfo_height()
        if width<10 or height<10:
            return
        from PIL import ImageTk
        preview=self.preview_image.copy()
        preview.thumbnail((width-4,height-4))
        self.photo=ImageTk.PhotoImage(preview)
        self.scale=self.size[0]/self.photo.width()
        self.canvas.delete('all')
        self.canvas.create_image(width/2,height/2,anchor='center',image=self.photo)

    def calibrate(self):
        if self.busy or self.state is None:
            return
        if not hasattr(self,'photo'):
            self.status.set('請先開啟遊戲畫面分頁，再進行校準。')
            return
        state = copy.deepcopy(self.state)
        own, enemy = sides(state)
        packet = pending_choice(state)
        tasks = []
        if own.get('player_tags',{}).get('MULLIGAN_STATE') == 'INPUT':
            cards, _ = opening_cards(state)
            tasks = [('mulligan_overrides', str(len(cards)), i, f'起手牌 {i+1}') for i in range(len(cards))]
            tasks.append(('mulligan_confirm', None, None, '確認按鈕'))
        elif packet:
            tasks = [('choice_overrides', str(len(packet['entities'])), i, f'候選 {i+1}') for i in range(len(packet['entities']))]
            if (packet.get('count_min'),packet.get('count_max'))!=(1,1):
                tasks.append(('choice_confirm',None,None,'選牌確認按鈕'))
        else:
            tasks = [(key,None,None,label) for key,label in [('hero_me','我方英雄'),('hero_enemy','敵方英雄'),('power_me','英雄能力'),('end_turn','結束回合'),('play_area','出牌空位')]]
            tasks += [('hand_overrides',str(len(own['hand'])),i,f'手牌 {i+1} 可見區域') for i in range(len(own['hand']))]
            for side, player in [('me',own),('enemy',enemy)]:
                tasks += [('board_overrides',f'{side}:{len(player["board"])}',i,f'{side} 場上卡牌 {i+1}') for i in range(len(player['board']))]
        layout = self.hands.layout
        updated = resized_layout(layout,*self.size) if layout.get('width') else copy.deepcopy(DEFAULT_LAYOUT)
        updated.update(width=self.size[0],height=self.size[1])
        popup = tk.Toplevel(self.root)
        popup.title('在截圖上校準；點擊不會送到遊戲')
        label = ttk.Label(popup,text='點選：'+tasks[0][3])
        label.pack()
        canvas = tk.Canvas(popup,width=self.photo.width(),height=self.photo.height())
        canvas.pack()
        canvas.create_image(0,0,anchor='nw',image=self.photo)
        index = [0]
        def clicked(event):
            point = [event.x*self.scale/self.size[0],event.y*self.scale/self.size[1]]
            if not all(.01 <= v <= .99 for v in point):
                return
            key, group, slot, _ = tasks[index[0]]
            if group is None:
                updated[key] = point
            else:
                values = updated.setdefault(key,{}).setdefault(group,[])
                if slot == 0:
                    values.clear()
                values.append(point)
            canvas.create_oval(event.x-4,event.y-4,event.x+4,event.y+4,fill='red')
            index[0] += 1
            if index[0] < len(tasks):
                label.configure(text='點選：'+tasks[index[0]][3])
                return
            popup.destroy()
            def save():
                latest = self.hands.observe()
                if fingerprint(latest) != fingerprint(state):
                    raise ValueError('校準期間局面已變更，請更新後重試')
                updated['confirmed'] = True
                (ROOT/'android-calibration.json').write_text(json.dumps(updated,indent=2),encoding='utf-8')
                self.hands.layout = updated
                return self.snapshot('校準已儲存')
            self.job('儲存校準…',save)
        canvas.bind('<Button-1>',clicked)
        popup.transient(self.root)
        popup.grab_set()

    def close(self):
        self.stop.set()
        if self.busy:
            self.closing = True
            self.status.set('等待輸入結束後關閉…')
        else:
            self.root.destroy()


if __name__ == '__main__':
    AndroidPanel().root.mainloop()
