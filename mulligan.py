"""Opening-hand actions derived from the local player's choice packet."""
from itertools import combinations


def opening_cards(state):
    from strategy import sides
    own, enemy = sides(state)
    if own.get('player_tags', {}).get('MULLIGAN_STATE') != 'INPUT':
        raise ValueError('目前不是起手選牌階段')
    choice = state.get('choices', {}).get(own['controller'])
    if not choice or choice.get('type') != 'MULLIGAN' or not choice.get('complete'):
        raise ValueError('等待完整起手選牌清單')
    sent = state.get('sent_choice') or {}
    if sent.get('id') == choice['id'] and sent.get('type') == 'MULLIGAN':
        raise ValueError('起手選牌已送出，等待結算')
    hand = own['hand']
    # The second player's choice packet includes the coin; it is not a
    # replaceable opening card. FIRST_PLAYER is authoritative for the count.
    if own.get('player_tags', {}).get('FIRST_PLAYER') == '1':
        count = 3
    elif enemy.get('player_tags', {}).get('FIRST_PLAYER') == '1' or own.get('player_tags', {}).get('FIRST_PLAYER') == '0':
        count = 4
    else:
        raise ValueError('等待先後手資訊')
    ordered = sorted(hand, key=lambda e: int(e['tags'].get('ZONE_POSITION', 0)))
    cards = ordered[:count]
    if (len(cards) != count or
        [int(e['tags'].get('ZONE_POSITION', 0)) for e in cards] != list(range(1, count + 1)) or
        any(e['id'] not in choice['entities'] or not e.get('card_id') for e in cards)):
        raise ValueError('起手卡牌尚未到齊')
    return cards, choice


def mulligan_actions(state, definitions):
    from strategy import name_of
    cards, choice = opening_cards(state)
    result = {}
    for count in range(len(cards) + 1):
        for selected in combinations(cards, count):
            ids = [e['id'] for e in selected]
            key = 'm' + str(choice['id']) + ':' + ','.join(map(str, ids))
            description = '全部保留' if not ids else '換掉：' + '、'.join(name_of(e, definitions) for e in selected)
            result[key] = dict(key=key, kind='mulligan', replace_ids=ids,
                               choice_id=choice['id'], opening_ids=[e['id'] for e in cards],
                               description=description, cost=0)
    return result
