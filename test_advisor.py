import copy
import unittest
from advisor import build_request
from reader import State

class OptionTests(unittest.TestCase):
    def test_options_targets_and_invalidation(self):
        state = State()
        for text in ['id=10', '  option 1 type=POWER mainEntity=[entityName=A id=7 zone=PLAY player=2] error=NONE errorParam=', '    target 0 entity=[entityName=B id=8 zone=PLAY player=1] error=REQ_TAUNT errorParam=', '    target 1 entity=[entityName=C id=9 zone=PLAY player=1] error=NONE errorParam=']:
            state.feed('GameState.DebugPrintOptions() - '+text)
        self.assertFalse(state.snapshot()['options_fresh'])
        state.feed('Other event')
        self.assertTrue(state.snapshot()['options_fresh'])
        self.assertEqual(state.options[0]['targets'][1]['entity_id'], 9)
        state.feed('GameState.DebugPrintPower() - TAG_CHANGE Entity=7 tag=EXHAUSTED value=1')
        self.assertFalse(state.snapshot()['options_fresh'])

    def test_only_legal_targets_and_running_local_turn(self):
        def entity(key, player):
            return {'id':key, 'card_id':'A', 'tags':{'CONTROLLER':player,'CARDTYPE':'MINION','ZONE':'PLAY','ATK':'3','HEALTH':'3'}}
        def player(key):
            hero={'id':int(key)+100,'card_id':'H','tags':{'CONTROLLER':key,'CARDTYPE':'HERO','HEALTH':'30','ZONE':'PLAY'}}
            return {'controller':key, 'current_player':'1' if key=='2' else '0', 'mana':3,'hand':[],'heroes':[hero],'hero_powers':[],'board':[entity(int(key),key)]}
        state={'game_state':'RUNNING','local_controller':'2','players':[player('1'),player('2')],'turn':'3','unresolved_events':0,'options_fresh':True,'options':[
            {'index':0,'type':'END_TURN','error':'INVALID','unsupported':False,'entity_id':None,'targets':[]},
            {'index':1,'type':'POWER','error':'NONE','unsupported':False,'entity_id':2,'targets':[{'index':0,'entity_id':2,'error':'REQ_ENEMY_TARGET'},{'index':1,'entity_id':1,'error':'NONE'}]}]}
        _,_,actions=build_request(state,{})
        self.assertEqual(set(actions),{'o0','o1t1'})
        done=copy.deepcopy(state)
        done['game_state']='COMPLETE'
        with self.assertRaises(ValueError):
            build_request(done,{})
        opponent=copy.deepcopy(state)
        opponent['players'][1]['current_player']='0'
        with self.assertRaises(ValueError):
            build_request(opponent,{})

if __name__=='__main__':
    unittest.main()
