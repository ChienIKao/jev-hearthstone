"""Windows input backend used only when the user arms the desktop application."""
import ctypes as C
from ctypes import wintypes as W
import time

U=C.WinDLL('user32',use_last_error=True)
try:
    U.SetProcessDpiAwarenessContext(C.c_void_p(-4))
except (AttributeError,OSError):
    pass

class MOUSEINPUT(C.Structure):
    _fields_=[('dx',W.LONG),('dy',W.LONG),('mouseData',W.DWORD),('dwFlags',W.DWORD),('time',W.DWORD),('dwExtraInfo',C.c_size_t)]
class KEYBDINPUT(C.Structure):
    _fields_=[('wVk',W.WORD),('wScan',W.WORD),('dwFlags',W.DWORD),('time',W.DWORD),('dwExtraInfo',C.c_size_t)]
class HARDWAREINPUT(C.Structure):
    _fields_=[('uMsg',W.DWORD),('wParamL',W.WORD),('wParamH',W.WORD)]
class INPUTUNION(C.Union):
    _fields_=[('mi',MOUSEINPUT),('ki',KEYBDINPUT),('hi',HARDWAREINPUT)]
class INPUT(C.Structure):
    _anonymous_=('u',)
    _fields_=[('type',W.DWORD),('u',INPUTUNION)]

class WINDOWPLACEMENT(C.Structure):
    _fields_=[('length',W.UINT),('flags',W.UINT),('showCmd',W.UINT),('ptMinPosition',W.POINT),('ptMaxPosition',W.POINT),('rcNormalPosition',W.RECT)]

U.GetForegroundWindow.restype=W.HWND
U.SetForegroundWindow.argtypes=[W.HWND]
U.GetClientRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
U.ClientToScreen.argtypes=[W.HWND,C.POINTER(W.POINT)]
U.GetWindowTextLengthW.argtypes=[W.HWND]
U.GetWindowTextW.argtypes=[W.HWND,W.LPWSTR,C.c_int]
U.IsWindowVisible.argtypes=[W.HWND]
U.IsIconic.argtypes=[W.HWND]
U.ShowWindow.argtypes=[W.HWND,C.c_int]
U.GetWindowLongPtrW.argtypes=[W.HWND,C.c_int]
U.GetWindowLongPtrW.restype=C.c_ssize_t
U.SetWindowLongPtrW.argtypes=[W.HWND,C.c_int,C.c_ssize_t]
U.SetWindowLongPtrW.restype=C.c_ssize_t
U.SetLayeredWindowAttributes.argtypes=[W.HWND,W.DWORD,W.BYTE,W.DWORD]
U.GetLayeredWindowAttributes.argtypes=[W.HWND,C.POINTER(W.DWORD),C.POINTER(W.BYTE),C.POINTER(W.DWORD)]
U.GetDpiForWindow.argtypes=[W.HWND]
U.GetWindowPlacement.argtypes=[W.HWND,C.POINTER(WINDOWPLACEMENT)]
U.SetWindowPlacement.argtypes=[W.HWND,C.POINTER(WINDOWPLACEMENT)]
U.GetWindowRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
U.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT]
U.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]
U.SendInput.argtypes=[W.UINT,C.POINTER(INPUT),C.c_int]
U.SendInput.restype=W.UINT
K=C.WinDLL('kernel32',use_last_error=True)
K.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD]
K.OpenProcess.restype=W.HANDLE
K.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]
K.CloseHandle.argtypes=[W.HANDLE]


def find_game():
    found=[]
    CALLBACK=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    def visit(hwnd,_):
        if not U.IsWindowVisible(hwnd):
            return True
        pid=W.DWORD()
        U.GetWindowThreadProcessId(hwnd,C.byref(pid))
        handle=K.OpenProcess(0x1000,False,pid.value)
        if handle:
            name=C.create_unicode_buffer(32768)
            size=W.DWORD(len(name))
            try:
                if K.QueryFullProcessImageNameW(handle,0,name,C.byref(size)) and name.value.lower().endswith('\\hearthstone.exe'):
                    rect=W.RECT()
                    if U.GetClientRect(hwnd,C.byref(rect)) and (U.IsIconic(hwnd) or (rect.right>600 and rect.bottom>400)):
                        found.append(hwnd)
            finally:
                K.CloseHandle(handle)
        return True
    U.EnumWindows(CALLBACK(visit),0)
    if len(found)!=1:
        raise ValueError('找不到唯一的爐石遊戲視窗')
    return found[0]


