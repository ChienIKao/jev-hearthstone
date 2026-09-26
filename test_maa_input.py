import unittest
from unittest.mock import patch
from maa_input import MaaTouchInput,align_plan
from unittest.mock import Mock

class Job:
    def __init__(self,ok=True):self.succeeded=ok
    def wait(self):return self

class TouchTests(unittest.TestCase):
    def test_alignment_recomputes_coordinates_after_dpi_resize(self):
        backend=Mock()
        stop=Mock()
        stop.is_set.return_value=False
        stop.wait.return_value=False
        rectangles=iter([(0,0,1000,600),(2000,0,1250,750),(2050,0,1250,750)])
        make_plan=lambda w,h:[{'op':'drag','from':[.5,.75],'to':[.5,.2]}]
        rect,plan=align_plan(backend,make_plan,lambda:next(rectangles),stop)
        self.assertEqual(rect,(2050,0,1250,750))
        self.assertEqual([c.args[0] for c in backend.hover.call_args_list],[(500,450),(625,562)])
        backend.click.assert_not_called()
        backend.drag.assert_not_called()

    def test_alignment_refuses_continuously_changing_size(self):
        backend=Mock()
        stop=Mock()
        stop.is_set.return_value=False
        stop.wait.return_value=False
        rectangles=iter([(0,0,1000+i*10,600) for i in range(5)])
        with self.assertRaisesRegex(ValueError,'縮放未穩定'):
            align_plan(backend,lambda w,h:[{'op':'click','point':[.5,.5]}],lambda:next(rectangles),stop)
        backend.click.assert_not_called()

    def test_minimized_capture_must_succeed_before_input(self):
        class Controller:
            def post_screencap(self):return Job(False)
        backend=MaaTouchInput.__new__(MaaTouchInput)
        backend.controller=Controller()
        with self.assertRaises(ValueError):backend.prepare_minimized()

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
