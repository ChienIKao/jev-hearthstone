"""MaaFramework background input and pseudo-minimized capture."""
import time


class MaaTouchInput:
    def __init__(self,hwnd,method='anchored_touch'):
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

    def click(self,point,check):
        check()
        self._wait(self.controller.post_click(*point))
        check()

    def prepare_minimized(self):
        self._wait(self.controller.post_screencap())
        frame=self.controller.cached_image
        if frame is None or frame.size==0:
            raise ValueError('最小化視窗擷取失敗，未送出輸入')
        return frame.shape[1],frame.shape[0]

    def drag(self,start,end,check):
        check()
        try:
            self._wait(self.controller.post_touch_down(*start))
            time.sleep(.08)
            for i in range(1,17):
                check()
                point=tuple(round(a+(b-a)*i/16) for a,b in zip(start,end))
                self._wait(self.controller.post_touch_move(*point))
                time.sleep(.025)
        finally:
            self._wait(self.controller.post_touch_up())

    def close(self):
        self._wait(self.controller.post_inactive())
