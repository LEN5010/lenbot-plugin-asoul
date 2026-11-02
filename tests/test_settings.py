"""Owners change the reminder through the public tool and use the saved value immediately."""

import json
from pathlib import Path

import pytest

from len_bot.plugin_testing import PluginTest


@pytest.mark.asyncio
async def test_owner_changes_reminder_and_other_senders_cannot(source):
    config = {'calendar_url': source.url + '/calendar.ics', 'dynamics_api_url': source.url + '/api',
              'remind_minutes': 0}
    async with PluginTest(Path(__file__).parents[1], config=config, owners=['onebot:70001']) as bot:
        owner = bot.add_message('提前五分钟提醒我', sender='onebot:70001').platform_message_id
        other = bot.add_message('关闭提醒', sender='onebot:70002').platform_message_id
        with pytest.raises(PermissionError, match='主人'):
            await bot.tool('asoul_schedule_settings', {'source_message_id': other, 'action': 'set', 'minutes': 0})
        result = json.loads(await bot.tool('asoul_schedule_settings', {
            'source_message_id': owner, 'action': 'set', 'minutes': 5}))
        assert result == {'remind_minutes': 5, 'scope': 'all_enabled_scenes'}
        assert bot.saved_config['remind_minutes'] == 5
        assert bot.host.plugins['asoul'].context.config['remind_minutes'] == 5
        read = json.loads(await bot.tool('asoul_schedule_settings', {'source_message_id': owner, 'action': 'get'}))
        assert read == result
        with pytest.raises(ValueError, match='minutes'):
            await bot.tool('asoul_schedule_settings', {'source_message_id': owner, 'action': 'set'})
        with pytest.raises(ValueError):
            await bot.tool('asoul_schedule_settings', {'source_message_id': owner, 'action': 'set', 'minutes': -1})
        await bot.tool('asoul_schedule_settings', {'source_message_id': owner, 'action': 'set', 'minutes': 0})
        assert bot.saved_config['remind_minutes'] == 0
