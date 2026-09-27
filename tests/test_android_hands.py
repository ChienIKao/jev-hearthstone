from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from laya_hearthstone.android_hands import AndroidHands,StateChanged,android_plan


class AndroidHandsTests(unittest.TestCase):
    def test_battlecry_places_rightmost_and_accounts_for_new_friendly_slot(self):
        from tests.test_strategy import fixture,unit
        from laya_hearthstone.executor import DEFAULT_LAYOUT
        from laya_hearthstone.geometry import board_points
        state,_=fixture([unit(1,'1',ZONE_POSITION=1),unit(2,'1',ZONE_POSITION=2)],
                        [unit(8,'2',ZONE_POSITION=1)],[])
        card=unit(3,'1',ZONE_POSITION=1)
        card['tags']['ZONE']='HAND'
        state['players'][0]['hand']=[card]
        action={'kind':'play','card_type':'MINION','entity_id':3,'target_id':2}
        plan=android_plan(state,action,DEFAULT_LAYOUT)
        points=board_points(3,'me',DEFAULT_LAYOUT)
        self.assertEqual(plan[0]['to'],points[-1])
        self.assertEqual(plan[-1]['point'],points[1])
        self.assertGreaterEqual(plan[1]['seconds'],2.5)
        action['target_id']=8
        self.assertEqual(android_plan(state,action,DEFAULT_LAYOUT)[-1]['point'],board_points(1,'enemy',DEFAULT_LAYOUT)[0])

    def test_failed_single_gesture_retries_once_after_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            hands=AndroidHands(Mock(serial='retry-test'),{}, {},Path(directory))
            action={'key':'o0','kind':'end_turn'}
            state={'game_serial':'same','turn':'3'}
            clock=[0.0];attempt_times=[]
            def attempt(*args):
                attempt_times.append(clock[0])
                return dict(id=str(len(attempt_times)),confirmed=False,plan=[{'op':'click'}],timings={'total':0})
            hands._run=Mock(side_effect=attempt)
            hands.observe=Mock(return_value=state)
            with patch('laya_hearthstone.android_hands.time.perf_counter',side_effect=lambda:clock[0]),patch('laya_hearthstone.android_hands.time.sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)),patch('laya_hearthstone.android_hands.action_succeeded',return_value=False),patch('laya_hearthstone.android_hands.get_actions',return_value=({'o0':action},[])):
                result=hands.run(action,state)
            self.assertEqual(len(attempt_times),2)
            self.assertGreaterEqual(attempt_times[1]-attempt_times[0],2.5)
            self.assertFalse(result['confirmed'])
            self.assertEqual(result['attempts'],['1','2'])

    def test_late_success_changed_state_and_mulligan_are_not_repeated(self):
        for late,changed,kind in ((True,True,'play'),(False,True,'play'),(False,False,'mulligan')):
            with self.subTest(late=late,changed=changed,kind=kind),tempfile.TemporaryDirectory() as directory:
                hands=AndroidHands(Mock(serial='retry-test'),{}, {},Path(directory));hands.action_interval=0
                hands._run=Mock(return_value=dict(id='1',confirmed=False,plan=[{'op':'click'}],timings={'total':0}))
                state={'game_serial':'same','turn':'3'}
                hands.observe=Mock(return_value=dict(state,turn='4') if changed else state)
                with patch('laya_hearthstone.android_hands.action_succeeded',return_value=late):
                    result=hands.run({'kind':kind},state)
                hands._run.assert_called_once()
                self.assertEqual(result['confirmed'],late)

    def test_stop_during_interval_prevents_input(self):
        with tempfile.TemporaryDirectory() as directory:
            hands=AndroidHands(Mock(serial='retry-test'),{}, {},Path(directory))
            hands._cooldown_until=float('inf')
            hands._run=Mock()
            with self.assertRaisesRegex(ValueError,'Stopped'):
                hands.run({}, {},lambda:True)
            hands._run.assert_not_called()

    def test_confirmed_actions_also_observe_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            hands=AndroidHands(Mock(serial='retry-test'),{}, {},Path(directory))
            clock=[0.0];times=[]
            def attempt(*args):
                times.append(clock[0])
                return dict(id=str(len(times)),confirmed=True,plan=[{'op':'click'}],timings={'total':0})
            hands._run=Mock(side_effect=attempt)
            with patch('laya_hearthstone.android_hands.time.perf_counter',side_effect=lambda:clock[0]),patch('laya_hearthstone.android_hands.time.sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)):
                hands.run({},{});hands.run({},{})
            self.assertGreaterEqual(times[1]-times[0],2.5)

    def test_location_drags_to_target_using_current_board_counts(self):
        from tests.test_strategy import fixture,unit
        from laya_hearthstone.executor import DEFAULT_LAYOUT,build_plan
        location=unit(1,'1',ZONE_POSITION=1)
        location['tags']['CARDTYPE']='LOCATION'
        state,_=fixture([location],[unit(8,'2',ZONE_POSITION=1)],[])
        action={'kind':'location','entity_id':1,'target_id':8}
        plan=android_plan(state,action,DEFAULT_LAYOUT)
        self.assertEqual(plan,[{'op':'drag','from':[.5,DEFAULT_LAYOUT['board_me_y']],
                               'to':[.5,DEFAULT_LAYOUT['board_enemy_y']]}])
        state['players'][1]['board'].insert(0,unit(7,'2',ZONE_POSITION=1))
        self.assertGreater(android_plan(state,action,DEFAULT_LAYOUT)[0]['to'][0],.5)
        self.assertEqual(build_plan(state,action,DEFAULT_LAYOUT)[0]['op'],'click')
        action.pop('target_id')
        self.assertEqual(android_plan(state,action,DEFAULT_LAYOUT),
                         [{'op':'click','point':[.5,DEFAULT_LAYOUT['board_me_y']]}])

    def test_waiting_for_screen_rechecks_game_before_any_input(self):
        with tempfile.TemporaryDirectory() as directory:
            device=Mock()
            device.wait_stable.side_effect=lambda check,**kwargs:check()
            hands=AndroidHands(device,{}, {},Path(directory))
            hands.observe=Mock(return_value={'game_serial':'new'})
            with patch('laya_hearthstone.android_hands.time.monotonic',side_effect=[0,1,1]):
                with self.assertRaises(StateChanged):
                    hands.run({'kind':'end_turn'},{'game_serial':'old'})
            device.execute.assert_not_called()


if __name__=='__main__':
    unittest.main()
