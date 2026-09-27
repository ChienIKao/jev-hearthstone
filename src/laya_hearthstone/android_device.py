"""ADB transport for device-local Hearthstone input and capture."""
from laya_hearthstone.paths import ROOT
import math
from functools import lru_cache
from pathlib import Path
import struct
import subprocess
import time

import numpy as np


@lru_cache(maxsize=1)
def _turn_banner():
    import cv2
    return cv2.imread(str(ROOT/'assets/turn-banner.png'),cv2.IMREAD_GRAYSCALE)


@lru_cache(maxsize=1)
def _opening_zero_mana():
    import cv2
    return cv2.imread(str(ROOT/'assets/opening-zero-mana.png'),cv2.IMREAD_GRAYSCALE)


class AndroidDevice:
    def __init__(self, adb_path, serial):
        self.adb_path = str(adb_path)
        self.serial = serial

    def command(self, *args, timeout=15):
        result = subprocess.run(
            [self.adb_path, '-s', self.serial, *map(str, args)],
            capture_output=True, timeout=timeout,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode:
            raise RuntimeError(result.stderr.decode('utf-8', errors='replace').strip())
        return result.stdout

    def connect(self):
        if self.serial.startswith(('127.0.0.1:', 'localhost:')):
            self.command('connect', self.serial)
        if self.command('get-state').strip()!=b'device':
            raise ValueError('Android device is not connected')

    def capture(self, path=None):
        png = self.command('exec-out', 'screencap', '-p')
        if len(png) < 24 or png[:8] != b'\x89PNG\r\n\x1a\n':
            raise ValueError('ADB did not return a PNG screenshot')
        size = struct.unpack('>II', png[16:24])
        if min(size) <= 0:
            raise ValueError('Invalid Android screen dimensions')
        if path is not None:
            Path(path).write_bytes(png)
        return size

    def frame(self):
        try:
            raw = self.command('exec-out','screencap',timeout=3)
        except subprocess.TimeoutExpired:
            import cv2
            png=self.command('exec-out','screencap','-p',timeout=3)
            decoded=cv2.imdecode(np.frombuffer(png,dtype=np.uint8),cv2.IMREAD_COLOR)
            if decoded is None:
                raise ValueError('ADB did not return a valid fallback frame')
            return cv2.cvtColor(decoded,cv2.COLOR_BGR2RGB)
        if len(raw)<12:
            raise ValueError('Incomplete Android frame')
        width,height,format_code = struct.unpack('<III',raw[:12])
        if format_code not in (1,2) or not 0<width<=8192 or not 0<height<=8192:
            raise ValueError('Unsupported Android raw frame format')
        offset = len(raw)-width*height*4
        if offset not in (12,16):
            raise ValueError('Incomplete Android pixel data')
        return np.frombuffer(raw,dtype=np.uint8,offset=offset).reshape(height,width,4)[:,:,:3]

    @staticmethod
    def scene_sample(frame):
        height,width=frame.shape[:2]
        # Measure each region independently so a moving hand card is not
        # diluted by the empty board. Hero skins animate even while idle.
        regions=((.30,.87,.65,.99),(.28,.29,.73,.66),(.68,.25,.80,.65))
        return tuple(frame[int(y1*height):int(y2*height):8,
                           int(x1*width):int(x2*width):8].astype(np.int16)
                     for x1,y1,x2,y2 in regions)

    @staticmethod
    def turn_ready(frame, point, opening=False):
        import cv2
        # The turn button lights up before the turn-start overlay releases input.
        template=_turn_banner()
        height,width=frame.shape[:2]
        if opening:
            zero=_opening_zero_mana()
            if zero is None:
                raise ValueError('缺少開局法力辨識圖樣')
            scene=cv2.resize(frame,(1920,1080))
            mana=cv2.cvtColor(scene[970:1035,1205:1325],cv2.COLOR_RGB2GRAY)
            if cv2.minMaxLoc(cv2.matchTemplate(mana,zero,cv2.TM_CCOEFF_NORMED))[1]>.85:
                return False
        if height>=200 and template is not None:
            scene=cv2.resize(frame,(round(width*1080/height),1080))
            center=scene.shape[1]//2
            crop=cv2.cvtColor(scene[400:650,max(0,center-350):center+350],cv2.COLOR_RGB2GRAY)
            if crop.shape[1]>=template.shape[1] and cv2.minMaxLoc(cv2.matchTemplate(crop,template,cv2.TM_CCOEFF_NORMED))[1]>.8:
                return False
        height,width=frame.shape[:2]
        x,y=(round(point[0]*width),round(point[1]*height))
        rx,ry=max(1,round(height*.035)),max(1,round(height*.012))
        patch=frame[max(0,y-ry):min(height,y+ry),max(0,x-rx):min(width,x+rx)].astype(np.int16)
        if not patch.size:
            return False
        red,green,blue=patch[:,:,0],patch[:,:,1],patch[:,:,2]
        # The enabled yellow/green button is distinct from the grey opponent
        # turn button, which can remain visible long after Power.log advances.
        enabled=(green>100)&(green>blue*1.5)&((red>120)|(green>red*1.1))
        return np.mean(enabled)>.4

    @staticmethod
    def mulligan_ready(frame, point):
        height,width=frame.shape[:2]
        x,y=round(point[0]*width),round(point[1]*height)
        rx,ry=max(1,round(height*.035)),max(1,round(height*.012))
        patch=frame[max(0,y-ry):min(height,y+ry),max(0,x-rx):min(width,x+rx)].astype(np.int16)
        if not patch.size:
            return False
        red,green,blue=patch[:,:,0],patch[:,:,1],patch[:,:,2]
        return np.mean((blue>150)&(green>100)&(blue>red*1.15))>.3

    def wait_stable(self, check=lambda:None, timeout=30, ready=None,
                    minimum=.4, quiet=.4):
        started=time.monotonic()
        stable_since=started
        previous=None
        read_failures=0
        while time.monotonic()-started<timeout:
            check()
            try:
                frame=self.frame()
            except subprocess.TimeoutExpired as exc:
                read_failures+=1
                if read_failures>=2:
                    raise ValueError('連續兩次無法取得 MuMu 畫面，已停止等待') from exc
                previous=None
                stable_since=time.monotonic()
                check()
                time.sleep(.25)
                continue
            read_failures=0
            sample=self.scene_sample(frame)
            now=time.monotonic()
            moving=previous is None or any(
                a.shape!=b.shape or np.mean(np.max(np.abs(a-b),axis=2)>30)>limit
                for a,b,limit in zip(sample,previous or sample,(.06,.05,.04)))
            if moving or (ready is not None and not ready(frame)):
                stable_since=now
            previous=sample
            if now-started>=minimum and now-stable_since>=quiet:
                self.last_frame=frame
                return now-started
            time.sleep(.05)
        raise ValueError('Android game animation has not settled; no input sent')

    @staticmethod
    def point(point, size):
        if len(point) != 2 or not all(math.isfinite(v) and .01 <= v <= .99 for v in point):
            raise ValueError('Target is outside the Android screen')
        return tuple(round(v * extent) for v, extent in zip(point, size))

    def execute(self, plan, check=lambda: None, wait=None, size=None):
        wait = wait or time.sleep
        fast=size is not None
        size = size or self.capture()
        commands = []
        for step in plan:
            if step['op'] == 'click':
                commands.append(('tap', *self.point(step['point'], size)))
            elif step['op'] == 'drag':
                commands.append(('swipe', *self.point(step['from'], size),
                                 *self.point(step['to'], size), 450))
            elif step['op'] == 'wait':
                seconds = step['seconds']
                if not math.isfinite(seconds) or not 0 <= seconds <= 10:
                    raise ValueError('Invalid input wait')
                commands.append(('wait', seconds))
            else:
                raise ValueError('Unsupported input operation')
        for command in commands:
            check()
            if command[0] == 'wait':
                wait(command[1])
            else:
                if fast:
                    frame=self.frame()
                    current_size=(frame.shape[1],frame.shape[0])
                else:
                    current_size=self.capture()
                if current_size != size:
                    raise ValueError('Android screen rotated or resized; input stopped')
                self.command('shell', 'input', 'touchscreen', *command)
            check()
        return size
