"""Exclusive device control across panels, processes and nested action calls."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import threading

LOCK_ROOT=Path(__file__).parent/'data'/'device-locks'
_registry={}
_registry_guard=threading.Lock()
_local=threading.local()


@contextmanager
def device_lease(serial):
    key=hashlib.sha256(str(serial).replace('localhost:','127.0.0.1:').encode()).hexdigest()[:24]
    with _registry_guard:
        lock=_registry.setdefault(key,threading.RLock())
    if not lock.acquire(blocking=False):
        raise ValueError('另一個工作正在操作這台 MuMu，請先停止該工作。')
    held=getattr(_local,'held',None)
    if held is None:
        held=_local.held=set()
    stream=None
    acquired=False
    try:
        if key not in held:
            LOCK_ROOT.mkdir(parents=True,exist_ok=True)
            stream=(LOCK_ROOT/(key+'.lock')).open('a+b')
            if stream.tell()==0:
                stream.write(b'0');stream.flush()
            stream.seek(0)
            try:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:
                raise ValueError('另一個助手正在操作這台 MuMu，請先停止該助手。') from None
            acquired=True
            held.add(key)
        yield
    finally:
        if acquired:
            held.remove(key)
            stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
        if stream is not None:
            stream.close()
        lock.release()
