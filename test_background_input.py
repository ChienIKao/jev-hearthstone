import unittest
from background_input import BackgroundInput

class BackgroundInputTests(unittest.TestCase):
    def test_drag_uses_client_coordinates_and_button_state(self):
        events=[]
        backend=BackgroundInput(123,lambda *args:events.append(args),lambda _:None)
        backend.drag((20,30),(100,200),lambda:None)
        self.assertEqual(events[1],(123,0x201,1,(30<<16)|20))
        self.assertEqual(events[-1],(123,0x202,0,(200<<16)|100))
        self.assertTrue(all(event[2]==1 for event in events[2:-1]))

    def test_interruption_releases_button(self):
        events=[]
        backend=BackgroundInput(123,lambda *args:events.append(args),lambda _:None)
        checks=[0]
        def check():
            checks[0]+=1
            if checks[0]>3:raise ValueError('stop')
        with self.assertRaises(ValueError):backend.drag((20,30),(100,200),check)
        self.assertEqual(events[-1][1],0x202)
        self.assertEqual(events[-1][3],events[-2][3])
