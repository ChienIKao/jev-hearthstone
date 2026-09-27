import copy
import unittest
from test_strategy import fixture,unit,option
from enchantments import enchantment_boundary,ORIGIN_TEXT,STATIC_EFFECTS
from card_simulator import simulate_card


class EnchantmentTests(unittest.TestCase):
    def setup_effect(self,cid,target):
        state,cards=fixture([unit(1,'1',3,3,EXHAUSTED=0)],[],[option(0,1,[102])])
        text,origin,_=STATIC_EFFECTS[cid]
        cards[cid]={'text':text}
        cards[origin]={'text':ORIGIN_TEXT[origin],'dbfId':777}
        state['enchantments']=[dict(card_id=cid,tags=dict(ZONE='PLAY',CREATOR_DBID='777',ATTACHED=str(target)))]
        return state,cards

    def test_starting_health_uses_observed_health_without_applying_bonus_twice(self):
        state,cards=self.setup_effect('TLC_835e',102)
        state['players'][1]['heroes'][0]['tags']['HEALTH']='40'
        state['enchantments'][0]['tags']['TAG_SCRIPT_DATA_NUM_1']='40'
        before=copy.deepcopy(state)
        self.assertIsNone(enchantment_boundary(state,cards))
        after=simulate_card(state,dict(kind='attack',entity_id=1,target_id=102),cards).state
        hero=after['players'][1]['heroes'][0]
        self.assertEqual((hero['tags']['HEALTH'],hero['tags']['DAMAGE']),('40','3'))
        self.assertEqual(state,before)
        state['players'][1]['heroes'][0]['tags']['HEALTH']='30'
        self.assertIsNotNone(enchantment_boundary(state,cards))

    def test_static_attack_buff_is_already_in_attack_tag(self):
        state,cards=self.setup_effect('REV_990e',1)
        after=simulate_card(state,dict(kind='attack',entity_id=1,target_id=102),cards).state
        self.assertEqual(after['players'][1]['heroes'][0]['tags']['DAMAGE'],'3')

    def test_removed_effects_do_not_block_but_unknown_active_effects_do(self):
        state,cards=fixture([],[],[])
        for zone in ('GRAVEYARD','REMOVEDFROMGAME'):
            state['enchantments']=[dict(card_id='UNKNOWN',tags={'ZONE':zone})]
            self.assertIsNone(enchantment_boundary(state,cards))
        state['enchantments'][0]['tags']['ZONE']='SETASIDE'
        self.assertIsNotNone(enchantment_boundary(state,cards))

    def test_changed_card_text_or_creator_returns_unknown(self):
        state,cards=self.setup_effect('JAIL_430e1',3)
        self.assertIsNone(enchantment_boundary(state,cards))
        state['enchantments'][0]['tags']['CREATOR_DBID']='778'
        self.assertIsNotNone(enchantment_boundary(state,cards))
        state['enchantments'][0]['tags']['CREATOR_DBID']='777'
        cards['JAIL_430']['text']='Whenever a minion attacks, draw a card'
        self.assertIsNotNone(enchantment_boundary(state,cards))

    def test_missing_attachment_and_unknown_zone_are_not_ignored(self):
        state,cards=self.setup_effect('REV_990e',1)
        del state['enchantments'][0]['tags']['ATTACHED']
        self.assertIsNotNone(enchantment_boundary(state,cards))
        state['enchantments'][0]['tags']['ATTACHED']='1'
        state['enchantments'][0]['tags']['ZONE']='UNKNOWN'
        self.assertIsNotNone(enchantment_boundary(state,cards))
