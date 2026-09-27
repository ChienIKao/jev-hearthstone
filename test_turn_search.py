import copy
import unittest
from test_strategy import fixture,unit,option
from turn_search import combat_plans,combat_inert,COMBAT_INERT


class SearchTests(unittest.TestCase):
    def test_known_resolved_battlecry_is_supported_but_changed_text_is_not(self):
        entity=unit(1,'1')
        entity['card_id']='CATA_556'
        cards={'CATA_556':{'text':COMBAT_INERT['CATA_556']}}
        self.assertTrue(combat_inert(entity,cards))
        cards['CATA_556']['text']+='每當攻擊抽一張牌'
        self.assertFalse(combat_inert(entity,cards))

    def test_taunt_order_and_state_immutability(self):
        state,cards=fixture([unit(1,'1',2,4),unit(2,'1',5,5)],
                            [unit(3,'2',1,2,TAUNT=1)],
                            [option(0,1,[3]),option(1,2,[3])],enemy_health=5)
        before=copy.deepcopy(state)
        plans=combat_plans(state,cards,time_budget=1)
        self.assertTrue(plans[0]['lethal'])
        self.assertEqual(plans[0]['sequence'],[(1,3),(2,102)])
        self.assertEqual(state,before)
        self.assertFalse(plans[0]['complete_turn'])

    def test_shield_and_poison_do_not_create_false_lethal(self):
        state,cards=fixture([unit(1,'1',2,4,POISONOUS=1)],
                            [unit(3,'2',1,2,TAUNT=1,DIVINE_SHIELD=1)],
                            [option(0,1,[3])],enemy_health=2)
        plans=combat_plans(state,cards,time_budget=1)
        self.assertFalse(any(p['lethal'] for p in plans))
        self.assertIn('敵方 1/2',plans[0]['summary'])

    def test_unknown_triggers_and_secrets_decline_simulation(self):
        state,cards=fixture([unit(1,'1')],[],[option(0,1,[102])])
        state['players'][1]['secret_count']=1
        self.assertEqual(combat_plans(state,cards),[])
        state['players'][1]['secret_count']=0
        cards['1']['text']='每當此手下攻擊，抽一張牌'
        self.assertEqual(combat_plans(state,cards),[])

    def test_forecasts_have_distinct_legal_first_actions(self):
        state,cards=fixture([unit(1,'1',3,4),unit(2,'1',2,3)],
                            [unit(3,'2',2,2)],
                            [option(0,1,[3,102]),option(1,2,[3,102])])
        plans=combat_plans(state,cards,time_budget=1)
        keys=[p['action']['key'] for p in plans]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertGreater(len(keys),1)
