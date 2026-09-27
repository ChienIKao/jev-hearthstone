"""Recognize Hearthstone menus and select the configured ranked deck."""
import re
import time
from pathlib import Path

import numpy as np


def normalized(text):
    return re.sub(r'[\s《》<>]', '', text).casefold()


class MenuVision:
    def __init__(self):
        from rapidocr import RapidOCR
        self.engine = RapidOCR()

    def arrows(self, frame):
        import cv2
        template=cv2.imread(str(Path(__file__).parent/'assets/menu-next.png'))
        if template is None:
            raise ValueError('缺少牌組翻頁圖樣')
        height,width=frame.shape[:2]
        image=cv2.resize(np.ascontiguousarray(frame[:,:,::-1]),(round(width*1080/height),1080))
        offset=(image.shape[1]-1920)//2
        points={}
        for direction,left,right in [('next',1080,1180),('previous',280,380)]:
            a,b=max(0,left+offset),min(image.shape[1],right+offset)
            crop=image[440:610,a:b]
            target=template if direction=='next' else cv2.flip(template,1)
            if crop.shape[1]<target.shape[1]:
                continue
            score=cv2.matchTemplate(crop,target,cv2.TM_CCOEFF_NORMED)
            _,confidence,_,position=cv2.minMaxLoc(score)
            if confidence>.87:
                points[direction]=[(a+position[0]+target.shape[1]/2)/image.shape[1],
                                   (440+position[1]+target.shape[0]/2)/1080]
        return points

    def read(self, frame):
        # Android frames are RGB; RapidOCR's ndarray interface expects BGR.
        result = self.engine(np.ascontiguousarray(frame[:,:,::-1]))
        height,width = frame.shape[:2]
        if result.boxes is None:
            return []
        return [dict(text=text, score=float(score),
                     point=[float(np.mean(box[:,0]))/width,float(np.mean(box[:,1]))/height])
                for text,score,box in zip(result.txts,result.scores,result.boxes) if score>=.8]


def find(labels, text, region=(0,0,1,1)):
    x1,y1,x2,y2=region
    matches=[label for label in labels if normalized(label['text'])==normalized(text)
             and x1<=label['point'][0]<=x2 and y1<=label['point'][1]<=y2]
    return matches[0] if len(matches)==1 else None


def menu_step(labels, profile, completed=False):
    def click(label, message):
        return dict(kind='click', point=label['point'], message=message)
    standard=find(labels,'標準')
    wild=find(labels,'開放')
    if standard and wild and find(labels,'休閒模式'):
        label=standard if profile['mode']=='standard' else wild
        # The caption is below the clickable emblem. Touching the caption
        # dismisses the chooser without changing the selected format.
        x,y=label['point']
        return dict(kind='click',point=[x,y-.2],message='切換對戰模式')
    title=find(labels,'標準對戰') or find(labels,'開放對戰')
    if title and find(labels,'選擇套牌'):
        expected='標準對戰' if profile['mode']=='standard' else '開放對戰'
        if normalized(title['text'])!=normalized(expected):
            return dict(kind='click', point=[.733,.05], message='開啟模式選單')
        selected=find(labels,profile['name'],(.63,.55,.84,.72))
        start=find(labels,'開始',(.63,.72,.85,.93))
        if selected and start:
            return dict(kind='queue',point=start['point'],message='使用 '+profile['name']+' 開始排隊')
        deck=find(labels,profile['name'],(.15,.18,.59,.82))
        if deck:
            return click(deck,'選擇牌組：'+profile['name'])
        return dict(kind='deck_missing',message='目前頁面找不到牌組：'+profile['name'])
    main=find(labels,'爐石戰記')
    if main and find(labels,'英雄戰場'):
        return click(main,'進入對戰選單')
    if completed:
        for label in labels:
            if any(word in normalized(label['text']) for word in ('輕點以繼續','點擊繼續','點擊任意','勝利','敗北','落敗','戰敗')):
                return dict(kind='click',point=[.5,.5],message='離開對局結算畫面')
    return dict(kind='wait',message='等待遊戲畫面或配對')


class RankedNavigator:
    def __init__(self, device, progress, stop):
        self.device,self.progress,self.stop=device,progress,stop
        self.vision=MenuVision()

    def enter_game(self, hands, profile, previous_game=None):
        deadline=time.monotonic()+300
        queued=False
        missing_since=None
        searching_forward=False
        pages_seen=set()
        stale_board_since=None
        while not self.stop.is_set() and time.monotonic()<deadline:
            state=hands.observe()
            if state.get('game_state')=='RUNNING' and state.get('game_serial')!=previous_game:
                return state
            frame=self.device.frame()
            labels=self.vision.read(frame)
            board_visible=find(labels,'敵方回合',(.73,.35,.87,.56)) or find(labels,'結束回合',(.73,.35,.87,.56))
            if queued and board_visible:
                stale_board_since=stale_board_since or time.monotonic()
                if time.monotonic()-stale_board_since>8:
                    raise ValueError('畫面已進入新對局，但 Power.log 未更新；停止自動操作，請檢查日誌')
            else:
                stale_board_since=None
            if queued:
                self.stop.wait(1)
                continue
            step=menu_step(labels,profile,state.get('game_state')=='COMPLETE')
            self.progress(step['message'])
            if step['kind']=='deck_missing':
                arrows=self.vision.arrows(frame)
                if not searching_forward and 'previous' in arrows:
                    step=dict(kind='click',point=arrows['previous'],message='向前尋找牌組')
                else:
                    searching_forward=True
                    page=tuple(sorted(normalized(item['text']) for item in labels
                                      if .15<item['point'][0]<.59 and .18<item['point'][1]<.82))
                    if page in pages_seen or 'next' not in arrows:
                        raise ValueError('找不到牌組：'+profile['name']+'；請確認遊戲內名稱與模式')
                    pages_seen.add(page)
                    step=dict(kind='click',point=arrows['next'],message='翻頁尋找牌組')
                missing_since=missing_since or time.monotonic()
                if time.monotonic()-missing_since>60:
                    raise ValueError(step['message'])
            else:
                missing_since=None
            if step['kind'] in ('click','queue'):
                def check():
                    if self.stop.is_set():
                        raise ValueError('已停止')
                self.device.execute([dict(op='click',point=step['point'])],check)
                queued=queued or step['kind']=='queue'
                self.stop.wait(2)
            else:
                self.stop.wait(1)
        if self.stop.is_set():
            return None
        raise ValueError('等待進入對局逾時；已停止排隊')
