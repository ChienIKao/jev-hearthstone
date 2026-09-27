"""Local deck selection and strategy notes shared by the panel and adviser."""
import copy
import json
from pathlib import Path
import uuid

from snapshot_io import publish_text

FIELDS = ('name', 'mode', 'deck_code', 'mulligan', 'game_plan', 'combos', 'source_url', 'meta_notes')


def new_profile():
    return dict(id=uuid.uuid4().hex, name='', mode='standard', deck_code='',
                mulligan='', game_plan='', combos='', source_url='', meta_notes='', reference_data=None)


def validate_profile(value):
    result = {key: str(value.get(key, '')).strip() for key in FIELDS}
    result['id'] = str(value.get('id', '')).strip()
    if not result['id'] or not result['name']:
        raise ValueError('請填寫遊戲內的牌組名稱')
    if result['mode'] not in ('standard', 'wild'):
        raise ValueError('請選擇標準或開放模式')
    if result['source_url']:
        from urllib.parse import urlsplit
        url=urlsplit(result['source_url'])
        if url.scheme!='https' or url.hostname not in ('hsreplay.net','www.hsreplay.net') or url.username or url.password:
            raise ValueError('來源請填寫 https://hsreplay.net/ 的牌組或環境頁面')
    reference=value.get('reference_data')
    if reference is not None:
        from hsreplay_import import validate_reference
        reference=validate_reference(reference)
        if reference['mode']!=result['mode']:
            raise ValueError('參考資料與牌組模式不同，請先移除參考資料再變更模式')
    result['reference_data']=reference
    return result


class DeckProfiles:
    def __init__(self, path):
        self.path = Path(path)
        self.profiles = []
        self.selected_id = None
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding='utf-8'))
            self.profiles = [validate_profile(p) for p in data['profiles']]
            self.selected_id = data.get('selected_id')
            if len({p['id'] for p in self.profiles}) != len(self.profiles):
                raise ValueError('牌組設定含有重複識別碼')

    def selected(self):
        return next((copy.deepcopy(p) for p in self.profiles if p['id'] == self.selected_id), None)

    def save(self, profile):
        profile = validate_profile(profile)
        updated = [p for p in self.profiles if p['id'] != profile['id']] + [profile]
        self._write(updated, profile['id'])

    def select(self, profile_id):
        if not any(p['id'] == profile_id for p in self.profiles):
            raise ValueError('找不到所選牌組')
        self._write(self.profiles, profile_id)

    def _write(self, profiles, selected_id):
        payload = json.dumps(dict(profiles=profiles, selected_id=selected_id), ensure_ascii=False, indent=2)
        if not publish_text(self.path, payload):
            raise ValueError('無法儲存牌組設定')
        self.profiles, self.selected_id = copy.deepcopy(profiles), selected_id


def strategy_context(profile):
    if not profile:
        return None
    return {key: profile.get(key, '') for key in ('name', 'mode', 'mulligan', 'game_plan', 'combos', 'source_url', 'meta_notes')}
