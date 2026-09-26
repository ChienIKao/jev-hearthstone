import copy
import unittest
from geometry import hand_points,board_points
from executor import DEFAULT_LAYOUT,point_for
from test_strategy import fixture,unit

class GeometryTests(unittest.TestCase):
    def test_all_counts_are_ordered_inside_client(self):
        for n in range(11):
            points,_=hand_points(n,DEFAULT_LAYOUT)
            self.assertEqual(len(points),n)
            self.assertTrue(all(0<x<1 and 0<y<1 for x,y in points))
            self.assertTrue(all(a[0]<b[0] for a,b in zip(points,points[1:])))
        for side in ('me','enemy'):
            for n in range(8):
                points=board_points(n,side,DEFAULT_LAYOUT)
                self.assertEqual(len(points),n)
                if n:self.assertAlmostEqual((points[0][0]+points[-1][0])/2,0.5)

    def test_calibration_precedence_and_curved_estimates(self):
        layout=copy.deepcopy(DEFAULT_LAYOUT)
        saved=[[.35,.95],[.42,.92],[.48,.91],[.54,.92],[.61,.95]]
        layout['hand_overrides']['5']=saved
        self.assertEqual(hand_points(5,layout),(saved,'calibrated'))
        for n in (3,6,10):
            points,status=hand_points(n,layout)
            self.assertEqual(status,'estimated')
            self.assertGreater(points[0][1],points[n//2][1])

    def test_card_is_relocated_after_left_card_leaves(self):
        state,_=fixture([],[],[])
        hand=[unit(i,'1',1,1) for i in range(1,7)]
        state['players'][0]['hand']=hand
        before=point_for(3,state,DEFAULT_LAYOUT)
        state['players'][0]['hand']=hand[1:]
        after=point_for(3,state,DEFAULT_LAYOUT)
        self.assertNotEqual(before,after)
        self.assertEqual(after,hand_points(5,DEFAULT_LAYOUT)[0][1])

    def test_bad_calibration_is_rejected(self):
        layout=copy.deepcopy(DEFAULT_LAYOUT)
        layout['hand_overrides']['2']=[[.5,.9]]
        with self.assertRaises(ValueError):hand_points(2,layout)
        with self.assertRaises(ValueError):board_points(8,'me',layout)

if __name__=='__main__':unittest.main()
