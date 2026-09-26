import unittest
from unittest.mock import patch
from maa_input import MaaTouchInput

class Job:
    def __init__(self,ok=True):self.succeeded=ok
    def wait(self):return self

class TouchTests(unittest.TestCase):
    def test_interrupted_drag_releases_contact(self):
        events=[]
        class Controller:
            def post_touch_down(self,*point):events.append(('down',point));return Job()
            def post_touch_move(self,*point):events.append(('move',point));return Job()
            def post_touch_up(self):events.append(('up',));return Job()
        backend=MaaTouchInput.__new__(MaaTouchInput)
        backend.controller=Controller()
        checks=[0]
        def check():
            checks[0]+=1
            if checks[0]==3:raise ValueError('stopped')
        with patch('maa_input.time.sleep'),self.assertRaises(ValueError):
            backend.drag((50,60),(100,200),check)
        self.assertEqual(events[0],('down',(50,60)))
        self.assertEqual(events[-1],('up',))

    def test_failed_job_is_not_reported_as_success(self):
        with self.assertRaises(ValueError):MaaTouchInput._wait(Job(False))
