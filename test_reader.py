import unittest
from reader import State

class ReaderTests(unittest.TestCase):
    def test_named_player_mana_and_entity_zone_change(self):
        state = State()
        lines = [
            'CREATE_GAME', 'GameEntity EntityID=1', 'tag=CARDTYPE value=GAME',
            'Player EntityID=3 PlayerID=2', 'tag=CARDTYPE value=PLAYER',
            'tag=PLAYER_ID value=2', 'tag=CONTROLLER value=2',
            'FULL_ENTITY - Creating ID=10 CardID=TEST',
            'tag=CONTROLLER value=2', 'tag=CARDTYPE value=MINION', 'tag=ZONE value=HAND']
        for line in lines:
            state.feed('GameState.DebugPrintPower() - ' + line)
        state.feed('GameState.DebugPrintGame() - PlayerID=2, PlayerName=Tester#123')
        for line in ['TAG_CHANGE Entity=Tester#123 tag=RESOURCES value=5',
                     'TAG_CHANGE Entity=Tester#123 tag=RESOURCES_USED value=2',
                     'TAG_CHANGE Entity=10 tag=ZONE value=PLAY',
                     'TAG_CHANGE Entity=GameEntity tag=TURN value=6']:
            state.feed('GameState.DebugPrintPower() - ' + line)
        snapshot = state.snapshot()
        self.assertEqual(snapshot['turn'], '6')
        self.assertEqual(snapshot['players'][0]['mana'], 3)
        self.assertEqual(snapshot['players'][0]['hand'], [])
        self.assertEqual(snapshot['players'][0]['board'][0]['card_id'], 'TEST')
        state.feed('GameState.DebugPrintPower() - CREATE_GAME')
        self.assertEqual(state.snapshot()['players'], [])
        self.assertEqual(state.player_names, {})

    def test_unresolved_player_is_reported(self):
        state = State()
        state.feed('GameState.DebugPrintPower() - TAG_CHANGE Entity=Unknown#123 tag=RESOURCES value=5')
        self.assertEqual(state.snapshot()['unresolved_events'], 1)

if __name__ == '__main__':
    unittest.main()
