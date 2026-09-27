import json
from pathlib import Path
import tempfile
import unittest

from laya_hearthstone.advisor import build_request
from laya_hearthstone.deck_profiles import DeckProfiles,new_profile
from laya_hearthstone.menu_navigation import menu_step
from tests.test_strategy import fixture,unit,option


class DeckProfileTests(unittest.TestCase):
    def test_source_and_meta_notes_survive_save_and_reach_model(self):
        with tempfile.TemporaryDirectory() as folder:
            store=DeckProfiles(Path(folder)/'decks.json')
            profile=dict(new_profile(),name='龍戰',source_url='https://hsreplay.net/zh-hant/meta/',meta_notes='2026-09-27：對快攻保留解牌')
            store.save(profile)
            state,cards=fixture([unit(1,'1')],[],[option(1,1,[102])],enemy_health=50)
            context,_,_=build_request(state,cards,store.selected())
            self.assertEqual(context['deck_strategy']['meta_notes'],profile['meta_notes'])
            self.assertEqual(DeckProfiles(store.path).selected()['source_url'],profile['source_url'])
            for url in ('javascript:alert(1)','https://hsreplay.net.evil.test/','http://hsreplay.net/'):
                with self.assertRaises(ValueError):store.save(dict(profile,source_url=url))

    def test_profiles_keep_separate_notes_and_selected_deck_after_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'decks.json'
            store=DeckProfiles(path)
            first=dict(new_profile(),name='龍戰',mulligan='保留 A',combos='A 然後 B')
            second=dict(new_profile(),name='另一套',mulligan='換掉 A')
            store.save(first);store.save(second);store.select(first['id'])
            restored=DeckProfiles(path)
            self.assertEqual(restored.selected(),first)
            changed=restored.selected();changed['combos']='changed'
            self.assertEqual(restored.selected()['combos'],'A 然後 B')
            with self.assertRaises(ValueError):store.save(dict(first,name=''))
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['selected_id'],first['id'])

    def test_strategy_reaches_model_without_six_action_cutoff(self):
        board=[unit(i,'1') for i in range(1,8)]
        state,cards=fixture(board,[],[option(i,i,[102]) for i in range(1,8)],enemy_health=50)
        profile=dict(new_profile(),name='龍戰',mulligan='留龍',game_plan='保留關鍵資源',combos='A 後 B')
        context,question,actions=build_request(state,cards,profile)
        self.assertEqual(context['deck_strategy']['combos'],'A 後 B')
        self.assertGreater(len(actions),6)
        self.assertIn('deck_strategy',question['move']['instructions'])


def label(text,x,y):
    return dict(text=text,point=[x,y],score=1)


class MenuTests(unittest.TestCase):
    profile=dict(name='龍戰',mode='standard')

    def test_queue_requires_correct_mode_and_selected_deck(self):
        base=[label('標準對戰',.4,.04),label('選擇套牌',.4,.13),label('開始',.73,.82)]
        step=menu_step(base+[label('龍戰',.22,.28),label('其他',.73,.64)],self.profile)
        self.assertEqual(step['kind'],'click')
        self.assertEqual(step['point'],[.22,.28])
        self.assertEqual(menu_step(base+[label('龍戰',.73,.64)],self.profile)['kind'],'queue')
        wrong=[label('開放對戰',.4,.04),*base[1:],label('龍戰',.73,.64)]
        self.assertEqual(menu_step(wrong,self.profile)['message'],'開啟模式選單')

    def test_similar_deck_names_and_unknown_screens_do_not_queue(self):
        labels=[label('標準對戰',.4,.04),label('選擇套牌',.4,.13),label('開始',.73,.82),label('海龍戰',.22,.28)]
        self.assertEqual(menu_step(labels,self.profile)['kind'],'deck_missing')
        self.assertEqual(menu_step([label('購買',.5,.5)],self.profile,True)['kind'],'wait')
        self.assertEqual(menu_step([label('勝利',.5,.5)],self.profile,False)['kind'],'wait')


if __name__=='__main__':
    unittest.main()
