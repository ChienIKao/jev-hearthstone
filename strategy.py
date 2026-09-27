"""Deterministic filters and a deliberately bounded combat model."""
import copy
import html
import re
import time
from functools import lru_cache

ZONES = ('hand', 'board', 'heroes', 'hero_powers', 'weapons')


def number(entity, tag, default=0):
    try:
        return int(entity.get('tags', {}).get(tag, default))
    except (ValueError, TypeError):
        return default


def hp(entity):
    return number(entity, 'HEALTH') - number(entity, 'DAMAGE')


def card_cost(entity,cards):
    value=entity.get('tags',{}).get('COST')
    if value is not None:
        try:return max(0,int(value))
        except (ValueError,TypeError):return None
    if cards.get(entity.get('card_id'),{}).get('cost')==0:
        return 0
    return None


def text_of(entity, cards):
    text = cards.get(entity.get('card_id'), {}).get('text', '')
    return html.unescape(re.sub(r'<[^>]+>|\[x\]', '', text)).replace('\n', ' ')


def name_of(entity, cards):
    return cards.get(entity.get('card_id'), {}).get('name') or entity.get('name') or entity.get('card_id') or f"實體 {entity['id']}"


def sides(state):
    own = next((p for p in state['players'] if p['controller'] == state.get('local_controller')), None)
    enemy = next((p for p in state['players'] if p['controller'] != state.get('local_controller')), None)
    if own is None or enemy is None:
        raise ValueError('尚未辨識双方玩家')
    return own, enemy


def entity_map(state):
    return {e['id']: e for p in state['players'] for zone in ZONES for e in p.get(zone, [])}


def get_actions(state, cards):
    if state.get('game_state') != 'RUNNING':
        raise ValueError('等待進入對局')
    own, enemy = sides(state)
    from choices import pending_choice, choice_actions
    if pending_choice(state) is not None:
        return choice_actions(state, cards), []
    if own.get('player_tags', {}).get('MULLIGAN_STATE') == 'INPUT':
        if state.get('unresolved_events'):
            raise ValueError('玩家事件尚未完整解析')
        from mulligan import mulligan_actions
        return mulligan_actions(state, cards), []
    if own.get('current_player') != '1':
        raise ValueError('等待我方回合')
    if own.get('player_tags', {}).get('MULLIGAN_STATE') not in (None, 'DONE'):
        raise ValueError('請先完成起手換牌')
    if not own.get('heroes') or not enemy.get('heroes'):
        raise ValueError('英雄狀態尚未完整')
    if state.get('unresolved_events'):
        raise ValueError('玩家事件尚未完整解析')
    if not state.get('options_fresh'):
        raise ValueError('等待完整可用動作清單')
    entities = entity_map(state)
    counts = {}
    for o in state['options']:
        if o['type'] == 'POWER' and o['error'] == 'NONE':
            counts[o.get('entity_id')] = counts.get(o.get('entity_id'), 0) + 1
    actions = {}
    unsupported = []
    for option in state['options']:
        key = 'o' + str(option['index'])
        if option['type'] == 'POWER' and option['error'] != 'NONE':
            continue
        if option.get('unsupported'):
            unsupported.append(option['index'])
            continue
        if option['type'] == 'END_TURN' and option['error'] in ('INVALID', 'NONE'):
            actions[key] = {'key': key, 'kind': 'end_turn', 'description': '結束回合', 'option_index': option['index'], 'cost': 0}
            continue
        if option['type'] != 'POWER' or option['error'] != 'NONE':
            continue
        source = entities.get(option['entity_id'])
        if source is None or source['tags'].get('CONTROLLER') != own['controller']:
            continue
        card_type = source['tags'].get('CARDTYPE')
        cost = 0
        if source['tags'].get('ZONE') == 'HAND':
            cost=card_cost(source,cards)
            if counts[source['id']] > 1 or cost is None:
                unsupported.append(option['index'])
                continue
            if own.get('mana') is None or cost > own['mana']:
                unsupported.append(option['index'])
                continue
            kind, verb = 'play', '出牌'
        elif card_type == 'HERO_POWER':
            kind, verb, cost = 'hero_power', '英雄能力', number(source, 'COST', 2)
        elif card_type in ('MINION', 'HERO'):
            mechanics=cards.get(source.get('card_id'),{}).get('mechanics',[])
            if number(source,'ATK')<=0 or 'TITAN' in mechanics:
                unsupported.append(option['index'])
                continue
            kind, verb = 'attack', '攻擊'
        elif card_type == 'LOCATION':
            kind, verb = 'location', '使用地點'
        else:
            unsupported.append(option['index'])
            continue
        base = {'kind': kind, 'entity_id': source['id'], 'card_type': card_type, 'cost': cost, 'option_index': option['index']}
        if option['targets']:
            for target in option['targets']:
                if target['error'] != 'NONE' or target['entity_id'] not in entities:
                    continue
                target_entity = entities[target['entity_id']]
                target_key = key + 't' + str(target['index'])
                side = '我方' if target_entity['tags'].get('CONTROLLER') == own['controller'] else '敵方'
                actions[target_key] = dict(base, key=target_key, target_id=target['entity_id'], description=f"{verb}：{name_of(source, cards)} → {side}{name_of(target_entity, cards)}")
        elif kind != 'attack':
            actions[key] = dict(base, key=key, description=f"{verb}：{name_of(source, cards)}")
    return actions, unsupported


