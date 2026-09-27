"""Visible in-game choice packets, including Discover and Choose One."""
from itertools import combinations

def pending_choice(state):
    packet = state.get('choices', {}).get(state.get('local_controller'))
    if not packet or packet.get('type') == 'MULLIGAN':
        return None
    # Timed-out decisions can resolve on the server without SendChoices. A new
    # turn invalidates that offer; a new offer carries its own revision/turn.
    if packet.get('offered_turn') is not None and state.get('turn') is not None and str(packet['offered_turn'])!=str(state['turn']):
        return None
    sent = state.get('sent_choice') or {}
    if (sent.get('id') == packet['id'] and sent.get('type') == packet['type']
            and sent.get('revision',0)>=packet.get('revision',0)):
        return None
    return packet


def choice_actions(state, definitions):
    from strategy import name_of
    packet = pending_choice(state)
    if packet is None:
        return {}
    if not packet.get('complete'):
        raise ValueError('等待完整選牌清單')
    cards = packet.get('cards', [])
    if not cards or len(cards) != len(packet['entities']) or any(not c.get('card_id') for c in cards):
        raise ValueError('候選卡牌資料尚未完整')
    result = {}
    minimum, maximum = packet.get('count_min'), packet.get('count_max')
    if not isinstance(minimum,int) or not isinstance(maximum,int) or not 0 <= minimum <= maximum <= len(cards) <= 10:
        raise ValueError('選牌數量範圍無效')
    for count in range(minimum,maximum+1):
        for indices in combinations(range(len(cards)),count):
            selected = [cards[i] for i in indices]
            ids = [c['id'] for c in selected]
            key = f'c{packet["id"]}:'+','.join(map(str,ids))
            result[key] = dict(key=key, kind='choice', choice_id=packet['id'],
                               choice_type=packet['type'], choice_ids=list(packet['entities']),
                               choice_card_ids=[c['card_id'] for c in cards],
                               selected_ids=ids, choice_indices=list(indices),
                               requires_confirm=(minimum,maximum)!=(1,1),
                               description='選擇：'+('、'.join(name_of(c,definitions) for c in selected) or '不選取'),cost=0)
            if len(ids)==1:
                result[key]['entity_id']=ids[0]
    return result
