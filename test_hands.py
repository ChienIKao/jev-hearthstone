import copy
import itertools
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from hands import Hands
from strategy import get_actions
from test_strategy import fixture
from executor import DEFAULT_LAYOUT
import time


class HandsTests(unittest.TestCase):
    def run_case(self, failed=False):
        before,cards=fixture([],[],[])
        before.update(game_serial='test',observed_at=time.time())
        after=copy.deepcopy(before)
        after['players'][0]['current_player']='0'
        action=get_actions(before,cards)[0]['o99']
        events=[]
        current=[before]
        preview=Mock(rect=(0,23,1920,1009))
        preview.close.side_effect=lambda:events.append('preview closed')
        hidden=Mock()
        hidden.close.side_effect=lambda *_:events.append('game restored')
        backend=Mock()
        def click(*args):
            events.append('click')
            if failed:raise ValueError('input failed')
            current[0]=after
        backend.click.side_effect=click
        backend.close.side_effect=lambda:events.append('backend closed')
        def show(*args):
            events.append('preview shown')
            return preview
        def hide(*args):
            events.append('game hidden')
            return hidden
        with tempfile.TemporaryDirectory() as directory:
            hands=Hands.__new__(Hands)
            hands.root_path=Path(directory)
            hands.cards=cards
            hands.layout=copy.deepcopy(DEFAULT_LAYOUT)
            hands.layout.update(confirmed=True,width=1920,height=1009)
            hands.stop_event=Mock()
            hands.stop_event.is_set.return_value=False
            hands.stop_event.wait.return_value=False
            hands.test_results=[]
            hands.last_pointer=None
            with (patch('hands.win') as win,
                  patch('hands.read_state',side_effect=lambda _:current[0]),
                  patch('hands.time.monotonic',side_effect=itertools.count(0,.5)),
                  patch('window_preview.LiveWindowPreview',side_effect=show),
                  patch('maa_input.MaaTouchInput',return_value=backend)):
                win.find_game.return_value=1
                win.minimized.return_value=False
                win.foreground.return_value=False
                win.cursor.return_value=(2500,500)
                win.client_rect.return_value=(0,23,1920,1009)
                win.stop_pressed.return_value=False
                win.U.GetDpiForWindow.return_value=96
                win.U.GetAsyncKeyState.return_value=0
                win.HiddenWindow.side_effect=hide
                hands.run(False,preferred=dict(action,_game_serial='test'))
            record=hands.test_results[-1]
            self.assertEqual(events,['preview shown','game hidden','click','backend closed','game restored','preview closed'])
            self.assertEqual(record['confirmed'],not failed)
            self.assertEqual(record['backend'],'window_preview')
            if not failed:
                self.assertTrue(Path(record['before_state']).exists())
                self.assertTrue(Path(record['after_state']).exists())

    def test_visible_preview_survives_until_game_is_restored(self):
        self.run_case()

    def test_failed_input_still_restores_game_before_closing_preview(self):
        self.run_case(failed=True)


if __name__=='__main__':unittest.main()