def client_rect(hwnd):
    rect=W.RECT()
    point=W.POINT(0,0)
    if not U.GetClientRect(hwnd,C.byref(rect)) or not U.ClientToScreen(hwnd,C.byref(point)):
        raise ValueError('無法取得遊戲視窗尺寸')
    return point.x,point.y,rect.right,rect.bottom


def foreground(hwnd):
    return U.GetForegroundWindow()==hwnd


def minimized(hwnd):
    return bool(U.IsIconic(hwnd))


def minimize(hwnd):
    U.ShowWindow(hwnd,6)


class HiddenWindow:
    """Keep the game's alignment and restoration invisible until cleanup ends."""
    def __init__(self,hwnd):
        self.hwnd=hwnd
        self.placement=WINDOWPLACEMENT(length=C.sizeof(WINDOWPLACEMENT))
        if not U.GetWindowPlacement(hwnd,C.byref(self.placement)):
            raise ValueError('無法保存視窗位置，未開始輸入')
        self.rect=W.RECT()
        self.was_minimized=minimized(hwnd)
        if not U.GetWindowRect(hwnd,C.byref(self.rect)):
            raise ValueError('無法保存視窗邊界，未開始輸入')
        self.style=U.GetWindowLongPtrW(hwnd,-20)
        self.color,self.alpha,self.flags=W.DWORD(),W.BYTE(255),W.DWORD(2)
        if self.style&0x80000 and not U.GetLayeredWindowAttributes(hwnd,C.byref(self.color),C.byref(self.alpha),C.byref(self.flags)):
            raise ValueError('無法保存視窗透明度，未開始輸入')
        U.SetWindowLongPtrW(hwnd,-20,self.style|0x80000|0x20)
        if not U.SetLayeredWindowAttributes(hwnd,0,0,2):
            U.SetWindowLongPtrW(hwnd,-20,self.style)
            raise ValueError('無法隱藏遊戲視窗，未開始輸入')

    def close(self,keep_minimized=False):
        if not self.was_minimized:
            r=self.rect
            for _ in range(2):
                U.SetWindowPos(self.hwnd,None,r.left,r.top,r.right-r.left,r.bottom-r.top,0x14)
                time.sleep(.1)
        self.placement.showCmd=6 if keep_minimized else (self.placement.showCmd if self.placement.showCmd==3 else 4)
        restored=U.SetWindowPlacement(self.hwnd,C.byref(self.placement))
        time.sleep(.1)
        if self.style&0x80000:
            U.SetLayeredWindowAttributes(self.hwnd,self.color,self.alpha,self.flags)
        else:
            U.SetLayeredWindowAttributes(self.hwnd,0,255,2)
        U.SetWindowLongPtrW(self.hwnd,-20,self.style)
        if not restored:raise ValueError('遊戲視窗位置還原失敗')


def show_game(hwnd):
    U.SetForegroundWindow(hwnd)


def cursor():
    point=W.POINT()
    U.GetCursorPos(C.byref(point))
    return point.x,point.y


def stop_pressed():
    return bool(U.GetAsyncKeyState(0x77)&0x8001 or U.GetAsyncKeyState(0x1B)&0x8001)


def _send(flags,dx=0,dy=0):
    event=INPUT(type=0,mi=MOUSEINPUT(dx,dy,0,flags,0,0))
    if U.SendInput(1,C.byref(event),C.sizeof(INPUT))!=1:
        raise OSError(C.get_last_error(),'SendInput failed')


def move(x,y):
    left,top=U.GetSystemMetrics(76),U.GetSystemMetrics(77)
    width,height=U.GetSystemMetrics(78),U.GetSystemMetrics(79)
    _send(0x0001|0x8000|0x4000,round((x-left)*65535/max(1,width-1)),round((y-top)*65535/max(1,height-1)))


def click(point,check):
    check()
    move(*point)
    check()
    _send(0x0002)
    try:
        time.sleep(0.05)
    finally:
        _send(0x0004)


def drag(start,end,check):
    check()
    move(*start)
    time.sleep(0.08)
    check()
    _send(0x0002)
    try:
        for i in range(1,13):
            check()
            t=i/12
            move(round(start[0]+(end[0]-start[0])*t),round(start[1]+(end[1]-start[1])*t))
            time.sleep(0.025)
    finally:
        _send(0x0004)
