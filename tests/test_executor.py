import copy
import time
import unittest
from laya_hearthstone.executor import DEFAULT_LAYOUT, validate, build_plan, action_succeeded, window_matches, pixel_plan
from laya_hearthstone.advisor import fingerprint
from laya_hearthstone.strategy import get_actions
from tests.test_strategy import fixture, unit, option


class ExecutionTests(unittest.TestCase):
    def test_wrong_sent_target_cannot_confirm_an_attack(self):
        before,_,advice,_=self.setup_action()
        action=advice['action']
        before['sent_option']=None
        after=copy.deepcopy(before)
        after['players'][0]['board'][0]['tags']['EXHAUSTED']='1'
        packet=dict(option_index=action['option_index'],target_id=999,revision=1)
        after['sent_option']=packet
        self.assertFalse(action_succeeded(before,after,action))
        packet['target_id']=action['target_id']
        self.assertTrue(action_succeeded(before,after,action))
        before['sent_option']=dict(packet)
        self.assertFalse(action_succeeded(before,after,action))

    def test_full_plan_rejects_offscreen_second_click_before_execution(self):
        plan=[{'op':'click','point':[.5,.7]},{'op':'click','point':[1.1,.3]}]
        with self.assertRaises(ValueError):pixel_plan(plan,1280,720)
        with self.assertRaises(ValueError):pixel_plan([{'op':'click','point':[float('nan'),.5]}],1280,720)

    def test_client_pixels_are_independent_of_desktop_position(self):
        plan=[{'op':'drag','from':[.4,.9],'to':[.5,.2]}]
        self.assertEqual(pixel_plan(plan,1280,720)[0],{'op':'drag','from':(512,648),'to':(640,144)})
        self.assertEqual(pixel_plan(plan,1280,720,(-1920,80))[0]['to'],(-1280,224))

    def test_hero_power_and_minion_target_use_current_entity_layout(self):
        state,_,_,layout=self.setup_action()
        enemy=unit(8,'2',2,3,ZONE_POSITION=1)
        state['players'][1]['board']=[enemy]
        power=unit(9,'1')
        power['tags']['CARDTYPE']='HERO_POWER'
        state['players'][0]['hero_powers']=[power]
        action={'kind':'hero_power','entity_id':9,'target_id':8}
        plan=build_plan(state,action,layout)
        self.assertEqual(plan[0]['point'],layout['power_me'])
        self.assertEqual(plan[-1]['point'],[.5,layout['board_enemy_y']])
        state['players'][1]['board'].insert(0,unit(7,'2',ZONE_POSITION=1))
        moved=build_plan(state,action,layout)
        self.assertGreater(moved[-1]['point'][0],plan[-1]['point'][0])

    def test_window_alignment_allows_translation_but_not_resize(self):
        before=(9,32,1902,991)
        translated=(-500,-200,1902,991)
        self.assertTrue(window_matches(translated,before,True))
        self.assertFalse(window_matches(translated,before,False))
        self.assertFalse(window_matches((-500,-200,1280,720),before,True))

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
        self.assertEqual(validate(state,advice,layout,1280,720,cards)['kind'],'attack')
        self.assertEqual(validate(state,advice,layout,1024,768,cards)['kind'],'attack')
        with self.assertRaises(ValueError):
            validate(state,advice,layout,0,0,cards)
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
