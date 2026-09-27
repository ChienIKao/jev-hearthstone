import copy
import unittest
from test_strategy import fixture,unit
from card_simulator import simulate_card,card_plans,PLAIN_BODIES
from test_strategy import option
from turn_search import COMBAT_INERT


class CardSimulationTests(unittest.TestCase):
    def test_battlecry_clears_taunt_before_face_attack(self):
        state,cards,action=self.dragon()
        attacker=unit(8,'1',6,6,EXHAUSTED=0)
        taunt=unit(7,'2',1,5,TAUNT=1)
        state['players'][0]['board']=[attacker]
        state['players'][1]['board']=[taunt]
        state['players'][1]['heroes'][0]['tags']['HEALTH']='6'
        state['options']=[option(0,5,[7,102]),option(1,8,[7])]
        cards.update({'8':{'text':''},'7':{'text':'嘲諷'}})
        before=copy.deepcopy(state)
        plans=card_plans(state,cards,time_budget=1)
        self.assertTrue(plans[0]['lethal'])
        self.assertEqual(plans[0]['action']['entity_id'],5)
        self.assertEqual(plans[0]['action']['target_id'],7)
        self.assertEqual(len(plans[0]['sequence']),2)
        self.assertEqual(state,before)

    def test_attack_opens_board_slot_for_card(self):
        board=[unit(i,'1',1,1,EXHAUSTED=0 if i==1 else 1) for i in range(1,8)]
        state,cards=fixture(board,[unit(8,'2',1,1)],[option(0,1,[8])])
        card=unit(9,'1',8,8,COST=2)
        card['tags']['ZONE']='HAND'
        state['players'][0]['hand']=[card];cards['9']={'text':''}
        plans=card_plans(state,cards,time_budget=1,max_depth=2)
        self.assertEqual(plans[0]['action']['key'],'o0t0')
        self.assertEqual(len(plans[0]['sequence']),2)
        self.assertIn('8/8',plans[0]['summary'])

    def test_attack_limits_and_simultaneous_poison_shield_damage(self):
        state,cards=fixture([unit(1,'1',1,5,EXHAUSTED=0,WINDFURY=1,DIVINE_SHIELD=1)],
                            [unit(2,'2',1,8,POISONOUS=1)],[])
        attack=dict(kind='attack',entity_id=1,target_id=2)
        first=simulate_card(state,attack,cards).state
        self.assertEqual(first['players'][0]['board'][0]['tags']['EXHAUSTED'],'0')
        self.assertEqual(first['players'][0]['board'][0]['tags']['DIVINE_SHIELD'],'0')
        second=simulate_card(first,attack,cards).state
        self.assertEqual(second['players'][0]['board'],[])
        self.assertEqual(second['players'][1]['board'][0]['tags']['DAMAGE'],'2')
        self.assertIsNone(simulate_card(second,attack,cards).state)

    def test_normal_attack_once_and_summoning_exhaustion(self):
        state,cards=fixture([unit(1,'1',3,3,EXHAUSTED=0)],[],[])
        attack=dict(kind='attack',entity_id=1,target_id=102)
        after=simulate_card(state,attack,cards).state
        self.assertIsNone(simulate_card(after,attack,cards).state)
        card=unit(9,'1',8,8,COST=2);card['tags']['ZONE']='HAND'
        state['players'][0]['hand']=[card];cards['9']={'text':''}
        after=simulate_card(state,dict(kind='play',entity_id=9),cards).state
        self.assertIsNone(simulate_card(after,dict(kind='attack',entity_id=9,target_id=102),cards).state)

    def test_search_chains_cards_without_reusing_them(self):
        state,cards=fixture([],[],[option(0,5,[]),option(1,6,[])])
        for ident in (5,6):
            card=unit(ident,'1',2,2,COST=2)
            card['tags']['ZONE']='HAND'
            state['players'][0]['hand'].append(card)
            cards[str(ident)]={'text':''}
        plans=card_plans(state,cards,time_budget=1)
        self.assertEqual(len(plans[0]['sequence']),2)
        self.assertIn('剩餘法力 1',plans[0]['summary'])
        self.assertIn(plans[0]['action']['key'],('o0','o1'))
        self.assertFalse(plans[0]['action']['key'].startswith('sim:'))

    def test_playing_last_other_dragon_increases_hand_cost(self):
        state,cards=fixture([],[],[])
        for ident,cid,cost in [(5,'CORE_NEW1_023',2),(6,'END_033',4)]:
            card=unit(ident,'1',3,3,COST=cost)
            card['card_id']=cid;card['tags']['ZONE']='HAND'
            state['players'][0]['hand'].append(card)
            cards[cid]={'text':PLAIN_BODIES[cid],'races':['DRAGON'],'cost':7 if cid=='END_033' else 2}
        result=simulate_card(state,dict(kind='play',entity_id=5),cards)
        self.assertEqual(result.state['players'][0]['hand'][0]['tags']['COST'],'7')

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
