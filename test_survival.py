import copy
import unittest
from unittest.mock import Mock
from test_strategy import fixture,unit,option
from survival import visible_attack_threat
from advisor import Decider


class SurvivalTests(unittest.TestCase):
    def test_next_turn_refreshes_attacks_and_includes_armor(self):
        state,cards=fixture([], [unit(2,'2',3,3,EXHAUSTED=1,NUM_ATTACKS_THIS_TURN=1)],[],own_health=3)
        before=copy.deepcopy(state)
        self.assertTrue(visible_attack_threat(state,cards,time_budget=1)['lethal'])
        self.assertEqual(state,before)
        state['players'][0]['heroes'][0]['tags']['ARMOR']='1'
        self.assertFalse(visible_attack_threat(state,cards,time_budget=1)['lethal'])

    def test_taunt_absorbs_attack_and_frozen_attacker_stays_unavailable(self):
        state,cards=fixture([unit(1,'1',1,1,TAUNT=1)], [unit(2,'2',5,5)],[],own_health=3)
        self.assertFalse(visible_attack_threat(state,cards,time_budget=1)['lethal'])
        state['players'][0]['board']=[]
        state['players'][1]['board'][0]['tags']['FROZEN']='1'
        self.assertFalse(visible_attack_threat(state,cards,time_budget=1)['lethal'])

    def test_enemy_can_remove_shielded_taunt_before_lethal(self):
        state,cards=fixture([unit(1,'1',0,1,TAUNT=1,DIVINE_SHIELD=1)],
                            [unit(2,'2',1,1),unit(3,'2',1,1),unit(4,'2',5,5)],[],own_health=5)
        self.assertTrue(visible_attack_threat(state,cards,time_budget=1)['lethal'])
        state['players'][1]['board'].pop()
        self.assertFalse(visible_attack_threat(state,cards,time_budget=1)['lethal'])

    def test_unknown_effect_and_budget_exhaustion_are_not_safety_certificates(self):
        state,cards=fixture([], [unit(2,'2',5,5)],[],own_health=5)
        self.assertIsNone(visible_attack_threat(state,cards,time_budget=0)['lethal'])
        cards['2']['text']='Whenever this attacks, summon a minion'
        self.assertIsNone(visible_attack_threat(state,cards,time_budget=1)['lethal'])

    def test_forced_armor_survival_bypasses_model(self):
        state,cards=fixture([], [unit(2,'2',3,3),unit(3,'2',3,3)], [option(0,9,[])],own_health=5)
        power=unit(9,'1',COST=2);power['tags']['CARDTYPE']='HERO_POWER'
        state['players'][0]['hero_powers']=[power]
        cards['9']={'text':'英雄能力獲得$d2點護甲值'}
        decider=Decider(cards);decider.load=Mock(side_effect=AssertionError('must take modeled survival'))
        result=decider.decide(state)
        self.assertEqual(result['method'],'rules_survival')
        self.assertEqual(result['action']['entity_id'],9)
        self.assertEqual(result['counterattack_if_pass']['lethal_probability'],1)
        self.assertEqual(result['survival_plan']['counterattack']['lethal_probability'],0)
        decider.load.assert_not_called()
