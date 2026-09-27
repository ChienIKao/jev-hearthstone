import copy
import unittest
from test_strategy import fixture,unit
from card_simulator import simulate_card
from turn_search import COMBAT_INERT


class CardSimulationTests(unittest.TestCase):
    def test_actual_localized_armor_power_text(self):
        state,cards=fixture([],[],[])
        power=unit(9,'1',COST=2)
        power['tags']['CARDTYPE']='HERO_POWER'
        state['players'][0]['hero_powers']=[power]
        cards['9']={'text':'<b>英雄能力</b>\n獲得$d2點護甲值'}
        action=dict(kind='hero_power',entity_id=9)
        result=simulate_card(state,action,cards)
        self.assertEqual(result.state['players'][0]['heroes'][0]['tags']['ARMOR'],'2')
        self.assertIsNone(simulate_card(result.state,action,cards).state)

    def dragon(self):
        state,cards=fixture([],[],[])
        dragon=unit(5,'1',6,6,COST=5)
        dragon['card_id']='TLC_600';dragon['tags']['ZONE']='HAND'
        state['players'][0]['hand']=[dragon]
        cards['TLC_600']={'text':COMBAT_INERT['TLC_600']}
        return state,cards,dict(kind='play',entity_id=5,target_id=102)

    def test_dragon_battlecry_damage_armor_mana_and_immutability(self):
        state,cards,action=self.dragon();before=copy.deepcopy(state)
        state['players'][1]['heroes'][0]['tags']['ARMOR']='3'
        before=copy.deepcopy(state)
        result=simulate_card(state,action,cards)
        self.assertIsNone(result.boundary)
        me,foe=result.state['players']
        self.assertEqual(me['mana'],0)
        self.assertEqual(me['heroes'][0]['tags']['ARMOR'],'5')
        self.assertEqual(foe['heroes'][0]['tags']['DAMAGE'],'2')
        self.assertEqual(len(me['hand']),0)
        self.assertEqual(len(me['board']),1)
        self.assertFalse(result.state['options_fresh'])
        self.assertEqual(state,before)

    def test_target_shield_absorbs_damage(self):
        state,cards,action=self.dragon()
        target=unit(7,'2',3,3,DIVINE_SHIELD=1)
        state['players'][1]['board']=[target];cards['7']={'text':''}
        action['target_id']=7
        result=simulate_card(state,action,cards)
        target=result.state['players'][1]['board'][0]
        self.assertEqual(target['tags']['DIVINE_SHIELD'],'0')
        self.assertNotIn('DAMAGE',target['tags'])

    def test_random_card_and_secret_stop_rollout(self):
        state,cards,action=self.dragon()
        state['players'][1]['secret_count']=1
        self.assertIsNone(simulate_card(state,action,cards).state)
        state['players'][1]['secret_count']=0
        state['players'][0]['hand'][0]['card_id']='CATA_556'
        cards['CATA_556']={'text':COMBAT_INERT['CATA_556']}
        self.assertIsNone(simulate_card(state,action,cards).state)
