"""Experimental window-message input. Never moves the system cursor."""
import time


class BackgroundInput:
    def __init__(self, hwnd, post=None, sleep=time.sleep):
        self.hwnd=hwnd
        self.sleep=sleep
        if post is None:
            import ctypes as c
            from ctypes import wintypes as w
            user=c.WinDLL('user32',use_last_error=True)
            user.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
            user.PostMessageW.restype=w.BOOL
            def post(hwnd,msg,buttons,position):
                if not user.PostMessageW(hwnd,msg,buttons,position):
                    raise OSError(c.get_last_error(),'PostMessage failed')
        self.post=post

    def send(self,msg,point,buttons=0):
        x,y=point
        if not 0<=x<=32767 or not 0<=y<=32767:
            raise ValueError('背景輸入座標超出範圍')
        self.post(self.hwnd,msg,buttons,(y<<16)|x)

    def click(self,point,check):
        check()
        self.send(0x200,point)
        self.send(0x201,point,1)
        try:
            self.sleep(.05)
        finally:
            self.send(0x202,point)

    def drag(self,start,end,check):
        check()
        self.send(0x200,start)
        self.send(0x201,start,1)
        current=start
        try:
            self.sleep(.08)
            for i in range(1,17):
                check()
                current=tuple(round(a+(b-a)*i/16) for a,b in zip(start,end))
                self.send(0x200,current,1)
                self.sleep(.025)
        finally:
            self.send(0x202,current)
