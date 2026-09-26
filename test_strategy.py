import unittest
from strategy import rank_actions, max_spend, get_actions, card_cost


def unit(key, side, attack=3, health=3, **tags):
    return {'id':key,'card_id':str(key),'tags':dict(CONTROLLER=side,CARDTYPE='MINION',ZONE='PLAY',ATK=str(attack),HEALTH=str(health),**{k:str(v) for k,v in tags.items()})}


def fixture(friend,foe,options,enemy_health=30,own_health=30):
    players=[]
    for side,board,health in [('1',friend,own_health),('2',foe,enemy_health)]:
        hero={'id':100+int(side),'card_id':'H','tags':{'CONTROLLER':side,'CARDTYPE':'HERO','HEALTH':str(health),'ZONE':'PLAY'}}
        players.append({'controller':side,'current_player':'1' if side=='1' else '0','mana':5,'hand':[],'board':board,'heroes':[hero],'hero_powers':[],'secret_count':0})
    state={'players':players,'local_controller':'1','game_state':'RUNNING','turn':'4','options_fresh':True,'unresolved_events':0,'options':options}
    state['options'].append({'index':99,'type':'END_TURN','error':'INVALID','entity_id':None,'targets':[],'unsupported':False})
    cards={e['card_id']:{'name':e['card_id'],'text':'','type':'MINION'} for e in friend+foe}
    return state,cards


def option(idx,source,targets):
    return {'index':idx,'type':'POWER','entity_id':source,'error':'NONE','targets':[{'index':i,'entity_id':t,'error':'NONE'} for i,t in enumerate(targets)],'unsupported':False}


class StrategyTests(unittest.TestCase):
    def test_zero_cost_coin_without_cost_tag_is_playable_at_zero_mana(self):
        state,cards=fixture([],[],[option(0,50,[])])
        state['players'][0]['mana']=0
        state['players'][0]['hand']=[{'id':50,'card_id':'GAME_005','tags':{'CONTROLLER':'1','CARDTYPE':'SPELL','ZONE':'HAND'}}]
        cards['GAME_005']={'cost':0,'type':'SPELL','name':'幸運幣'}
        actions,unsupported=get_actions(state,cards)
        self.assertIn('o0',actions)
        self.assertEqual(actions['o0']['cost'],0)
        self.assertEqual(unsupported,[])

    def test_cost_tags_override_zero_base_and_unknown_cost_stays_unknown(self):
        cards={'coin':{'cost':0},'paid':{'cost':5}}
        self.assertEqual(card_cost({'card_id':'coin','tags':{'COST':'2'}},cards),2)
        self.assertEqual(card_cost({'card_id':'paid','tags':{'COST':'0'}},cards),0)
        self.assertIsNone(card_cost({'card_id':'paid','tags':{}},cards))

    def test_two_attacks_find_lethal(self):
        state,cards=fixture([unit(1,'1',4),unit(2,'1',3)],[],[option(0,1,[102]),option(1,2,[102])],7)
        lethal=rank_actions(state,cards)['lethal']
        self.assertEqual(len(lethal['sequence']),2)
        self.assertEqual(lethal['action']['target_id'],102)

    def test_taunt_requires_trade_before_face(self):
        state,cards=fixture([unit(1,'1',2,4),unit(2,'1',5,5)],[unit(3,'2',1,2,TAUNT=1)],[option(0,1,[3]),option(1,2,[3])],5)
        lethal=rank_actions(state,cards)['lethal']
        self.assertEqual(lethal['sequence'][0],(1,3))
        self.assertEqual(lethal['sequence'][1],(2,102))

    def test_shield_prevents_false_lethal(self):
        state,cards=fixture([unit(1,'1',2,4),unit(2,'1',5,5)],[unit(3,'2',1,2,TAUNT=1,DIVINE_SHIELD=1)],[option(0,1,[3]),option(1,2,[3])],5)
        self.assertIsNone(rank_actions(state,cards)['lethal'])

    def test_secret_or_trigger_disables_certificate(self):
        state,cards=fixture([unit(1,'1',7)],[],[option(0,1,[102])],5)
        state['players'][1]['secret_count']=1
        self.assertIsNone(rank_actions(state,cards)['lethal'])
        state['players'][1]['secret_count']=0
        cards['1']['text']='每當此手下攻擊，對自己造成傷害'
        self.assertIsNone(rank_actions(state,cards)['lethal'])

    def test_hero_suicide_filtered(self):
        state,cards=fixture([],[unit(3,'2',5,5)],[option(0,101,[3])],own_health=4)
        state['players'][0]['heroes'][0]['tags']['ATK']='3'
        result=rank_actions(state,cards)
        self.assertEqual([a['kind'] for a in result['ranked']],['end_turn'])
        self.assertTrue(result['rejected'])

    def test_full_health_heal_is_filtered(self):
        state,cards=fixture([],[],[option(0,50,[101])])
        power={'id':50,'card_id':'HEAL','tags':{'CONTROLLER':'1','CARDTYPE':'HERO_POWER','ZONE':'PLAY','COST':'2'}}
        state['players'][0]['hero_powers']=[power]
        cards['HEAL']={'name':'次級治療術','text':'恢復2點生命值'}
        self.assertEqual([a['kind'] for a in rank_actions(state,cards)['ranked']],['end_turn'])

    def test_mana_combinations_do_not_double_count_target_options(self):
        actions={'a':{'entity_id':1,'cost':3},'b':{'entity_id':1,'cost':3},'c':{'entity_id':2,'cost':2},'d':{'entity_id':3,'cost':4}}
        self.assertEqual(max_spend(actions,5),5)
        self.assertEqual(max_spend(actions,6,exclude=2),4)

if __name__=='__main__':
    unittest.main()
