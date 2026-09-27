import copy
import tempfile
from pathlib import Path
import unittest

from laya_hearthstone.hsreplay_import import parse_deck_page, decision_reference, parse_meta_page, correct_mulligan
from laya_hearthstone.deck_profiles import DeckProfiles, new_profile


URL='https://hsreplay.net/zh-hant/decks/Tqcm39067GQSMafXBbErHe/'
# Public table observed on 2026-09-27; columns: cost, count, name, four rates, turns held.
ROWS=[
    (1,2,'火炬',59.3,12.8,58.7,52.0,2),
    (1,2,'火砲大師',61.9,95.7,58.6,57.1,.6),
    (1,2,'血紅深淵',59.2,23.1,57.1,53.8,.9),
    (1,2,'運送幼龍',62.7,97.0,59.5,56.8,.9),
    (1,2,'黑暗騎兵',62.0,93.7,59.5,58.7,.8),
    (2,2,'拋鉤猛拉',64.8,93.0,61.3,59.7,1.1),
    (2,2,'暗焰噬襲',60.8,45.6,59.7,56.9,1.4),
    (2,2,'母巢守衛者',62.7,85.0,59.1,59.2,1.3),
    (2,2,'灼熱裂縫',56.9,15.4,57.5,52.5,2),
    (3,2,'噴發火山',58.5,15.2,57.3,51.7,1.6),
    (4,1,'曲齒',53.2,1.7,54.2,50.8,2.3),
    (4,2,'母鴨',61.9,30.3,59.7,54.7,2),
    (4,2,'競技場播報員',62.6,25.8,59.5,55.0,2.2),
    (7,2,'預知滑龍',61.4,64.2,58.9,57.2,2.1),
    (8,2,'巔風飛龍',61.7,17.8,60.3,59.7,2.2),
    (8,1,'破鏈者霍格',53.7,.6,53.4,25.8,2.8),
]


def page_text():
    names='\n'.join(f'{cost}\n{count if count>1 else "★"}\n{name}' for cost,count,name,*_ in ROWS)
    stats='\n'.join('\n'.join([*(f'{v}%' for v in row[3:7]),str(row[7])]) for row in ROWS)
    return '樣本數\n100,000 場\nAvg. Turns Held\n平均而言，捏在手上多久。\n'+names+'\n'+stats+'\nHSReplay.net'


def reference():
    return parse_deck_page(page_text(),URL,'青銅到黃金','過去 30 天','standard',{})


