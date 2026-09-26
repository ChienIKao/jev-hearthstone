"""MaaFramework synthetic touch backend; no cursor-seizing fallback."""
import time


class MaaTouchInput:
    def __init__(self,hwnd):
        from maa.controller import Win32Controller
        from maa.define import MaaWin32InputMethodEnum as Input, MaaWin32ScreencapMethodEnum as Capture
        self.controller=Win32Controller(hwnd,screencap_method=Capture.FramePool,
                                        mouse_method=Input.AnchoredTouch,keyboard_method=Input.PostMessage)
        self.controller.set_screenshot_use_raw_size(True)
        self._wait(self.controller.post_connection())

    @staticmethod
    def _wait(job):
        if not job.wait().succeeded:
            raise ValueError('MaaFramework 觸控操作失敗，未切換其他輸入方式')

    def click(self,point,check):
        check()
        self._wait(self.controller.post_click(*point))
        check()

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
