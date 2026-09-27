import unittest
from laya_hearthstone.decision_pipeline import staged_action, predict_choice
from unittest.mock import Mock
from tests.test_strategy import fixture,unit,option
from types import SimpleNamespace


def fake_agent():
    class Tokenizer:
        mask_token='[MASK]'
        mask_token_id=3
        cls_token_id=1
        sep_token_id=2
        def __call__(self,text,**kwargs):
            ids=list(range(max(1,len(text)//8)))
            if kwargs.get('truncation'):ids=ids[:kwargs['max_length']]
            return {'input_ids':ids}
    return SimpleNamespace(tok=Tokenizer(),cfg={'max_len':1024,'head_max_len':256})


class StagedDecisionTests(unittest.TestCase):
    def test_soft_prior_breaks_uncertain_pass_but_allows_confident_pass(self):
        state,cards=fixture([unit(1,'1')],[],[option(0,1,[102])])
        def chooser(probability):
            def choose(context,question):
                return dict(choice='a1',probabilities={'a0':1-probability,'a1':probability}),{}
            return choose
        scores={'o0t0':3,'o99':-3}
        action,trace=staged_action(state,cards,None,chooser(.53),scores)
        self.assertEqual(action['kind'],'attack')
        self.assertTrue(trace[0]['heuristic_adjusted'])
        action,trace=staged_action(state,cards,None,chooser(.95),scores)
        self.assertEqual(action['kind'],'end_turn')
        self.assertFalse(trace[0]['heuristic_adjusted'])

    def test_split_development_choices_can_outweigh_pass_preference(self):
        state,cards=fixture([unit(1,'1'),unit(3,'1')],[],[option(0,1,[102]),option(1,3,[102])])
        def choose(context,question):
            return dict(choice='a2',probabilities={'a0':.126,'a1':.126,'a2':.748}),{}
        action,trace=staged_action(state,cards,None,choose,{'o0t0':3.8,'o1t0':5.35,'o99':-3})
        self.assertEqual(action['entity_id'],3)
        self.assertTrue(trace[0]['heuristic_adjusted'])

    def test_context_heavy_options_are_compared_in_pairs(self):
        from unittest.mock import patch
        from laya_hearthstone.decision_pipeline import ContextBudgetError
        router=Mock();router.load.return_value=fake_agent()
        visited=[]
        def batch(router,agent,context,question,maximum,head):
            criteria=question['move']['criteria']
            if len(criteria)>2:raise ContextBudgetError('budget')
            visited.extend(criteria)
            return {'choice':next(iter(criteria))},{'context_tokens':100}
        with patch('laya_hearthstone.decision_pipeline._predict_batch',side_effect=batch):
            answer,budget=predict_choice(router,{}, {'move':dict(type='choice',instructions='choose',criteria={str(i):'short' for i in range(5)})})
        self.assertEqual(set(visited),set('01234'))
        self.assertEqual(answer['choice'],'0')
        self.assertGreater(budget['comparison_calls'],1)

    def test_source_choice_describes_all_targets_without_preselecting_source(self):
        state,cards=fixture([unit(1,'1'),unit(3,'1')],[unit(2,'2')],
                            [option(0,1,[2,102]),option(1,3,[2,102])])
        calls=[]
        def choose(context,question):
            calls.append(question)
            if len(calls)==1:
                self.assertNotIn('→',str(question))
                self.assertNotIn('selected_entity',context)
                values=list(question['move']['criteria'].values())
                self.assertEqual(sum('2,102' in value for value in values),2)
                self.assertTrue(any('結束回合' in value for value in values))
            else:self.assertEqual(context['selected_entity'],1)
            return {'choice':next(iter(question['move']['criteria']))},{}
        staged_action(state,cards,None,choose)
        self.assertEqual(len(calls),2)

    def test_many_choices_are_compared_in_bounded_batches(self):
        router=Mock();router.load.return_value=fake_agent()
        criteria={f'a{i}':str(i)+'x'*320 for i in range(16)}
        def predict(context,question,**kwargs):
            choices=question['move']['criteria']
            return {'answers':{'move':{'choice':max(choices,key=lambda k:int(k[1:]))}}}
        router.predict.side_effect=predict
        answer,budget=predict_choice(router,{}, {'move':dict(type='choice',instructions='choose',criteria=criteria)})
        self.assertEqual(answer['choice'],'a15')
        self.assertGreater(budget['comparison_calls'],1)
        visited=set()
        for call in router.predict.call_args_list:
            visited.update(call.args[1]['move']['criteria'])
            self.assertLessEqual(len(call.args[1]['move']['criteria']),5)
        self.assertEqual(visited,set(criteria))

    def test_long_option_and_instruction_are_preserved_in_context(self):
        import json
        router=Mock();router.load.return_value=fake_agent()
        description='x'*600+'distinct final effect'
        instruction='y'*600+'choose carefully'
        def predict(context,question,**kwargs):
            payload=json.loads(context)
            self.assertEqual(payload['candidate_details']['a'],description)
            self.assertEqual(payload['decision_instructions'],instruction)
            self.assertIn('candidate_details',question['move']['criteria']['a'])
            return {'answers':{'move':{'choice':'a'}}}
        router.predict.side_effect=predict
        answer,_=predict_choice(router,{}, {'move':dict(type='choice',instructions=instruction,criteria={'a':description,'b':'short'})})
        self.assertEqual(answer['choice'],'a')

    def test_over_budget_numeric_state_is_not_silently_truncated(self):
        router=Mock()
        router.load.return_value=fake_agent()
        with self.assertRaisesRegex(ValueError,'輸入預算'):
            predict_choice(router,{'observations':list(range(5000))},
                           {'move':dict(type='choice',instructions='choose',criteria={'a':'A','b':'B'})})
        router.predict.assert_not_called()

    def test_target_selection_preserves_complete_legal_action(self):
        state,cards=fixture([unit(1,'1')],[unit(2,'2')],[option(0,1,[2,102])])
        calls=[]
        def choose(context,question):
            calls.append(question)
            keys=list(question['move']['criteria'])
            return {'choice':keys[-1] if len(calls)==2 else keys[0]},{}
        action,trace=staged_action(state,cards,None,choose)
        self.assertEqual(action['target_id'],102)
        self.assertEqual(action['key'],'o0t1')
        self.assertEqual(len(trace),2)

    def test_hidden_opponent_hand_is_not_sent(self):
        state,cards=fixture([unit(1,'1')],[],[option(0,1,[102])])
        state['players'][1]['hand']=[dict(id=99,card_id='HIDDEN_SECRET',tags={})]
        def choose(context,question):
            self.assertNotIn('HIDDEN_SECRET',str(context))
            self.assertEqual(context['opponent_hand_count'],1)
            return {'choice':list(question['move']['criteria'])[0]},{}
        staged_action(state,cards,None,choose)