class HSReplayTests(unittest.TestCase):
    def test_extreme_keep_guard_is_optional_and_preserves_borderline_choices(self):
        from tests.test_mulligan import opening
        from laya_hearthstone.strategy import get_actions
        state,_,_=opening(True)
        cards={}
        for entity,name,cost in zip(state['players'][0]['hand'],('運送幼龍','預知滑龍','破鏈者霍格'),(1,7,8)):
            cards[entity['card_id']]=dict(name=name,cost=cost,type='MINION')
        actions,_=get_actions(state,cards)
        chosen=next(a for a in actions.values() if set(a['replace_ids'])=={10})
        ref=reference();ref['guard_mulligan']=True
        corrected=correct_mulligan(ref,state['players'][0]['hand'],cards,chosen,actions)
        self.assertEqual(corrected['replace_ids'],[12])
        ref['guard_mulligan']=False
        self.assertEqual(correct_mulligan(ref,state['players'][0]['hand'],cards,chosen,actions),chosen)
        ref.update(guard_mulligan=True,sample_size=20)
        self.assertEqual(correct_mulligan(ref,state['players'][0]['hand'],cards,chosen,actions),chosen)

    def test_meta_preserves_tiers_samples_and_filters(self):
        text='Core Cards\nA\nDragon Warrior\n58.3%\n120,000\nView Stats\nB\nAura Paladin\n53.6%\n44,000\nView Stats\nHSReplay.net'
        result=parse_meta_page(text,'標準／青銅到黃金／所有伺服器','過去 7 天')
        self.assertEqual(result['rows'][0],dict(name='Dragon Warrior',tier='A',winrate=58.3,matches=120000))
        self.assertEqual(result['rows'][1]['tier'],'B')
        self.assertEqual(result['time_range'],'過去 7 天')
        for invalid in (text.replace('44,000','…'),text.replace('53.6%','153.6%'), 'Core Cards\nA\nB'):
            with self.assertRaises(ValueError):parse_meta_page(invalid,'青銅','7 天')

    def test_saved_reference_reaches_actual_mulligan_prediction(self):
        import json
        from laya_hearthstone.advisor import Decider
        from tests.test_strategy import fixture
        state,cards=fixture([],[],[])
        own=state['players'][0]
        own['player_tags']={'MULLIGAN_STATE':'INPUT','FIRST_PLAYER':'1'}
        state['choices']={'1':dict(id=1,type='MULLIGAN',complete=True,entities=[1,2,3])}
        own['hand']=[{'id':i,'card_id':str(i),'tags':{'ZONE':'HAND','CONTROLLER':'1','CARDTYPE':'MINION','ZONE_POSITION':str(i)}} for i in (1,2,3)]
        cards.update({str(i):{'name':name,'cost':cost,'type':'MINION'} for i,name,cost in [(1,'運送幼龍',1),(2,'火炬',1),(3,'其他牌',8)]})
        class Router:
            def load(self,name):
                from tests.test_decision_pipeline import fake_agent
                return fake_agent()
            def predict(self,context,question,**kwargs):
                self.context=json.loads(context)
                return {'answers':{'move':{'choice':next(iter(question['move']['criteria']))}}}
        decider=Decider(cards,profile=dict(new_profile(),name='龍戰',reference_data=reference()))
        decider.router=Router()
        result=decider.decide(state)
        self.assertEqual(result['method'],'laya')
        context=decider.router.context
        self.assertEqual({r['name'] for r in context['mulligan_reference']['cards']},{'運送幼龍','火炬'})
        self.assertEqual(context['mulligan_reference']['source_url'],URL)

    def test_public_table_pairs_each_card_with_its_statistics(self):
        result=reference()
        self.assertEqual(result['sample_size'],100000)
        self.assertEqual(len(result['cards']),16)
        self.assertEqual(sum(r['count'] for r in result['cards']),30)
        self.assertEqual(result['cards'][5]['name'],'拋鉤猛拉')
        self.assertEqual(result['cards'][5]['keep_percentage'],93)
        self.assertEqual(result['cards'][-1]['mulligan_winrate'],53.7)

    def test_incomplete_or_wrong_page_never_imports(self):
        for text in ('獲取尊爵會員',page_text().replace('25.8%',''),page_text().replace('53.7%','153.7%')):
            with self.assertRaises(ValueError):
                parse_deck_page(text,URL,'青銅','30 天','standard',{})
        with self.assertRaises(ValueError):
            parse_deck_page(page_text(),'https://hsreplay.net.evil.test/decks/abc/','青銅','30 天','standard',{})

    def test_reference_persists_without_overwriting_manual_notes(self):
        with tempfile.TemporaryDirectory() as folder:
            store=DeckProfiles(Path(folder)/'decks.json')
            profile=dict(new_profile(),name='龍戰',mulligan='我的留牌思路',reference_data=reference())
            store.save(profile)
            restored=DeckProfiles(store.path).selected()
            self.assertEqual(restored['mulligan'],'我的留牌思路')
            self.assertEqual(restored['reference_data'],profile['reference_data'])
            invalid=copy.deepcopy(profile)
            invalid['reference_data']['cards'][0]['keep_percentage']=float('nan')
            with self.assertRaises(ValueError):store.save(invalid)
            self.assertEqual(DeckProfiles(store.path).selected(),restored)

    def test_model_gets_only_relevant_cards_and_provenance(self):
        result=decision_reference(reference(),{'運送幼龍','火炬'})
        self.assertEqual([r['name'] for r in result['cards']],['火炬','運送幼龍'])
        self.assertEqual(result['rank_range'],'青銅到黃金')
        self.assertIsNone(decision_reference(reference(),{'其他卡'}))


if __name__=='__main__':unittest.main()
