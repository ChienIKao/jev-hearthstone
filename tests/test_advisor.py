import copy
import unittest
from laya_hearthstone.advisor import build_request
from laya_hearthstone.reader import State
from unittest.mock import Mock, patch
from laya_hearthstone.advisor import Decider
from tests.test_strategy import fixture,unit,option
from laya_hearthstone.turn_search import COMBAT_INERT

class OptionTests(unittest.TestCase):
    def test_plan_choices_identify_first_action_and_location_resources(self):
        state,cards=fixture([],[],[option(0,5,[])])
        location=unit(5,'1',0,3,COST=1)
        location.update(card_id='CORE_REV_990')
        location['tags'].update(CARDTYPE='LOCATION',ZONE='HAND')
        state['players'][0]['hand']=[location]
        cards['CORE_REV_990']={'name':'血紅深淵','text':COMBAT_INERT['CORE_REV_990']}
        decider=Decider(cards);decider.load=Mock()
        def choose(router,context,question):
            choices=question['move']['criteria']
            play=next(k for k,v in choices.items() if v.startswith('出牌：血紅深淵；'))
            self.assertIn('血紅深淵 3次可用',choices[play])
            return {'choice':play},{}
        with patch('laya_hearthstone.decision_pipeline.predict_choice',side_effect=choose):
            result=decider.decide(state)
        self.assertEqual(result['action']['entity_id'],5)
        plans=result['search_plans']
        play=next(p for p in plans if p['action']['kind']=='play')
        passed=next(p for p in plans if p['action']['kind']=='end_turn')
        self.assertGreater(play['score'],passed['score'])

    def test_plan_context_overflow_falls_back_to_legal_staged_choice(self):
        from laya_hearthstone.decision_pipeline import ContextBudgetError
        state,cards=fixture([unit(1,'1',3,3,EXHAUSTED=0)],[],[option(0,1,[102])])
        decider=Decider(cards);decider.load=Mock()
        def choose(router,context,question):
            choices=question['move']['criteria']
            if 'other' in choices:raise ContextBudgetError('budget')
            return {'choice':next(iter(choices))},{}
        with patch('laya_hearthstone.decision_pipeline.predict_choice',side_effect=choose):
            result=decider.decide(state)
        self.assertEqual(result['method'],'laya_staged')
        self.assertEqual(result['plan_selection']['skipped'],'context_budget')
        self.assertIn(result['action']['key'],('o0t0','o99'))

    def test_mixed_lethal_is_selected_without_model_and_rechecked(self):
        state,cards=fixture([unit(1,'1',6,6,EXHAUSTED=0)],
                            [unit(2,'2',1,5,TAUNT=1)],
                            [option(0,5,[2,102]),option(1,1,[2])],enemy_health=6)
        dragon=unit(5,'1',6,6,COST=5)
        dragon.update(card_id='TLC_600');dragon['tags']['ZONE']='HAND'
        state['players'][0]['hand']=[dragon]
        cards['TLC_600']={'text':COMBAT_INERT['TLC_600']}
        decider=Decider(cards)
        decider.load=Mock(side_effect=AssertionError('proven lethal must bypass model'))
        result=decider.decide(state)
        self.assertEqual(result['method'],'rules_search_lethal')
        self.assertEqual(result['action']['key'],'o0t0')
        self.assertEqual(len(result['lethal_certificate']['sequence']),2)
        # A new observed legal packet is required for the next decision.
        state['players'][1]['board']=[]
        state['players'][0]['hand']=[]
        state['options']=[option(2,1,[102])]
        next_result=decider.decide(state)
        self.assertEqual(next_result['action']['key'],'o2t0')
        decider.load.assert_not_called()

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
