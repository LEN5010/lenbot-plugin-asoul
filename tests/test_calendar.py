"""Schedule command, tool and pre-live reminders against a local ICS calendar."""

import asyncio
from datetime import datetime, timedelta
from io import BytesIO
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from PIL import Image as PILImage

from len_bot.plugin import Image
from len_bot.plugin_testing import PluginTest

PACKAGE = Path(__file__).parents[1]
ZONE = ZoneInfo("Asia/Shanghai")


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%S")


def calendar(*events: tuple) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0"]
    for uid, start, title, host, *status in events:
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTART;TZID=Asia/Shanghai:{stamp(start)}",
                  f"DTEND;TZID=Asia/Shanghai:{stamp(start + timedelta(hours=2))}", f"SUMMARY:{title}",
                  f"DESCRIPTION:直播|{host}", *(f"STATUS:{value}" for value in status), "END:VEVENT"]
    return "\r\n".join([*lines, "END:VCALENDAR"]) + "\r\n"


def config(source, **values) -> dict:
    return {"calendar_url": source.url + "/calendar.ics", "dynamics_api_url": source.url + "/api",
            "live_keywords": ["直播"], **values}


async def first_remind(bot) -> None:
    while bot.state()["plugins"][0]["backgrounds"][0]["last_finished"] is None:
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_schedule_command_and_tool_read_the_calendar(source):
    today = datetime.now(ZONE).replace(hour=0, minute=0, second=1, microsecond=0)
    tomorrow = today + timedelta(days=1, hours=20)
    source.text("/calendar.ics", calendar(("a", today, "嘉然直播", "嘉然"), ("b", tomorrow, "乃琳直播", "乃琳")))
    async with PluginTest(PACKAGE, config=config(source, remind_minutes=0, card_mode="text")) as bot:
        assert await bot.message("/日程")
        assert bot.deliveries[-1].text.startswith("今天直播安排：")
        assert "嘉然直播（嘉然）" in bot.deliveries[-1].text and "乃琳" not in bot.deliveries[-1].text
        assert await bot.message("/日程 下周")
        assert bot.deliveries[-1].text == "用法：/日程、/日程 明天、/日程 本周"
        found = json.loads(await bot.tool("live_schedule", {"start": tomorrow.date().isoformat(), "member": "乃琳"}))
        assert [event["uid"] for event in found["events"]] == ["b"]


@pytest.mark.asyncio
async def test_schedule_command_answers_in_a_telegram_group(source):
    today = datetime.now(ZONE).replace(hour=0, minute=0, second=1, microsecond=0)
    source.text("/calendar.ics", calendar(("a", today, "嘉然直播", "嘉然")))
    scene = "telegram:group:-1001234"
    async with PluginTest(PACKAGE, config=config(source, remind_minutes=0, card_mode="text"),
                          scenes=(scene,), bots={"telegram": "telegram:7001"}) as bot:
        assert await bot.message("/日程", scene=scene, sender="telegram:501")
        assert bot.deliveries[-1].scene == scene and "嘉然直播（嘉然）" in bot.deliveries[-1].text


@pytest.mark.asyncio
async def test_reminder_is_sent_once_per_event(source):
    soon = datetime.now(ZONE).replace(microsecond=0) + timedelta(minutes=5)
    source.text("/calendar.ics", calendar(("soon", soon, "贝拉直播", "贝拉")))
    async with PluginTest(PACKAGE, config=config(source)) as bot:
        await first_remind(bot)
        plugin = bot.host.plugins["asoul"]
        await plugin.instance.remind(plugin.context)
        events = bot.events()
        assert len(events) == 1 and "贝拉直播" in events[0]["content"]
        assert json.loads((plugin.context.data_dir / "reminded.json").read_text()) == [f"soon||{soon.isoformat()}"]


@pytest.mark.asyncio
async def test_unreachable_calendar_is_not_reported_as_empty(source):
    async with PluginTest(PACKAGE, config=config(source, remind_minutes=0)) as bot:
        with pytest.raises(RuntimeError, match="HTTP 404"):
            await bot.message("/日程")
        assert bot.deliveries[-1].text == "今天日程暂时没取到，稍后再试。"


@pytest.mark.asyncio
async def test_schedule_card_shows_cancelled_and_special_follow(source):
    today = datetime.now(ZONE).replace(hour=0, minute=0, second=0, microsecond=0)
    source.text("/calendar.ics", calendar(
        ("a", today + timedelta(hours=1), "【日常】嘉然直播: 早安", "嘉然"),
        ("b", today + timedelta(hours=3), "【日常】贝拉直播: 跳舞", "贝拉"),
        ("c", today + timedelta(hours=5), "【2D】思诺直播: 唱歌", "思诺", "CANCELLED")))
    async with PluginTest(PACKAGE, config=config(source, remind_minutes=0)) as bot:
        assert await bot.message("/日程高亮 今天")
        listing = bot.deliveries[-1].text
        assert "1. " in listing and "2. " in listing and "思诺" not in listing
        assert await bot.message("/日程高亮 今天 2")
        assert bot.deliveries[-1].text.startswith("已设为特别关注：") and "贝拉" in bot.deliveries[-1].text
        assert await bot.message("/日程高亮列表")
        assert "贝拉直播" in bot.deliveries[-1].text
        assert await bot.message("/日程")
        card, = bot.deliveries[-1].parts
        assert isinstance(card, Image) and PILImage.open(BytesIO(card.data)).size[0] == 1080
        assert "跳舞（贝拉）（特别关注）" in card.description and "唱歌（思诺）（已取消）" in card.description
        found = json.loads(await bot.tool("live_schedule", {"start": today.date().isoformat()}))
        assert [event["special_follow"] for event in found["events"]] == [False, True]
        assert await bot.message("/取消日程高亮 今天 2")
        assert await bot.message("/取消日程高亮 今天 2")
        assert bot.deliveries[-1].text == "这场本来就不是特别关注。"
        assert await bot.message("/日程高亮 下个月")
        assert bot.deliveries[-1].text.startswith("用法：/日程高亮 日期 序号")
