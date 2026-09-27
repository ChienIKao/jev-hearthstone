import unittest
from perception import describe_observation, observed_stats


class PerceptionTests(unittest.TestCase):
    def test_pending_choice_is_visible_until_submission_and_reappears_after_rewind(self):
        packet=dict(id=5,type='GENERAL',revision=10,complete=True,count_min=1,count_max=1,
                    cards=[dict(id=20,card_id='choice',tags={})])
        state=dict(local_controller='1',game_state='RUNNING',players=[dict(controller='1')],choices={'1':packet})
        cards={'choice':dict(name='候選卡',text='抽一張牌')}
        text=describe_observation(state,cards)
        self.assertIn('待選候選',text)
        self.assertIn('候選卡',text)
        self.assertIn('抽一張牌',text)
        state['sent_choice']=dict(id=5,type='GENERAL',revision=11)
        self.assertNotIn('待選候選',describe_observation(state,cards))
        packet['revision']=12
        self.assertIn('待選候選',describe_observation(state,cards))
        state['game_state']='COMPLETE'
        self.assertNotIn('待選候選',describe_observation(state,cards))

    def test_observed_stats_use_live_tags_and_distinguish_absent_values(self):
        text=observed_stats(dict(tags=dict(ATK='7',HEALTH='9',DAMAGE='3',SILENCED='1',TAUNT='0')))
        self.assertEqual(text,'攻擊 7 · 生命上限 9 · 已受傷害 3 · 沉默')
        self.assertEqual(observed_stats(dict(tags={})), '')

    def test_finished_game_is_identified_as_last_record(self):
        state=dict(local_controller='1',game_state='COMPLETE',players=[dict(controller='1')])
        self.assertIn('已結束對局的最後紀錄',describe_observation(state,{}))

    def test_unknown_card_and_attached_effect_are_distinguished(self):
        state=dict(local_controller='1',turn='4',game_state='RUNNING',players=[
            dict(controller='1',hand=[dict(id=8,card_id='missing',tags={})])],
            enchantments=[dict(id=9,card_id='buff',tags={'ATTACHED':'8','ZONE':'GRAVEYARD'})])
        text=describe_observation(state,{'buff':dict(name='加成',text='攻擊力+1')})
        self.assertIn('費用 未知',text)
        self.assertIn('效果未知',text)
        self.assertIn('加成 [GRAVEYARD]',text)
        self.assertIn('生效狀態待判讀',text)
        self.assertIn('攻擊力+1',text)

    def test_no_local_player_reports_missing_observation(self):
        self.assertIn('尚未辨識',describe_observation({},{}))
