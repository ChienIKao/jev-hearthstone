import copy
import unittest
from unittest.mock import Mock

from choices import choice_actions
from executor import action_succeeded, build_plan
from android_reader import AndroidReader
from advisor import Decider
from unittest.mock import patch


class ChoiceTests(unittest.TestCase):
    def state(self):
        return dict(game_serial='game',local_controller='1',choices={'1':dict(
            id=3,type='GENERAL',complete=True,count_min=1,count_max=1,entities=[89,90,91],
            cards=[dict(id=i,card_id=f'C{i}',tags={}) for i in (89,90,91)])})

    def test_visible_order_and_exact_confirmation(self):
        state=self.state()
        actions=choice_actions(state,{})
        action=actions['c3:90']
        layout={'choice_overrides':{'3':[[.3,.45],[.5,.45],[.7,.45]]}}
        self.assertEqual(build_plan(state,action,layout),[{'op':'click','point':[.5,.45]}])
        after=copy.deepcopy(state)
        after['sent_choice']=dict(id=3,type='GENERAL',complete=True,entities=[89])
        self.assertFalse(action_succeeded(state,after,action))
        after['sent_choice']['entities']=[90]
        self.assertTrue(action_succeeded(state,after,action))
        self.assertEqual(choice_actions(after,{}),{})

    def test_reused_choice_id_after_rewind_remains_pending(self):
        state=self.state()
        state['choices']['1']['revision']=12
        state['sent_choice']=dict(id=3,type='GENERAL',complete=True,entities=[90],revision=8)
        self.assertEqual(len(choice_actions(state,{})),3)
        state['sent_choice']['revision']=13
        self.assertEqual(choice_actions(state,{}),{})

    def test_multiple_choice_requires_confirmation_and_exact_selected_set(self):
        state=self.state()
        packet=state['choices']['1']
        packet['complete']=False
        with self.assertRaises(ValueError):choice_actions(state,{})
        packet['complete']=True
        packet['count_max']=2
        actions=choice_actions(state,{})
        self.assertEqual(len(actions),6)
        action=actions['c3:89,91']
        layout={'choice_overrides':{'3':[[.3,.45],[.5,.45],[.7,.45]]}}
        with self.assertRaises(ValueError):build_plan(state,action,layout)
        layout['choice_confirm']=[.5,.8]
        plan=build_plan(state,action,layout)
        self.assertEqual([p['point'] for p in plan if p['op']=='click'],[[.3,.45],[.7,.45],[.5,.8]])
        after=copy.deepcopy(state)
        after['sent_choice']=dict(id=3,type='GENERAL',complete=True,entities=[91,89])
        self.assertTrue(action_succeeded(state,after,action))

    def test_rewind_choices_use_card_identity_instead_of_packet_order(self):
        from android_layout import default_layout
        from geometry import resized_layout
        state=self.state()
        packet=state['choices']['1']
        packet['entities']=[89,90]
        packet['cards']=[dict(id=89,card_id='TIME_000ta'),dict(id=90,card_id='TIME_000tb')]
        actions=choice_actions(state,{})
        layout=resized_layout(default_layout(),1280,720)
        keep=build_plan(state,actions['c3:89'],layout)[0]['point']
        rewind=build_plan(state,actions['c3:90'],layout)[0]['point']
        self.assertGreater(keep[0],rewind[0])
        self.assertAlmostEqual(keep[0],.305)
        self.assertEqual(keep[1],.745)

    def test_android_snapshot_is_independent_of_next_poll(self):
        device=Mock(serial='test')
        device.command.side_effect=[b'Hearthstone_2026_09_27_1\n',b'']*2
        reader=AndroidReader(device)
        reader.poll()
        reader.state.choices={'1':dict(id=1,type='MULLIGAN',entities=[10],complete=True)}
        before=reader.poll()
        reader.state.choices['1']['entities'].append(11)
        self.assertEqual(before['choices']['1']['entities'],[10])

    def test_laya_receives_candidates_and_returns_only_a_legal_choice(self):
        state=self.state()
        state['game_state']='RUNNING'
        state['players']=[{'controller':'1'},{'controller':'2'}]
        decider=Decider({})
        decider.router=Mock()
        from test_decision_pipeline import fake_agent
        decider.router.load.return_value=fake_agent()
        decider.router.predict.return_value={'answers':{'move':{'choice':'c3:90'}}}
        with patch.object(decider,'load'):
            self.assertEqual(decider.decide(state)['action']['entity_id'],90)
            decider.router.predict.return_value={'answers':{'move':{'choice':'c3:999'}}}
            with self.assertRaises(ValueError):decider.decide(state)


if __name__=='__main__':
    unittest.main()