def compact_state(state, cards):
    own, enemy = sides(state)
    def card(e):
        definition=cards.get(e.get('card_id'),{})
        value = {'id': e['id'], 'name': name_of(e, cards), 'cost': card_cost(e,cards), 'atk': number(e, 'ATK'), 'hp': hp(e), 'armor': number(e, 'ARMOR'), 'effect': text_of(e, cards)}
        value['card_type']=e.get('tags',{}).get('CARDTYPE',definition.get('type'))
        value['printed_races']=definition.get('races') or ([definition['race']] if definition.get('race') else [])
        if 'CARDRACE' in e.get('tags',{}):
            value['race_tag']=e['tags']['CARDRACE']
        if value['card_type']=='WEAPON':
            value['durability']=(max(0,number(e,'DURABILITY')-number(e,'DAMAGE'))
                                 if 'DURABILITY' in e.get('tags',{}) else None)
        value['tags'] = [k for k in ('TAUNT','DIVINE_SHIELD','POISONOUS','LIFESTEAL','FROZEN','EXHAUSTED','STEALTH','IMMUNE','SILENCED') if number(e, k)]
        return value
    return {'turn': state.get('turn'), 'mana': own.get('mana'), 'me': {z: [card(e) for e in own.get(z, [])] for z in ZONES}, 'opponent': {z: [card(e) for e in enemy.get(z, [])] for z in ('board','heroes','weapons')}, 'opponent_hand_count': len(enemy.get('hand',[])), 'opponent_secrets': enemy.get('secret_count', 0)}


def max_spend(actions, mana, exclude=None):
    groups = {}
    for a in actions.values():
        if a.get('entity_id') != exclude and a['cost'] > 0:
            groups[a['entity_id']] = a['cost']
    totals = {0}
    for cost in groups.values():
        totals |= {v + cost for v in tuple(totals) if v + cost <= mana}
    return max(totals)


def vanilla(e, cards):
    if number(e, 'SILENCED'):
        return True
    # Only this restricted subset is simulated. Triggers, deathrattles, locations,
    # enchantment text and unknown cards make a lethal certificate unavailable.
    definition = cards.get(e.get('card_id'))
    if not definition:
        return False
    if e['tags'].get('CARDTYPE') != 'MINION':
        return False
    clean = re.sub(r'[\s，。、,.;；：:]+', '', text_of(e, cards))
    for keyword in ('嘲諷', '聖盾術', '衝鋒', '衝刺', '風怒', '致命劇毒'):
        clean = clean.replace(keyword, '')
    return not clean and not any(number(e, k) for k in ('DEATHRATTLE','REBORN','LIFESTEAL','IMMUNE','DORMANT','CANT_BE_DAMAGED'))


