import copy
import unittest
from tests.test_strategy import fixture,unit
from laya_hearthstone.strategy import hp
from laya_hearthstone.turn_search import COMBAT_INERT
from laya_hearthstone.turn_end import finish_turn
from laya_hearthstone.card_simulator import card_plans


class TurnEndTests(unittest.TestCase):
    def cannon(self,ident,side='1'):
        result=unit(ident,side,1,1,EXHAUSTED=1)
        result['card_id']='CAP_107t'
        return result

    def test_random_shot_is_not_a_certain_lethal(self):
        state,cards=fixture([self.cannon(1)],[unit(2,'2',2,1)],[],enemy_health=1)
        cards['CAP_107t']={'text':COMBAT_INERT['CAP_107t']}
        before=copy.deepcopy(state)
        result=finish_turn(state,cards)
        self.assertEqual(len(result.outcomes),2)
        self.assertAlmostEqual(sum(p for p,_ in result.outcomes),1)
        self.assertEqual(sorted(hp(s['players'][1]['heroes'][0]) for _,s in result.outcomes),[0,1])
        plan=card_plans(state,cards,time_budget=1)[0]
        self.assertFalse(plan['lethal'])
        self.assertEqual(plan['lethal_probability'],.5)
        self.assertTrue(plan['complete_turn'])
        self.assertEqual(state,before)

    def test_two_shots_retarget_after_death_and_prove_lethal(self):
        state,cards=fixture([self.cannon(1),self.cannon(3)],[unit(2,'2',2,1)],[],enemy_health=1)
        cards['CAP_107t']={'text':COMBAT_INERT['CAP_107t']}
        ending=finish_turn(state,cards)
        self.assertAlmostEqual(sum(p for p,_ in ending.outcomes),1)
        self.assertTrue(all(hp(s['players'][1]['heroes'][0])<=0 for _,s in ending.outcomes))
        plan=card_plans(state,cards,time_budget=1)[0]
        self.assertTrue(plan['lethal'])
        self.assertEqual(plan['action']['kind'],'end_turn')

    def test_enemy_cannons_and_silenced_cannons_do_not_fire(self):
        cannon=self.cannon(1);cannon['tags']['SILENCED']='1'
        state,cards=fixture([cannon],[self.cannon(2,'2')],[])
        cards['CAP_107t']={'text':COMBAT_INERT['CAP_107t']}
        ending=finish_turn(state,cards)
        self.assertEqual(len(ending.outcomes),1)
        self.assertEqual([hp(p['heroes'][0]) for p in ending.outcomes[0][1]['players']],[30,30])

    def test_shield_and_armor_absorb_shots(self):
        state,cards=fixture([self.cannon(1)],[],[])
        cards['CAP_107t']={'text':COMBAT_INERT['CAP_107t']}
        hero=state['players'][1]['heroes'][0]
        for tag in ('DIVINE_SHIELD','ARMOR'):
            hero['tags'][tag]='1'
            result=finish_turn(state,cards).outcomes[0][1]['players'][1]['heroes'][0]
            self.assertEqual(hp(result),30)
            self.assertEqual(result['tags'][tag],'0')
            del hero['tags'][tag]

    def test_unknown_end_effect_or_branch_limit_returns_boundary(self):
        state,cards=fixture([self.cannon(1),self.cannon(3)],[unit(2,'2')],[])
        cards['CAP_107t']={'text':COMBAT_INERT['CAP_107t']}
        self.assertIsNotNone(finish_turn(state,cards,max_outcomes=2).boundary)
        cards['2']['text']='At end of turn, deal damage'
        self.assertEqual(finish_turn(state,cards).outcomes,[])
