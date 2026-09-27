import copy
import unittest
from tests.test_strategy import fixture,unit,option
from laya_hearthstone.card_simulator import simulate_card,card_plans
from laya_hearthstone.turn_search import COMBAT_INERT


class SummonSearchTests(unittest.TestCase):
    def mother(self,board=None):
        state,cards=fixture(board or [],[unit(9,'2',2,3)],[option(0,5,[])])
        mother=unit(5,'1',2,3,COST=4)
        mother['card_id']='EDR_492';mother['tags']['ZONE']='HAND'
        state['players'][0]['hand']=[mother]
        cards.update(EDR_492={'text':COMBAT_INERT['EDR_492']},
                     EDR_492t={'text':'衝刺','attack':1,'health':1})
        return state,cards,dict(kind='play',entity_id=5)

    def test_summons_three_rushers_that_can_trade_but_cannot_hit_face(self):
        state,cards,play=self.mother()
        before=copy.deepcopy(state)
        after=simulate_card(state,play,cards).state
        self.assertEqual(state,before)
        self.assertEqual(after['players'][0]['mana'],1)
        board=after['players'][0]['board']
        self.assertEqual(len(board),4)
        self.assertEqual(board[0]['tags']['EXHAUSTED'],'1')
        self.assertEqual(len({e['id'] for e in board}),4)
        for duck in board[1:]:
            self.assertIsNone(simulate_card(after,dict(kind='attack',entity_id=duck['id'],target_id=102),cards).state)
            after=simulate_card(after,dict(kind='attack',entity_id=duck['id'],target_id=9),cards).state
        self.assertEqual(after['players'][1]['board'],[])
        self.assertEqual([e['id'] for e in after['players'][0]['board']],[5])

    def test_respects_board_capacity(self):
        state,cards,play=self.mother([unit(i,'1',1,1,EXHAUSTED=1) for i in (1,2,3,4,6)])
        after=simulate_card(state,play,cards).state
        self.assertEqual(len(after['players'][0]['board']),7)
        self.assertEqual(sum(e['card_id']=='EDR_492t' for e in after['players'][0]['board']),1)
        state['players'][0]['board'].append(unit(7,'1',1,1));cards['7']={'text':''}
        self.assertEqual(len(simulate_card(state,play,cards).state['players'][0]['board']),7)
        state['players'][0]['board'].append(unit(8,'1',1,1));cards['8']={'text':''}
        self.assertIsNone(simulate_card(state,play,cards).state)

    def test_repeated_summons_have_distinct_forecast_entity_ids(self):
        state,cards,play=self.mother()
        second=copy.deepcopy(state['players'][0]['hand'][0]);second['id']=6
        state['players'][0]['hand'].append(second)
        state['players'][0]['mana']=8
        after=simulate_card(state,play,cards).state
        after=simulate_card(after,dict(kind='play',entity_id=6),cards).state
        ids=[e['id'] for e in after['players'][0]['board']]
        self.assertEqual(len(ids),7)
        self.assertEqual(len(set(ids)),7)
        self.assertEqual(after['players'][0]['mana'],0)

    def test_search_finds_summon_clear_taunt_then_lethal(self):
        state,cards,play=self.mother([unit(1,'1',6,6,EXHAUSTED=0)])
        state['players'][1]['board'][0]['tags']['TAUNT']='1'
        state['players'][1]['heroes'][0]['tags']['HEALTH']='6'
        plans=card_plans(state,cards,max_depth=6,beam_width=32,time_budget=2)
        self.assertTrue(plans[0]['lethal'])
        self.assertEqual(plans[0]['action']['entity_id'],5)
        self.assertEqual(len(plans[0]['sequence']),5)
        self.assertTrue(plans[0]['complete_turn'])

    def test_changed_token_definition_stops_rollout(self):
        state,cards,play=self.mother()
        cards['EDR_492t']['text']='衝刺 死亡之聲：抽牌'
        self.assertIsNone(simulate_card(state,play,cards).state)

    def test_played_rush_and_charge_attack_limits(self):
        for keyword,face_allowed in [('RUSH',False),('CHARGE',True)]:
            state,cards=fixture([],[],[])
            card=unit(5,'1',2,2,COST=1,**{keyword:1})
            card['tags']['ZONE']='HAND';state['players'][0]['hand']=[card]
            cards['5']={'text':'衝刺' if keyword=='RUSH' else '衝鋒'}
            after=simulate_card(state,dict(kind='play',entity_id=5),cards).state
            attack=simulate_card(after,dict(kind='attack',entity_id=5,target_id=102),cards)
            self.assertEqual(attack.state is not None,face_allowed)

    def test_bronze_whelp_preserves_observed_keywords(self):
        state,cards=fixture([],[],[])
        card=unit(5,'1',4,1,COST=3,LIFESTEAL=1,DIVINE_SHIELD=1)
        card['card_id']='TIME_056';card['tags']['ZONE']='HAND'
        state['players'][0]['hand']=[card];cards['TIME_056']={'text':COMBAT_INERT['TIME_056']}
        action=dict(kind='play',entity_id=5)
        after=simulate_card(state,action,cards).state
        self.assertEqual(after['players'][0]['board'][0]['tags']['DIVINE_SHIELD'],'1')
        card['tags'].pop('LIFESTEAL')
        self.assertIsNone(simulate_card(state,action,cards).state)