def attack_lethal(state, actions, cards, time_budget=0.025):
    """Certificate only for attack-only, trigger-free boards; returns first action."""
    own, enemy = sides(state)
    if enemy.get('secret_count', 0) or own.get('secret_count', 0):
        return None
    if any(not vanilla(e, cards) for e in own['board'] + enemy['board']):
        return None
    hero = enemy['heroes'][0]
    if any(number(hero, k) for k in ('IMMUNE','CANT_BE_DAMAGED','CANT_BE_ATTACKED','DIVINE_SHIELD')):
        return None
    candidates = [a for a in actions.values() if a['kind'] == 'attack' and a['card_type'] == 'MINION']
    attackers = {a['entity_id'] for a in candidates}
    if not attackers:
        return None
    friendly = [e for e in own['board'] if e['id'] in attackers]
    foes = list(enemy['board'])
    # Tuple: id, attack, health, shield, taunt, poison, attacks remaining, rush-only.
    def unit(e, is_friend):
        remaining = 1
        if number(e, 'WINDFURY'):
            remaining = max(0, 2-number(e, 'NUM_ATTACKS_THIS_TURN'))
        face_allowed = any(a.get('target_id') == hero['id'] and a['entity_id'] == e['id'] for a in candidates)
        return (e['id'], number(e,'ATK'), hp(e), bool(number(e,'DIVINE_SHIELD')), bool(number(e,'TAUNT')), bool(number(e,'POISONOUS')), remaining, is_friend and bool(number(e,'RUSH')) and not face_allowed)
    start_f = tuple(unit(e, True) for e in friendly)
    start_e = tuple(unit(e, False) for e in foes)
    deadline = time.monotonic() + time_budget
    target_health = hp(hero) + number(hero, 'ARMOR')
    @lru_cache(maxsize=20000)
    def search(fs, es, health):
        if health <= 0:
            return ()
        if time.monotonic() > deadline:
            return None
        if sum(f[1]*f[6] for f in fs if f[2] > 0) < health:
            return None
        taunts = [i for i,e in enumerate(es) if e[2] > 0 and e[4]]
        for i,f in enumerate(fs):
            if f[2] <= 0 or f[6] <= 0 or f[1] <= 0:
                continue
            targets = taunts if taunts else [-1]+[j for j,e in enumerate(es) if e[2]>0]
            for j in targets:
                if j == -1 and f[7]:
                    continue
                nf = list(fs)
                ne = list(es)
                ff = list(f)
                ff[6] -= 1
                nh = health
                if j == -1:
                    nh -= f[1]
                    tid = hero['id']
                else:
                    e = es[j]
                    ee = list(e)
                    tid = e[0]
                    if ee[3]:
                        ee[3] = False
                    else:
                        ee[2] = 0 if f[5] else ee[2]-f[1]
                    if e[1] > 0:
                        if ff[3]:
                            ff[3] = False
                        else:
                            ff[2] = 0 if e[5] else ff[2]-e[1]
                    ne[j] = tuple(ee)
                nf[i] = tuple(ff)
                tail = search(tuple(nf), tuple(ne), nh)
                if tail is not None:
                    return ((f[0], tid),)+tail
        return None
    sequence = search(start_f, start_e, target_health)
    if sequence:
        first = next((a for a in candidates if (a['entity_id'],a['target_id']) == sequence[0]), None)
        if first:
            return {'action': first, 'sequence': sequence, 'scope': 'attack_only_vanilla_board'}
    return None


