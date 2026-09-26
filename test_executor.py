import copy
import time
import unittest
from executor import DEFAULT_LAYOUT, validate, build_plan, action_succeeded
from advisor import fingerprint
from strategy import get_actions
from test_strategy import fixture, unit, option


class ExecutionTests(unittest.TestCase):
    def setup_action(self):
        state,cards=fixture([unit(1,'1',3,4,ZONE_POSITION=1)],[],[option(0,1,[102])])
        state['observed_at']=time.time()
        state['game_serial']='test'
        actions,_=get_actions(state,cards)
        action=actions['o0t0']
        advice={'status':'suggestion','state_fingerprint':fingerprint(state),'action':action}
        layout=copy.deepcopy(DEFAULT_LAYOUT)
        layout.update(confirmed=True,width=1920,height=1080)
        return state,cards,advice,layout

    def test_gate_rejects_stale_uncalibrated_or_resized(self):
        state,cards,advice,layout=self.setup_action()
        self.assertEqual(validate(state,advice,layout,1920,1080,cards)['kind'],'attack')
        with self.assertRaises(ValueError):
            validate(state,advice,layout,1280,720,cards)
        layout['confirmed']=False
        with self.assertRaises(ValueError):
            validate(state,advice,layout,1920,1080,cards)
        layout['confirmed']=True
        with self.assertRaises(ValueError):
            validate(state,advice,layout,1920,1080,cards,now=state['observed_at']+3)
        state['turn']='99'
        with self.assertRaises(ValueError):
            validate(state,advice,layout,1920,1080,cards)

    def test_attack_plan_and_log_confirmation(self):
        state,cards,advice,layout=self.setup_action()
        plan=build_plan(state,advice['action'],layout)
        self.assertEqual(plan[0]['op'],'drag')
        self.assertEqual(plan[0]['to'],layout['hero_enemy'])
        after=copy.deepcopy(state)
        self.assertFalse(action_succeeded(state,after,advice['action']))
        after['players'][0]['board'][0]['tags']['NUM_ATTACKS_THIS_TURN']='1'
        self.assertTrue(action_succeeded(state,after,advice['action']))

    def test_play_confirmed_only_when_card_leaves_hand(self):
        state,cards,advice,layout=self.setup_action()
        card=unit(9,'1',2,2)
        card['tags'].update(ZONE='HAND',ZONE_POSITION='1')
        state['players'][0]['hand']=[card]
        action={'kind':'play','entity_id':9}
        after=copy.deepcopy(state)
        self.assertFalse(action_succeeded(state,after,action))
        after['players'][0]['hand']=[]
        self.assertTrue(action_succeeded(state,after,action))

if __name__=='__main__':
    unittest.main()
