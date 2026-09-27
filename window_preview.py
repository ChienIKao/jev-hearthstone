"""Live DWM projection that stays in place during background window alignment."""
import ctypes as C
from ctypes import wintypes as W
import threading
import win_input as win


class ThumbnailProperties(C.Structure):
    _fields_=[('flags',W.DWORD),('destination',W.RECT),('source',W.RECT),
              ('opacity',W.BYTE),('visible',W.BOOL),('client_only',W.BOOL)]


class LiveWindowPreview:
    def __init__(self, source):
        self.source=source
        self.rect=win.client_rect(source)
        self.ready=threading.Event()
        self.stopped=threading.Event()
        self.error=None
        self.hwnd=None
        self.thread=threading.Thread(target=self._run,daemon=True)
        self.thread.start()
        if not self.ready.wait(5):
            self.stopped.set()
            raise ValueError('即時遊戲畫面未準備完成，未開始輸入')
        if self.error:
            raise ValueError('無法建立即時遊戲畫面：'+str(self.error))

    def _run(self):
        u=win.U
        dwm=C.WinDLL('dwmapi')
        u.CreateWindowExW.argtypes=[W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,C.c_int,C.c_int,
                                   C.c_int,C.c_int,W.HWND,W.HMENU,W.HINSTANCE,W.LPVOID]
        u.CreateWindowExW.restype=W.HWND
        u.DestroyWindow.argtypes=[W.HWND]
        u.GetWindow.argtypes=[W.HWND,W.UINT]
        u.GetWindow.restype=W.HWND
        u.PeekMessageW.argtypes=[C.POINTER(W.MSG),W.HWND,W.UINT,W.UINT,W.UINT]
        u.TranslateMessage.argtypes=[C.POINTER(W.MSG)]
        u.DispatchMessageW.argtypes=[C.POINTER(W.MSG)]
        u.DispatchMessageW.restype=C.c_ssize_t
        dwm.DwmRegisterThumbnail.argtypes=[W.HWND,W.HWND,C.POINTER(W.HANDLE)]
        dwm.DwmUpdateThumbnailProperties.argtypes=[W.HANDLE,C.POINTER(ThumbnailProperties)]
        dwm.DwmUnregisterThumbnail.argtypes=[W.HANDLE]
        thumbnail=W.HANDLE()
        try:
            u.SetThreadDpiAwarenessContext.argtypes=[C.c_void_p]
            u.SetThreadDpiAwarenessContext(C.c_void_p(-4))
            previous=u.GetWindow(self.source,3)
            x,y,width,height=self.rect
            self.hwnd=u.CreateWindowExW(0x08000080,'STATIC','Laya 即時遊戲畫面',0x80000000,
                                       x,y,width,height,None,None,None,None)
            if not self.hwnd:
                raise C.WinError(C.get_last_error())
            if dwm.DwmRegisterThumbnail(self.hwnd,self.source,C.byref(thumbnail)):
                raise ValueError('DwmRegisterThumbnail failed')
            properties=ThumbnailProperties(flags=0x1|0x4|0x8|0x10,
                destination=W.RECT(0,0,width,height),opacity=255,visible=True,client_only=True)
            if dwm.DwmUpdateThumbnailProperties(thumbnail,C.byref(properties)):
                raise ValueError('DwmUpdateThumbnailProperties failed')
            if not u.SetWindowPos(self.hwnd,previous,x,y,width,height,0x10|0x40):
                raise C.WinError(C.get_last_error())
            dwm.DwmFlush()
            self.ready.set()
            msg=W.MSG()
            while not self.stopped.wait(.01):
                while u.PeekMessageW(C.byref(msg),None,0,0,1):
                    u.TranslateMessage(C.byref(msg))
                    u.DispatchMessageW(C.byref(msg))
        except Exception as exc:
            self.error=exc
        finally:
            self.ready.set()
            if thumbnail:
                dwm.DwmUnregisterThumbnail(thumbnail)
            if self.hwnd:
                u.DestroyWindow(self.hwnd)

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise ValueError('即時遊戲畫面尚未關閉')
