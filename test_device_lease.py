import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import device_lease as leases


class DeviceLeaseTests(unittest.TestCase):
    def test_nested_calls_work_but_other_thread_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(leases,'LOCK_ROOT',Path(directory)):
            failures=[]
            def compete():
                try:
                    with leases.device_lease('127.0.0.1:16384'):pass
                except ValueError as exc:failures.append(str(exc))
            with leases.device_lease('localhost:16384'):
                with leases.device_lease('127.0.0.1:16384'):pass
                thread=threading.Thread(target=compete);thread.start();thread.join()
            self.assertEqual(len(failures),1)
            with leases.device_lease('127.0.0.1:16384'):pass

    def test_other_process_is_rejected_and_lock_releases_after_exception(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(leases,'LOCK_ROOT',Path(directory)):
            script="from pathlib import Path; import device_lease as d; import sys; d.LOCK_ROOT=Path(sys.argv[1]);\nwith d.device_lease('test-device'): print('acquired')"
            def child():
                return subprocess.run([sys.executable,'-c',script,directory],capture_output=True,timeout=10,
                                      creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            with self.assertRaises(RuntimeError):
                with leases.device_lease('test-device'):
                    self.assertNotEqual(child().returncode,0)
                    raise RuntimeError('operation failed')
            self.assertEqual(child().returncode,0)


if __name__=='__main__':unittest.main()
