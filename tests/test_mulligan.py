import copy
import time
import unittest
from laya_hearthstone.advisor import fingerprint
from laya_hearthstone.executor import DEFAULT_LAYOUT, validate, build_plan, action_succeeded
from laya_hearthstone.geometry import resized_layout
from laya_hearthstone.reader import State
from laya_hearthstone.strategy import get_actions
from tests.test_strategy import fixture, unit


def opening(first):
    state, cards = fixture([], [], [])
    own = state['players'][0]
    count = 3 if first else 4
    own['current_player'] = '1' if first else '0'
    own['player_tags'] = {'FIRST_PLAYER': '1' if first else '0', 'MULLIGAN_STATE': 'INPUT'}
    own['hand'] = [unit(10+i, '1', ZONE_POSITION=i+1) for i in range(count)]
    if not first:
        own['hand'].append(unit(72, '1', ZONE_POSITION=5))
    state.update(game_serial='test', observed_at=time.time(), options_fresh=False,
                 choices={'1':dict(id=1,type='MULLIGAN',complete=True,entities=[e['id'] for e in own['hand']])})
    layout = copy.deepcopy(DEFAULT_LAYOUT)
    layout.update(confirmed=True,width=1920,height=1009,
                  mulligan_overrides={str(count):[[.5+(i-(count-1)/2)*.126,.46] for i in range(count)]})
    return state, cards, layout


class MulliganTests(unittest.TestCase):
    def test_adjacent_player_choice_packets_finish_previous_packet(self):
        s=State()
        s.entity(2)['tags'].update(CARDTYPE='PLAYER',PLAYER_ID='1')
        s.entity(3)['tags'].update(CARDTYPE='PLAYER',PLAYER_ID='2')
        s.feed('GameState.DebugPrintEntityChoices() - id=1 Player=2 TaskList= ChoiceType=MULLIGAN CountMin=0 CountMax=5')
        s.feed('GameState.DebugPrintEntityChoices() - Entities[0]=[id=29]')
        s.feed('GameState.DebugPrintEntityChoices() - id=2 Player=3 TaskList= ChoiceType=MULLIGAN CountMin=0 CountMax=3')
        self.assertTrue(s.choices['1']['complete'])
        self.assertFalse(s.choices['2']['complete'])
        s.feed('')
        self.assertTrue(s.choices['2']['complete'])

    def test_first_and_second_player_subsets_exclude_coin(self):
        for first in (True,False):
            state,cards,layout=opening(first)
            actions,_=get_actions(state,cards)
            self.assertEqual(len(actions),8 if first else 16)
            for action in actions.values():
                self.assertNotIn(72,action['replace_ids'])
                advice=dict(status='suggestion',state_fingerprint=fingerprint(state),action=action)
                self.assertEqual(validate(state,advice,layout,1366,768,cards),action)
                plan=build_plan(state,action,resized_layout(layout,1366,768))
                self.assertEqual(len([c for c in plan if c['op']=='click']),len(action['replace_ids'])+1)

    def test_reject_incomplete_packet_missing_card_and_modified_selection(self):
        state,cards,layout=opening(False)
        action=list(get_actions(state,cards)[0].values())[1]
        advice=dict(status='suggestion',state_fingerprint=fingerprint(state),action=dict(action,replace_ids=[72]))
        with self.assertRaises(ValueError):validate(state,advice,layout,1920,1009,cards)
        state['choices']['1']['complete']=False
        with self.assertRaises(ValueError):get_actions(state,cards)
        state['choices']['1']['complete']=True
        state['players'][0]['hand'].pop(0)
        with self.assertRaises(ValueError):get_actions(state,cards)

    def test_confirmation_requires_exact_submitted_set_in_same_game(self):
        state,cards,_=opening(False)
        action=list(get_actions(state,cards)[0].values())[1]
        after=copy.deepcopy(state)
        after['players'][0]['player_tags']['MULLIGAN_STATE']='DONE'
        self.assertFalse(action_succeeded(state,after,action))
        after['sent_choice']=dict(id=1,type='MULLIGAN',complete=True,entities=[i for i in action['opening_ids'] if i not in action['replace_ids']])
        self.assertTrue(action_succeeded(state,after,action))
        after['sent_choice']['entities']=[]
        self.assertFalse(action_succeeded(state,after,action))

    def test_reader_tracks_both_players_and_submitted_selection(self):
        s=State()
        for line in ['CREATE_GAME','Player EntityID=2','tag=CARDTYPE value=PLAYER','tag=PLAYER_ID value=1']:
            s.feed('GameState.DebugPrintPower() - '+line)
        s.feed('GameState.DebugPrintEntityChoices() - id=7 Player=2 TaskList=5 ChoiceType=MULLIGAN CountMin=0 CountMax=3')
        for i in range(3):
            s.feed(f'GameState.DebugPrintEntityChoices() - Entities[{i}]=[entityName=UNKNOWN id={10+i} zone=DECK]')
        self.assertFalse(s.snapshot()['choices']['1']['complete'])
        s.feed('')
        self.assertEqual(s.snapshot()['choices']['1']['entities'],[10,11,12])
        s.feed('GameState.SendChoices() - id=7 ChoiceType=MULLIGAN')
        s.feed('GameState.SendChoices() - m_chosenEntities[0]=[entityName=Card id=11 zone=HAND]')
        s.feed('')
        self.assertEqual(s.snapshot()['sent_choice'],dict(id=7,type='MULLIGAN',complete=True,entities=[11],revision=6))
        s.feed('GameState.DebugPrintPower() - CREATE_GAME')
        self.assertEqual(s.snapshot()['choices'],{})
        self.assertIsNone(s.snapshot()['sent_choice'])

    def test_android_choice_accepts_empty_task_list(self):
        s=State()
        for line in ['CREATE_GAME','Player EntityID=2','tag=CARDTYPE value=PLAYER','tag=PLAYER_ID value=1']:
            s.feed('GameState.DebugPrintPower() - '+line)
        s.feed('GameState.DebugPrintEntityChoices() - id=1 Player=2 TaskList= ChoiceType=MULLIGAN CountMin=0 CountMax=3')
        for i in range(3):
            s.feed(f'GameState.DebugPrintEntityChoices() - Entities[{i}]=[id={10+i} zone=HAND]')
        s.feed('')
        self.assertEqual(s.snapshot()['choices']['1'],dict(id=1,type='MULLIGAN',entities=[10,11,12],complete=True,revision=5))


if __name__ == '__main__':
    unittest.main()
