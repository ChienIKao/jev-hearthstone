import unittest
from decision_pipeline import staged_action, predict_choice
from unittest.mock import Mock
from test_strategy import fixture,unit,option
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
