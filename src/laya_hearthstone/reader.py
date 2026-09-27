"""Read Hearthstone Power.log into an observable state. Python standard library only."""
from laya_hearthstone.paths import ROOT
import argparse
import json
from pathlib import Path
import re
import time
from laya_hearthstone.snapshot_io import publish_text

class State:
    def __init__(self):
        self.entities = {}
        self.current = None
        self.games = 0
        self.unresolved = 0
        self.player_names = {}
        self.options = []
        self.option_set = None
        self.options_fresh = False
        self.option_current = None
        self.options_collecting = False
        self.game_serial = None
        self.revision = 0
        self.choices = {}
        self.choice_current = None
        self.sent_choice = None
        self.sent_option = None
        self.sent_collecting = False
        self.public_plays = []
        self.pending_plays = {}
        config = ROOT / 'config.json'
        self.local_name = json.loads(config.read_text(encoding='utf-8-sig')).get('local_player_name') if config.exists() else None

    def entity(self, key):
        return self.entities.setdefault(int(key), {'id': int(key), 'card_id': '', 'tags': {}})

    def resolve(self, value):
        if value == 'GameEntity':
            return next((k for k, e in self.entities.items() if e['tags'].get('CARDTYPE') == 'GAME'), None)
        if value in self.player_names:
            player_id = self.player_names[value]
            return next((k for k, e in self.entities.items() if e['tags'].get('PLAYER_ID') == player_id), None)
        if value.isdigit():
            return int(value)
        match = re.search(r'\bid=(\d+)', value)
        if match:
            return int(match[1])
        for key, entity in self.entities.items():
            if entity.get('name') == value:
                return key
        unknown = self.player_names.get('UNKNOWN HUMAN PLAYER')
        if unknown and '#' in value and unknown not in [v for n, v in self.player_names.items() if n != 'UNKNOWN HUMAN PLAYER']:
            self.player_names[value] = unknown
            return self.resolve(value)
        return None

    def publish_play(self,key):
        event=self.pending_plays.get(key)
        entity=self.entities.get(key,{})
        if event and event.get('card_id') and entity.get('tags',{}).get('ZONE') in ('PLAY','GRAVEYARD'):
            self.public_plays.append(dict(event))
            del self.pending_plays[key]

    def feed(self, line):
        sent=re.search(r'GameState\.SendOption\(\) - selectedOption=(\d+) selectedSubOption=(-?\d+) selectedTarget=(\d+) selectedPosition=(\d+)',line)
        if sent:
            self.revision+=1
            self.sent_option=dict(option_index=int(sent[1]),sub_option=int(sent[2]),
                                  target_id=int(sent[3]),position=int(sent[4]),revision=self.revision)
            return
        choice_prefix = 'GameState.DebugPrintEntityChoices() - '
        if choice_prefix in line:
            text = line.split(choice_prefix, 1)[1].strip()
            head = re.match(r'id=(\d+) Player=(.*?) TaskList=\d* ChoiceType=(\S+) CountMin=(\d+) CountMax=(\d+)', text)
            if head:
                if self.choice_current is not None:
                    self.choice_current['complete'] = True
                self.revision += 1
                player = self.resolve(head[2])
                controller = self.entities.get(player, {}).get('tags', {}).get('PLAYER_ID')
                self.choice_current = dict(id=int(head[1]), type=head[3], entities=[], complete=False, revision=self.revision)
                game=next((e['tags'] for e in self.entities.values() if e['tags'].get('CARDTYPE')=='GAME'),{})
                if head[3] != 'MULLIGAN':
                    if game.get('TURN') is not None:self.choice_current['offered_turn']=game['TURN']
                    self.choice_current.update(count_min=int(head[4]), count_max=int(head[5]))
                if controller:
                    self.choices[controller] = self.choice_current
            else:
                entity = re.match(r'Entities\[(\d+)\]=(.*)', text)
                if entity and self.choice_current is not None:
                    self.choice_current['entities'].append(self.resolve(entity[2]))
            return
        if self.choice_current is not None:
            self.choice_current['complete'] = True
            self.choice_current = None
        sent_prefix = 'GameState.SendChoices() - '
        if sent_prefix in line:
            text = line.split(sent_prefix, 1)[1].strip()
            head = re.match(r'id=(\d+) ChoiceType=(\S+)', text)
            if head:
                self.revision += 1
                self.sent_choice = dict(id=int(head[1]), type=head[2], entities=[], complete=False, revision=self.revision)
                self.sent_collecting = True
            else:
                entity = re.match(r'm_chosenEntities\[\d+\]=(.*)', text)
                if entity and self.sent_collecting:
                    self.sent_choice['entities'].append(self.resolve(entity[1]))
            return
        if self.sent_collecting:
            self.sent_choice['complete'] = True
            self.sent_collecting = False
        option_prefix = 'GameState.DebugPrintOptions() - '
        if option_prefix in line:
            text = line.split(option_prefix, 1)[1].strip()
            head = re.fullmatch(r'id=(\d+)', text)
            if head:
                self.revision += 1
                self.option_set = int(head[1])
                self.options = []
                self.option_current = None
                self.options_fresh = False
                self.options_collecting = True
                return
            main = re.match(r'option (\d+) type=(\S+) mainEntity=(.*?) error=(\S+)', text)
            if main:
                self.option_current = {'index': int(main[1]), 'type': main[2], 'entity_id': self.resolve(main[3]), 'error': main[4], 'targets': [], 'unsupported': False}
                self.options.append(self.option_current)
                return
            target = re.match(r'target (\d+) entity=(.*?) error=(\S+)', text)
            if target and self.option_current is not None:
                self.option_current['targets'].append({'index': int(target[1]), 'entity_id': self.resolve(target[2]), 'error': target[3]})
                return
            if self.option_current is not None:
                self.option_current['unsupported'] = True
            return
        if self.options_collecting:
            self.options_collecting = False
            self.options_fresh = True

        meta = re.search(r'GameState.DebugPrintGame\(\) - PlayerID=(\d+), PlayerName=(.*)', line)
        if meta:
            self.player_names[meta[2].strip()] = meta[1]
            return
        # Use one stream; GameState also emits duplicate power events.
        prefix = 'GameState.DebugPrintPower() - '
        if prefix not in line:
            return
        self.options_fresh = False
        self.revision += 1
        text = line.split(prefix, 1)[1].strip()
        if text == 'CREATE_GAME':
            self.public_plays = []
            self.pending_plays = {}
            self.sent_option = None
            self.choices = {}
            self.choice_current = None
            self.sent_choice = None
            self.sent_collecting = False
            self.game_serial = line.split(' GameState.', 1)[0].strip()
            self.options = []
            self.option_set = None
            self.options_fresh = False
            self.options_collecting = False
            self.entities.clear()
            self.player_names.clear()
            self.unresolved = 0
            self.current = None
            self.games += 1
            return
        play=re.match(r'BLOCK_START BlockType=PLAY Entity=(.*?) EffectCardId=',text)
        if play:
            self.current=None
            descriptor=play[1]
            key=self.resolve(descriptor)
            zone=re.search(r'\bzone=(\w+)',descriptor)
            owner=re.search(r'\bplayer=(\d+)',descriptor)
            card=re.search(r'\bcardId=([^\s\]]*)',descriptor)
            # A location activation or hero power is not a card played from hand.
            if key is not None and zone and zone[1]=='HAND' and owner:
                game=next((e['tags'] for e in self.entities.values() if e['tags'].get('CARDTYPE')=='GAME'),{})
                self.pending_plays[key]=dict(entity_id=key,controller=owner[1],
                    card_id=card[1] if card else '',turn=game.get('TURN'),revision=self.revision)
            return
        match = re.match(r'(?:GameEntity|Player) EntityID=(\d+)', text)
        if not match:
            match = re.match(r'FULL_ENTITY - Creating ID=(\d+)', text)
        if match:
            self.current = int(match[1])
            entity = self.entity(self.current)
            card = re.search(r'CardID=(\S*)', text)
            if card:
                entity['card_id'] = card[1]
            return
        match = re.match(r'(?:SHOW_ENTITY|CHANGE_ENTITY) - Updating Entity=(.*?) CardID=(\S*)', text)
        if match:
            self.current = self.resolve(match[1])
            if self.current is not None:
                entity = self.entity(self.current)
                entity['card_id'] = match[2]
                name = re.search(r'entityName=(.*?) id=', match[1])
                if name and not name[1].startswith('UNKNOWN'):
                    entity['name'] = name[1]
                if self.current in self.pending_plays:
                    self.pending_plays[self.current]['card_id']=match[2]
                    self.publish_play(self.current)
            return
        match = re.match(r'TAG_CHANGE Entity=(.*?) tag=(\S+) value=(\S+)', text)
        if match:
            self.current = None
            key = self.resolve(match[1])
            if key is None:
                self.unresolved += 1
                return
            entity = self.entity(key)
            entity['tags'][match[2]] = match[3]
            if match[2]=='ZONE':self.publish_play(key)
            name = re.search(r'entityName=(.*?) id=', match[1])
            if name and not name[1].startswith('UNKNOWN'):
                entity['name'] = name[1]
            return
        match = re.match(r'tag=(\S+) value=(\S+)', text)
        if match and self.current is not None:
            self.entity(self.current)['tags'][match[1]] = match[2]
            if match[1]=='ZONE':self.publish_play(self.current)
        elif not match:
            self.current = None

    def snapshot(self):
        for packet in self.choices.values():
            if packet['type'] != 'MULLIGAN':
                packet['cards'] = [self.entities.get(eid, {'id': eid, 'card_id': '', 'tags': {}})
                                   for eid in packet['entities']]
        players = []
        for entity in self.entities.values():
            tags = entity['tags']
            if tags.get('CARDTYPE') != 'PLAYER':
                continue
            controller = tags.get('PLAYER_ID', tags.get('CONTROLLER'))
            cards = [e for e in self.entities.values() if e['tags'].get('CONTROLLER') == controller]
            def zone(name):
                return sorted([e for e in cards if e['tags'].get('ZONE') == name and e['tags'].get('CARDTYPE') != 'PLAYER'], key=lambda e: int(e['tags'].get('ZONE_POSITION', 0)))
            mana_keys = ('RESOURCES', 'RESOURCES_USED', 'TEMP_RESOURCES')
            mana = None
            if 'RESOURCES' in tags:
                mana = int(tags['RESOURCES']) - int(tags.get('RESOURCES_USED', 0)) + int(tags.get('TEMP_RESOURCES', 0))
            players.append({'controller': controller, 'current_player': tags.get('CURRENT_PLAYER'), 'mana': mana, 'resource_tags': {k: tags[k] for k in mana_keys if k in tags}, 'hand': zone('HAND'), 'board': [e for e in zone('PLAY') if e['tags'].get('CARDTYPE') in ('MINION', 'LOCATION')], 'heroes': [e for e in zone('PLAY') if e['tags'].get('CARDTYPE') == 'HERO'], 'hero_powers': [e for e in zone('PLAY') if e['tags'].get('CARDTYPE') == 'HERO_POWER'], 'weapons': [e for e in zone('PLAY') if e['tags'].get('CARDTYPE') == 'WEAPON'], 'secret_count': len(zone('SECRET')), 'deck_count': len(zone('DECK')), 'player_tags': {k: tags[k] for k in ('FIRST_PLAYER','MULLIGAN_STATE','PLAYSTATE','FATIGUE','SPELLPOWER','HEALING_DOES_DAMAGE','TIMEOUT') if k in tags}})
        game = next((e['tags'] for e in self.entities.values() if e['tags'].get('CARDTYPE') == 'GAME'), {})
        return {'public_plays': [dict(e) for e in self.public_plays], 'enchantments': [dict(e, tags=dict(e['tags'])) for e in self.entities.values() if e['tags'].get('CARDTYPE') == 'ENCHANTMENT'], 'choices': self.choices, 'sent_choice': self.sent_choice, 'sent_option': self.sent_option, 'game_serial': self.game_serial, 'revision': self.revision, 'games_seen': self.games, 'turn': game.get('TURN'), 'step': game.get('STEP'), 'game_state': game.get('STATE'), 'players': players, 'unresolved_events': self.unresolved, 'local_controller': self.player_names.get(self.local_name), 'options': self.options, 'option_set': self.option_set, 'options_fresh': self.options_fresh and not self.options_collecting, 'status': 'observed_partial_state' if players else 'waiting_for_game'}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--logs', type=Path, default=Path(r'D:\Battle.net\Hearthstone\Logs'))
    parser.add_argument('--file', type=Path, help='Replay a specific log and exit')
    parser.add_argument('--output', type=Path, default=ROOT / 'state.json')
    parser.add_argument('--interval', type=float, default=0.1)
    args = parser.parse_args()
    state = State()
    if args.file:
        with args.file.open(encoding='utf-8', errors='replace') as stream:
            for line in stream:
                state.feed(line)
        args.output.write_text(json.dumps(state.snapshot(), ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'output': str(args.output), 'games': state.games, 'entities': len(state.entities), 'unresolved': state.unresolved}))
        return
    path = None
    position = 0
    pending = ''
    last = None
    last_scan = 0
    newest = None
    last_data = time.monotonic()
    last_report = None
    print('Watching logs. Ctrl+C to stop.', flush=True)
    while True:
        if time.monotonic() - last_scan >= 2:
            candidates = list(args.logs.glob('*/Power.log'))
            newest = max(candidates, key=lambda p: p.parent.name) if candidates else None
            last_scan = time.monotonic()
        if newest is None:
            time.sleep(1)
            continue
        if newest != path or newest.stat().st_size < position:
            path, position, pending, state = newest, 0, '', State()
            print('Log: ' + str(path), flush=True)
        with path.open('rb') as stream:
            stream.seek(position)
            data = stream.read()
            position = stream.tell()
        if data:
            last_data = time.monotonic()
        elif (state.options_collecting or state.choice_current is not None or state.sent_collecting) and not pending and time.monotonic() - last_data >= 0.2:
            state.feed('')
        # Buffer bytes so a partial UTF-8 character survives a polling boundary.
        if isinstance(pending, str):
            pending = b''
        lines = (pending + data).split(b'\n')
        pending = lines.pop()
        for line in lines:
            state.feed(line.decode('utf-8', errors='replace'))
        snapshot = state.snapshot()
        snapshot['source'] = str(path)
        snapshot['bytes_read'] = position
        snapshot['observed_at'] = time.time()
        snapshot['source_updated_at'] = path.stat().st_mtime
        encoded = json.dumps(snapshot, ensure_ascii=False, indent=2)
        if encoded != last:
            if not publish_text(args.output, encoded):
                print('Snapshot busy; retrying next poll.', flush=True)
                time.sleep(1)
                continue
            report = (state.games, snapshot['turn'], snapshot['game_state'])
            if report != last_report:
                print(f"{snapshot['status']} | game={state.games} | turn={snapshot['turn']} | state={snapshot['game_state']}", flush=True)
                last_report = report
            last = encoded
        time.sleep(max(0.05, args.interval))

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
