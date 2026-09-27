import copy
import unittest
from tests.test_strategy import fixture,unit,option
from laya_hearthstone.turn_search import COMBAT_INERT
from laya_hearthstone.card_simulator import simulate_card,card_plans
from laya_hearthstone.strategy import rank_actions


class LocationEffectTests(unittest.TestCase):
    def setup_location(self,health=1):
        state,cards=fixture([unit(1,'1',1,health,EXHAUSTED=0)],[],[option(0,2,[1]),option(1,1,[102])])
        location=unit(2,'1',0,3,COST=1);location.update(card_id='CORE_REV_990')
        location['tags']['CARDTYPE']='LOCATION'
        state['players'][0]['board'].append(location)
        cards['CORE_REV_990']={'text':COMBAT_INERT['CORE_REV_990'],'health':3}
        return state,cards,dict(kind='location',entity_id=2,target_id=1)

    def test_one_health_target_dies_and_location_spends_one_charge(self):
        state,cards,action=self.setup_location();before=copy.deepcopy(state)
        after=simulate_card(state,action,cards).state
        self.assertEqual([e['id'] for e in after['players'][0]['board']],[2])
        self.assertEqual(after['players'][0]['board'][0]['tags']['DAMAGE'],'1')
        self.assertEqual(after['players'][0]['mana'],5)
        self.assertIsNone(simulate_card(after,action,cards).state)
        self.assertEqual(state,before)
        ranked=rank_actions(state,cards)['ranked']
        scores={a['key']:a['rule_score'] for a in ranked}
        self.assertLess(scores['o0t0'],scores['o99'])

    def test_buff_before_attack_finds_lethal_and_cannot_repeat(self):
        state,cards,action=self.setup_location(health=3)
        state['players'][1]['heroes'][0]['tags']['HEALTH']='3'
        plans=card_plans(state,cards,max_depth=3,time_budget=1)
        self.assertTrue(plans[0]['lethal'])
        self.assertEqual(plans[0]['action']['kind'],'location')
        after=simulate_card(state,action,cards).state
        self.assertIsNone(simulate_card(after,action,cards).state)

    def test_unknown_enchantment_preserves_local_damage_penalty(self):
        state,cards,action=self.setup_location()
        state['enchantments']=[dict(card_id='unknown',tags={'ATTACHED':'102'})]
        self.assertIsNone(simulate_card(state,action,cards).state)
        scores={a['key']:a['rule_score'] for a in rank_actions(state,cards)['ranked']}
        self.assertLess(scores['o0t0'],scores['o99'])

    def test_play_location_can_be_used_immediately_and_last_charge_removes_it(self):
        state,cards,action=self.setup_location(health=3)
        location=state['players'][0]['board'].pop()
        location['tags']['ZONE']='HAND';location['tags']['DAMAGE']='2'
        state['players'][0]['hand']=[location]
        after=simulate_card(state,dict(kind='play',entity_id=2),cards).state
        self.assertEqual(after['players'][0]['mana'],4)
        after=simulate_card(after,action,cards).state
        self.assertEqual([e['id'] for e in after['players'][0]['board']],[1])
        self.assertEqual(after['players'][0]['board'][0]['tags']['ATK'],'3')
