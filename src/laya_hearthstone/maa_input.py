"""MaaFramework background input and pseudo-minimized capture."""
import time
import math


def align_plan(backend,make_plan,get_rect,stop_event):
    rect=get_rect()
    for _ in range(4):
        if stop_event.is_set():raise ValueError('已停止')
        width,height=rect[2:]
        plan=make_plan(width,height)
        first=plan[0].get('from',plan[0].get('point'))
        if not all(0.01<=v<=0.99 for v in first):raise ValueError('座標超出遊戲範圍')
        backend.hover((round(first[0]*width),round(first[1]*height)))
        if stop_event.wait(.2):raise ValueError('已停止')
        updated=get_rect()
        if updated[2:]==rect[2:]:
            return updated,make_plan(*updated[2:])
        rect=updated
    raise ValueError('跨螢幕縮放未穩定，未按下滑鼠')


class MaaTouchInput:
    def __init__(self,hwnd,method='anchored_touch'):
        self.method=method
        from maa.controller import Win32Controller
        from maa.define import MaaWin32InputMethodEnum as Input, MaaWin32ScreencapMethodEnum as Capture
        methods={'anchored_touch':Input.AnchoredTouch,'sendmessage_window':Input.SendMessageWithWindowPos,'sendmessage':Input.SendMessage,'maa_postmessage':Input.PostMessage}
        self.controller=Win32Controller(hwnd,screencap_method=Capture.FramePool,
                                        mouse_method=methods[method],keyboard_method=Input.PostMessage)
        self.controller.set_screenshot_use_raw_size(True)
        self._wait(self.controller.post_connection())

    @staticmethod
    def _wait(job):
        if not job.wait().succeeded:
            raise ValueError('MaaFramework 操作失敗，未切換其他輸入方式')

    def set_coordinate_space(self, width, height, get_size):
        self.coordinate_space=(width,height,get_size)

    def _point(self,point):
        space=getattr(self,'coordinate_space',None)
        if space is None:
            return point
        base_width,base_height,get_size=space
        width,height=get_size()
        if min(width,height,base_width,base_height)<=0:
            raise ValueError('遊戲尺寸無效')
        x=width/2+(point[0]-base_width/2)*height/base_height
        y=point[1]*height/base_height
        if not all(math.isfinite(v) for v in (x,y)) or not (.01*width<=x<=.99*width and .01*height<=y<=.99*height):
            raise ValueError('跨螢幕後座標超出遊戲範圍')
        return round(x),round(y)

    def _prepare_press(self,point,check):
        space=getattr(self,'coordinate_space',None)
        if space is None:
            return
        get_size=space[2]
        for _ in range(4):
            check()
            before=get_size()
            self._wait(self.controller.post_touch_move(*self._point(point)))
            time.sleep(.04)
            if get_size()==before:
                return
        raise ValueError('按下前視窗縮放仍在變動，未送出按下事件')

    def click(self,point,check):
        check()
        if getattr(self,'method',None)=='sendmessage_window':
            # Let the game's render/input loop observe both edges while the
            # window follows a user-controlled cursor between those edges.
            self._prepare_press(point,check)
            try:
                self._wait(self.controller.post_touch_down(*self._point(point)))
                for _ in range(6):
                    check()
                    self._wait(self.controller.post_touch_move(*self._point(point)))
                    time.sleep(.02)
            finally:
                self._wait(self.controller.post_touch_up())
            self._wait(self.controller.post_touch_move(*self._point(point)))
            time.sleep(.04)
        else:
            self._wait(self.controller.post_click(*point))
        check()

    def prepare_minimized(self):
        self._wait(self.controller.post_screencap())
        frame=self.controller.cached_image
        if frame is None or frame.size==0:
            raise ValueError('最小化視窗擷取失敗，未送出輸入')
        return frame.shape[1],frame.shape[0]

    def hover(self,point):
        self._wait(self.controller.post_touch_move(*point))

    def drag(self,start,end,check):
        check()
        self._prepare_press(start,check)
        try:
            self._wait(self.controller.post_touch_down(*self._point(start)))
            time.sleep(.08)
            for i in range(1,17):
                check()
                point=tuple(round(a+(b-a)*i/16) for a,b in zip(start,end))
                self._wait(self.controller.post_touch_move(*self._point(point)))
                time.sleep(.025)
        finally:
            self._wait(self.controller.post_touch_up())

    def close(self):
        self._wait(self.controller.post_inactive())
