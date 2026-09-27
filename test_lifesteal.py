import copy
import unittest
from test_strategy import fixture,unit,option
from card_simulator import simulate_card,card_plans
from turn_search import COMBAT_INERT,combat_plans
from turn_end import finish_turn
from survival import visible_attack_threat
from strategy import hp


class LifestealTests(unittest.TestCase):
    def state(self,attack=5,defense=1,**tags):
        source=unit(1,'1',attack,3,EXHAUSTED=0,LIFESTEAL=1)
        source['card_id']='TIME_056'
        target=unit(2,'2',2,defense,**tags)
        state,cards=fixture([source],[target],[option(0,1,[2,102])])
        cards['TIME_056']={'text':COMBAT_INERT['TIME_056']}
        for player in state['players']:player['heroes'][0]['tags']['DAMAGE']='10'
        return state,cards

    def attack(self,state,cards,target=2):
        return simulate_card(state,dict(kind='attack',entity_id=1,target_id=target),cards)

    def test_overkill_heals_full_damage_and_caps_at_max_health(self):
        state,cards=self.state()
        before=copy.deepcopy(state)
        after=self.attack(state,cards).state
        self.assertEqual(hp(after['players'][0]['heroes'][0]),25)
        self.assertEqual(after['players'][1]['board'],[])
        self.assertEqual(state,before)
        state['players'][0]['heroes'][0]['tags']['DAMAGE']='2'
        self.assertEqual(hp(self.attack(state,cards).state['players'][0]['heroes'][0]),30)

    def test_shield_prevents_healing_and_armor_counts(self):
        state,cards=self.state(DIVINE_SHIELD=1)
        after=self.attack(state,cards).state
        self.assertEqual(hp(after['players'][0]['heroes'][0]),20)
        self.assertEqual(after['players'][1]['board'][0]['tags']['DIVINE_SHIELD'],'0')
        state['players'][1]['heroes'][0]['tags']['ARMOR']='8'
        after=self.attack(state,cards,102).state
        self.assertEqual(hp(after['players'][0]['heroes'][0]),25)
        self.assertEqual(after['players'][1]['heroes'][0]['tags']['ARMOR'],'3')

    def test_both_sides_heal_even_when_minions_die_and_poison_adds_no_healing(self):
        state,cards=self.state(attack=1,defense=20,LIFESTEAL=1)
        state['players'][0]['board'][0]['tags'].update(POISONOUS='1',HEALTH='1')
        target=state['players'][1]['board'][0];target['card_id']='EDR_449'
        cards['EDR_449']={'text':COMBAT_INERT['EDR_449']}
        after=self.attack(state,cards).state
        self.assertEqual([p['board'] for p in after['players']],[[],[]])
        self.assertEqual([hp(p['heroes'][0]) for p in after['players']],[21,22])

    def test_healing_conversion_and_lifesteal_cannon_stop_forecasts(self):
        state,cards=self.state()
        state['players'][0]['player_tags']={'HEALING_DOES_DAMAGE':'1'}
        self.assertIsNone(self.attack(state,cards).state)
        self.assertIsNotNone(finish_turn(state,cards).outcomes)
        cannon=state['players'][0]['board'][0];cannon['card_id']='CAP_107t'
        cards['CAP_107t']={'text':COMBAT_INERT['CAP_107t']}
        self.assertTrue(finish_turn(state,cards).boundary)

    def test_defending_lifesteal_can_prevent_visible_lethal(self):
        state,cards=self.state(attack=5,defense=3)
        state['players'][0]['heroes'][0]['tags']['DAMAGE']='27'
        defender=state['players'][0]['board'][0]
        defender['tags'].update(HEALTH='1',TAUNT='1')
        state['players'][1]['board'].append(unit(3,'2',3,3))
        cards['3']={'text':''}
        self.assertFalse(visible_attack_threat(state,cards,time_budget=1)['lethal'])
        defender['tags']['LIFESTEAL']='0'
        self.assertTrue(visible_attack_threat(state,cards,time_budget=1)['lethal'])

    def test_mixed_search_supports_known_lifesteal_with_completed_turn(self):
        state,cards=self.state()
        plans=card_plans(state,cards,time_budget=1)
        self.assertTrue(plans)
        self.assertTrue(all(p['complete_turn'] for p in plans))
        self.assertIn('我英雄',plans[0]['summary'])
        self.assertEqual(combat_plans(state,cards),[])
        cards['TIME_056']['text']='生命竊取 在攻擊後，抽牌'
        self.assertIsNone(self.attack(state,cards).state)