def rank_actions(state, cards):
    actions, unsupported = get_actions(state, cards)
    own, enemy = sides(state)
    entities = entity_map(state)
    own_hp = hp(own['heroes'][0]) + number(own['heroes'][0], 'ARMOR')
    enemy_hp = hp(enemy['heroes'][0]) + number(enemy['heroes'][0], 'ARMOR')
    pressure = sum(number(e, 'ATK') for e in enemy['board'] if not number(e, 'FROZEN'))
    danger = pressure >= own_hp
    ranked, rejected = [], []
    ally_text = ' '.join(text_of(e, cards) for e in own['board'])
    for action in actions.values():
        a = copy.deepcopy(action)
        score, reasons = 0.0, []
        if a['kind'] == 'end_turn':
            score = -3.0
            reasons.append('保留資源或無有效行動時結束')
        else:
            source = entities[a['entity_id']]
            target = entities.get(a.get('target_id'))
            text = text_of(source, cards)
            if a['kind'] == 'attack':
                attack = number(source, 'ATK')
                if target is None:
                    continue
                if source['tags'].get('CARDTYPE') == 'HERO' and target['tags'].get('CARDTYPE') != 'HERO' and own_hp <= number(target,'ATK') and not number(source,'IMMUNE') and not number(source,'IMMUNE_WHILE_ATTACKING'):
                    rejected.append({'key':a['key'],'reason':'英雄攻擊後會因可見反傷死亡'})
                    continue
                if target['tags'].get('CARDTYPE') == 'HERO':
                    score += attack*1.4 + (8 if attack >= enemy_hp else 0)
                    reasons.append('推進對方英雄血量')
                    if danger:
                        score -= 7
                else:
                    shield = bool(number(target,'DIVINE_SHIELD'))
                    killed = not shield and (attack >= hp(target) or number(source,'POISONOUS')) and not number(target,'IMMUNE')
                    dead = not number(source,'DIVINE_SHIELD') and number(target,'ATK') >= hp(source)
                    value = number(target,'ATK')*1.3 + min(hp(target),8)*0.4
                    score += value if killed else min(attack,hp(target))*0.45
                    if shield:
                        score += 1.8-attack*0.15
                    if dead:
                        score -= number(source,'ATK')*1.0 + min(hp(source),8)*0.35
                    elif killed:
                        score += 3
                        reasons.append('交換後可保留攻擊者')
                    if killed and danger:
                        score += number(target,'ATK')*2
                        reasons.append('降低對手場上可見傷害')
                    if killed and re.search('每當|回合結束|回合開始|降低|抽', text_of(target,cards)):
                        score += 2
                        reasons.append('移除持續效果手下')
            elif a['kind'] in ('play','hero_power','location'):
                cost = a['cost']
                if source['tags'].get('CARDTYPE') == 'MINION':
                    score += 2 + number(source,'ATK')*0.7 + hp(source)*0.45
                    if number(source,'TAUNT') and danger:
                        score += 8
                    if len(own['board']) >= 6 and re.search('召喚', text):
                        score -= 3
                        reasons.append('場位接近上限')
                if '護甲' in text and a['kind']=='hero_power':
                    score += 2 if danger else 0.5
                heal = re.search(r'恢復\s*\$?(\d+)\s*點生命', text)
                if heal and target is not None:
                    synergy = bool(re.search('治療|恢復|溢補|傷害', ally_text))
                    missing = number(target,'DAMAGE')
                    if missing <= 0 and not synergy:
                        rejected.append({'key':a['key'],'reason':'目標滿血，且未發現相關觸發收益'})
                        continue
                    restored = min(missing,int(heal[1]))
                    if target['tags'].get('CONTROLLER') == own['controller']:
                        score += restored*(2.5 if danger else 0.8)
                        reasons.append('補回已損失生命')
                    else:
                        score -= restored*3 + 5
                if target and target['tags'].get('CONTROLLER') != own['controller'] and re.search('賦予|使一個.*獲得',text):
                    score -= 8
                    reasons.append('增益敵方通常不利')
                if re.search('抽|發現',text):
                    score += 2
                    if len(own['hand']) >= 9:
                        score -= 5
                        reasons.append('接近手牌上限')
                    if own.get('deck_count') == 0 and '抽' in text:
                        score -= 6
                        reasons.append('空牌庫抽牌會疲勞')
                if target and '消滅' in text and number(target,'ATK') <= 2 and hp(target) <= 2:
                    score -= 3
                    reasons.append('保留硬解處理更大威脅')
                # Mana is a tie-breaker, not a reason to consume a useless card.
                remaining = max(0,(own.get('mana') or 0)-cost)
                spend = cost + max_spend(actions, remaining, a.get('entity_id'))
                score += min(spend,10)*0.2
                if danger and '所有敵方手下' in text and re.search('傷害|消滅',text):
                    score += 5
                    reasons.append('可考慮清場降低可見威脅')
                if not reasons:
                    reasons.append('比較卡牌效果與後續費用組合')
        a['rule_score'] = round(score,3)
        a['reasons'] = reasons
        ranked.append(a)
    ranked.sort(key=lambda a:(-a['rule_score'],a['key']))
    valid = {a['key']:a for a in ranked}
    lethal = attack_lethal(state,valid,cards)
    return {'ranked':ranked,'rejected':rejected,'unsupported_options':unsupported,'lethal':lethal,'visible_enemy_attack':pressure,'danger_estimate':danger}
