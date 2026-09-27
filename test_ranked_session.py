from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch

from ranked_session import RankedSession,deadline_action
from menu_navigation import RankedNavigator,menu_step


def state(game,status):
    return dict(game_serial=game,game_state=status,local_controller='1',players=[
        dict(controller='1',player_tags={'PLAYSTATE':'WON'}),dict(controller='2')])


class RankedSessionTests(unittest.TestCase):
    def test_mode_selection_touches_emblem_above_caption(self):
        labels=[dict(text='標準',point=[.497,.537]),
                dict(text='開放',point=[.324,.603]),
                dict(text='休閒模式',point=[.67,.6])]
        for mode,x,y in [('standard',.497,.337),('wild',.324,.403)]:
            step=menu_step(labels,dict(mode=mode))
            self.assertEqual(step['kind'],'click')
            self.assertAlmostEqual(step['point'][0],x)
            self.assertAlmostEqual(step['point'][1],y)

    def test_log_cap_prevents_model_loading_and_queue(self):
        hands=Mock()
        hands.observe.return_value=state('old','COMPLETE')
        hands.reader.check_logging_health.side_effect=ValueError('log cap reached')
        decider=Mock()
        with patch('ranked_session.RankedNavigator') as navigator:
            with self.assertRaisesRegex(ValueError,'log cap'):
                RankedSession(hands,decider,dict(name='龍戰'),threading.Event(),Mock(),1).run()
            navigator.assert_not_called()
            decider.load.assert_not_called()
    def test_result_animation_waits_until_result_overlay(self):
        stop=Mock();stop.is_set.return_value=False
        hands=Mock()
        hands.observe.side_effect=[state('old','COMPLETE'),state('new','RUNNING')]
        labels=[dict(text='敵方回合',point=[.8,.45])]
        with patch('menu_navigation.MenuVision') as vision, patch('menu_navigation.time.monotonic',side_effect=[0,1,100]):
            vision.return_value.read.return_value=labels
            navigator=RankedNavigator(Mock(),Mock(),stop)
            self.assertEqual(navigator.enter_game(hands,dict(name='龍戰',mode='standard'),'old')['game_serial'],'new')
            navigator.device.execute.assert_not_called()
        prompt=[dict(text='輕點以繼續',point=[.5,.94])]
        self.assertEqual(menu_step(prompt,{},completed=True)['kind'],'click')
        self.assertEqual(menu_step(prompt,{},completed=False)['kind'],'wait')

    def test_deadline_uses_game_timeout_and_does_not_interrupt_choices(self):
        current=state('one','RUNNING')
        current['players'][0]['player_tags']['TIMEOUT']='75'
        end=dict(key='o0',kind='end_turn')
        self.assertIsNone(deadline_action(current,{'o0':end},60))
        self.assertEqual(deadline_action(current,{'o0':end},68),end)
        current['players'][0]['player_tags']['MULLIGAN_STATE']='INPUT'
        self.assertIsNone(deadline_action(current,{'o0':end},80))

    def test_two_games_requeue_with_same_profile_and_stop_at_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            hands=Mock(evidence=Path(folder)/'evidence')
            hands.observe.side_effect=[state('old','COMPLETE'),state('one','COMPLETE'),state('two','COMPLETE')]
            decider=Mock()
            profile=dict(name='龍戰',mode='standard',combos='保留 A')
            with patch('ranked_session.RankedNavigator') as factory:
                navigator=factory.return_value
                navigator.enter_game.side_effect=[state('one','RUNNING'),state('two','RUNNING')]
                session=RankedSession(hands,decider,profile,threading.Event(),Mock(),2)
                profile['name']='changed'
                session.run()
                self.assertEqual(session.completed,2)
                self.assertEqual(navigator.enter_game.call_count,2)
                self.assertEqual(navigator.enter_game.call_args.args[2],'one')
                self.assertEqual(decider.profile['name'],'龍戰')
                self.assertEqual(len((Path(folder)/'ranked-results.jsonl').read_text(encoding='utf-8').splitlines()),2)

    def test_stop_during_model_loading_never_queues(self):
        stop=threading.Event()
        decider=Mock();decider.load.side_effect=stop.set
        with patch('ranked_session.RankedNavigator') as navigator:
            session=RankedSession(Mock(),decider,dict(name='龍戰'),stop,Mock())
            session.run()
            navigator.assert_not_called()


if __name__=='__main__':
    unittest.main()
