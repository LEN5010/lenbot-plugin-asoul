"""Calendar: live schedule from one ICS calendar, schedule card, special follows, schedule tool and pre-live scene events."""

from __future__ import annotations
from typing import Annotated
from pydantic import Field

import asyncio
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import re
import time as clock
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx

from len_bot.plugin import Image, Invocation, PluginContext, background, command, fullmatch, tool

from .card_kit import Fonts
from .ics import CalendarEvent, parse_calendar
from .schedule_card import Day, Entry, render_schedule


WEEKDAYS = "一二三四五六日"
KEEP_REMINDED = 500
ASSETS = Path(__file__).parent / "assets"
FONT = ASSETS / "font.ttf"
# Symbols and kaomoji the bundled font lacks; only fonts present on this machine are used.
FALLBACK_FONTS = ("/Library/Fonts/Arial Unicode.ttf", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                  "/System/Library/Fonts/Apple Symbols.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                  "/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf",
                  "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
HIGHLIGHTS = "highlights"


def card_fonts() -> Fonts:
    return Fonts(FONT, FONT, fallbacks=tuple(Path(path) for path in FALLBACK_FONTS if Path(path).is_file()),
                 fake_bold=True)


def highlight_key(event: CalendarEvent) -> str:
    return f"{event.source_uid}|{event.recurrence_id or ''}"


def entry_parts(event: CalendarEvent) -> tuple[str, str, list[str]]:
    """(category, title, members) from titles like 【日常】嘉然直播: 标题 and the host line of the description."""
    match = re.match(r"【([^】]+)】(.*)", event.title)
    category, rest = (match[1], match[2]) if match else ("", event.title)
    title = rest.split(": ", 1)[1] if ": " in rest else rest
    return category, title.strip() or event.title, (event.host_signature or "").replace("、", " ").split()


class CalendarFeature:
    def _init_calendar(self, ctx: PluginContext) -> None:
        url = urlsplit(ctx.config["calendar_url"])
        if url.scheme not in {"http", "https"} or not url.netloc:
            raise ValueError("calendar_url 必须是完整的 HTTP(S) 地址")
        self.calendar_zone = ZoneInfo(ctx.config["calendar_timezone"])
        if ctx.config["card_mode"] not in {"text", "image"}:
            raise ValueError("card_mode 必须明确为 text 或 image")
        self.card_fonts = card_fonts()
        self.stickers = {folder.name: sorted(folder.glob("*.webp"))
                         for folder in (ASSETS / "stickers").iterdir() if folder.is_dir()}
        if ctx.config["request_timeout_seconds"] <= 0 or ctx.config["calendar_cache_seconds"] < 0 or ctx.config["remind_minutes"] < 0:
            raise ValueError("读取超时必须大于0，缓存秒数和提醒分钟数不能小于0")
        self.calendar_client = httpx.AsyncClient(timeout=ctx.config["request_timeout_seconds"], trust_env=False,
                                                 follow_redirects=False,
                                                 headers={"User-Agent": ctx.config["calendar_user_agent"]})
        self.calendar_snapshot: tuple[float, tuple[CalendarEvent, ...]] | None = None
        self.calendar_lock = asyncio.Lock()
        self.reminded_path = ctx.data_dir / "reminded.json"

    async def _stop_calendar(self) -> None:
        await self.calendar_client.aclose()

    async def events(self) -> tuple[CalendarEvent, ...]:
        async with self.calendar_lock:
            now = clock.time()
            if (self.calendar_snapshot is not None
                    and now < self.calendar_snapshot[0] + self.ctx.config["calendar_cache_seconds"]):
                return self.calendar_snapshot[1]
            response = await self.calendar_client.get(self.ctx.config["calendar_url"])
            if response.status_code != 200:
                raise RuntimeError(f"日历返回 HTTP {response.status_code}：{response.text[:300]!r}")
            events = parse_calendar(response.content.decode("utf-8-sig"), self.calendar_zone)
            self.calendar_snapshot = (now, events)
            return events

    def is_live(self, event: CalendarEvent) -> bool:
        config = self.ctx.config
        if event.all_day and not config["include_all_day"]:
            return False
        if event.url and "live.bilibili.com" in event.url:
            return True
        text = " ".join((event.title, event.categories, event.location)).casefold()
        if any(word.casefold() in text for word in config["live_keywords"]):
            return True
        return not any(word.casefold() in text for word in config["non_live_keywords"])

    async def between(self, start: datetime, end: datetime, member: str | None, *,
                      cancelled: bool = False) -> list[CalendarEvent]:
        """Live entries overlapping the range, by start time; cancelled ones only for the schedule card."""
        selected = []
        for event in await self.events():
            if not self.is_live(event) or (event.cancelled and not cancelled):
                continue
            overlaps = (start <= event.start_at < end if event.end_at is None
                        else event.start_at < end and event.end_at > start)
            if overlaps and (member is None or member.casefold() in
                             " ".join((event.title, event.host_signature or "")).casefold()):
                selected.append(event)
        return sorted(selected, key=lambda event: event.start_at)

    async def highlights(self) -> dict[str, dict]:
        return await self.ctx.get_kv(HIGHLIGHTS, {})

    def line(self, event: CalendarEvent, zone: ZoneInfo) -> str:
        start = event.start_at.astimezone(zone)
        when = f"{start:%m-%d} 周{WEEKDAYS[start.weekday()]} " + ("全天" if event.all_day else f"{start:%H:%M}")
        return f"{when} {event.title}" + (f"（{event.host_signature}）" if event.host_signature else "")

    def day_of(self, text: str, today: date) -> date | None:
        named = {"今天": today, "明天": today + timedelta(days=1), "后天": today + timedelta(days=2)}
        if text in named:
            return named[text]
        try:
            return date.fromisoformat(text)
        except ValueError:
            pass
        match = re.fullmatch(r"(\d{1,2})[-/.月](\d{1,2})日?", text)
        if match is None:
            return None
        try:
            day = date(today.year, int(match[1]), int(match[2]))
        except ValueError:
            return None
        # A month-day already well past means next year's.
        return day.replace(year=today.year + 1) if day < today - timedelta(days=180) else day

    @fullmatch("今日直播", "直接查看今日直播日程，不调用对话模型")
    async def today(self, ctx: Invocation) -> None:
        await self.schedule(ctx, "今天")

    @command("日程", "查看直播日程：/日程、/日程 明天、/日程 本周")
    async def schedule(self, ctx: Invocation, args: str) -> None:
        zone = ZoneInfo(ctx.timezone())
        now = datetime.fromtimestamp(ctx.now(), zone)
        today = now.date()
        spans = {"": (today, 1, "今天"), "今天": (today, 1, "今天"), "明天": (today + timedelta(days=1), 1, "明天"),
                 "本周": (today - timedelta(days=today.weekday()), 7, "本周")}
        if args not in spans:
            await ctx.reply("用法：/日程、/日程 明天、/日程 本周")
            return
        first, days, label = spans[args]
        start = datetime.combine(first, time.min, zone)
        try:
            events = await self.between(start, start + timedelta(days=days), None,
                                        cancelled=self.ctx.config["card_mode"] == "image")
            marked = await self.highlights()
        except Exception:
            await ctx.reply(f"{label}日程暂时没取到，稍后再试。")
            raise
        if not any(not event.cancelled for event in events):
            await ctx.reply(f"{label}暂无直播。")
            return
        lines = [self.line(event, zone) + ("（特别关注）" if highlight_key(event) in marked else "")
                 + ("（已取消）" if event.cancelled else "") for event in events]
        if self.ctx.config["card_mode"] == "text":
            await ctx.reply(f"{label}直播安排：\n" + "\n".join(lines))
            return
        groups = []
        for offset in range(days):
            day = first + timedelta(days=offset)
            entries = []
            for event in events:
                begin = event.start_at.astimezone(zone)
                if begin.date() != day:
                    continue
                category, title, members = entry_parts(event)
                entries.append(Entry(begin, title, category, members, highlight=highlight_key(event) in marked,
                                     cancelled=event.cancelled,
                                     live_now=(not event.cancelled and event.end_at is not None
                                               and event.start_at <= now < event.end_at)))
            groups.append(Day(day, entries, today=day == today))
        live = sum(not event.cancelled for event in events)
        zone_text = "北京时间" if zone.key in {"Asia/Shanghai", "Asia/Chongqing", "PRC"} else zone.key
        if days == 1:
            subtitle = f"{first.month}月{first.day}日 周{WEEKDAYS[first.weekday()]} · 共 {live} 场 · {zone_text}"
        else:
            last = first + timedelta(days=days - 1)
            subtitle = f"{first.month}月{first.day}日 – {last.month}月{last.day}日 · 共 {live} 场 · {zone_text}"
        data = await asyncio.to_thread(render_schedule, f"{label}直播", subtitle, groups, self.card_fonts,
                                       stickers=self.stickers, source=urlsplit(self.ctx.config["calendar_url"]).netloc,
                                       compact=days > 1)
        await ctx.reply_parts([Image(data, f"{label}直播安排卡片：\n" + "\n".join(lines))])

    @command("日程高亮", "把某天的一场直播设为特别关注：/日程高亮 日期 查看序号，/日程高亮 日期 序号 标记")
    async def mark(self, ctx: Invocation, args: str) -> None:
        await self.change_mark(ctx, args, True)

    @command("取消日程高亮", "取消特别关注：/取消日程高亮 日期 序号")
    async def unmark(self, ctx: Invocation, args: str) -> None:
        await self.change_mark(ctx, args, False)

    async def change_mark(self, ctx: Invocation, args: str, marking: bool) -> None:
        name = "日程高亮" if marking else "取消日程高亮"
        zone = ZoneInfo(ctx.timezone())
        today = datetime.fromtimestamp(ctx.now(), zone).date()
        words = args.split()
        day = self.day_of(words[0], today) if words else None
        if day is None or len(words) > 2 or (len(words) == 2 and not words[1].isdigit()):
            await ctx.reply(f"用法：/{name} 日期 序号；日期写 今天、明天、10-07 或 2026-10-07，只写日期先看序号。")
            return
        start = datetime.combine(day, time.min, zone)
        try:
            events = [event for event in await self.between(start, start + timedelta(days=1), None)
                      if event.start_at.astimezone(zone).date() == day]
        except Exception:
            await ctx.reply("日程暂时没取到，稍后再试。")
            raise
        if not events:
            await ctx.reply(f"{day.month}月{day.day}日暂无直播。")
            return
        marked = await self.highlights()
        if len(words) == 1:
            rows = [f"{index}. {self.line(event, zone)}" + ("（特别关注）" if highlight_key(event) in marked else "")
                    for index, event in enumerate(events, 1)]
            await ctx.reply(f"{day.month}月{day.day}日的直播：\n" + "\n".join(rows) + f"\n用 /{name} {words[0]} 序号 选择。")
            return
        index = int(words[1])
        if not 1 <= index <= len(events):
            await ctx.reply(f"序号要在 1 到 {len(events)} 之间。")
            return
        event = events[index - 1]
        key = highlight_key(event)
        if marking:
            marked[key] = {"start": event.start_at.isoformat(), "title": event.title,
                           "hosts": event.host_signature or ""}
        elif marked.pop(key, None) is None:
            await ctx.reply("这场本来就不是特别关注。")
            return
        # Records of days long past are dropped whenever the list is written.
        cutoff = datetime.fromtimestamp(ctx.now(), zone) - timedelta(days=7)
        marked = {key: value for key, value in marked.items() if datetime.fromisoformat(value["start"]) >= cutoff}
        await self.ctx.set_kv(HIGHLIGHTS, marked)
        await ctx.reply(("已设为特别关注：" if marking else "已取消特别关注：") + self.line(event, zone))

    @command("日程高亮列表", "列出还没过去的特别关注直播")
    async def list_marks(self, ctx: Invocation, args: str) -> None:
        zone = ZoneInfo(ctx.timezone())
        now = datetime.fromtimestamp(ctx.now(), zone)
        rows = sorted(((datetime.fromisoformat(value["start"]).astimezone(zone), value)
                       for value in (await self.highlights()).values()), key=lambda row: row[0])
        rows = [(start, value) for start, value in rows if start.date() >= now.date()]
        if not rows:
            await ctx.reply("现在没有特别关注的直播。")
            return
        await ctx.reply("特别关注：\n" + "\n".join(
            f"{start:%m-%d} 周{WEEKDAYS[start.weekday()]} {start:%H:%M} {value['title']}"
            + (f"（{value['hosts']}）" if value["hosts"] else "") for start, value in rows))

    @tool("live_schedule", "按日期查询直播日历；start 为 YYYY-MM-DD（本群时区），days 为天数，member 按日历原文包含的文字筛选", summary='查询 A-SOUL 指定日期的直播日历')
    async def lookup(
        self,
        ctx: Invocation,
        start: Annotated[
            str,
            Field(description='日期 YYYY-MM-DD，按本群时区解释', examples=['2026-10-06']),
        ],
        days: Annotated[
            int,
            Field(description='从 start 开始查询的天数', ge=1, le=31),
        ] = 1,
        member: Annotated[
            str | None,
            Field(description='按日历原文包含的成员名称筛选'),
        ] = None,
    ) -> dict:
        zone = ZoneInfo(ctx.timezone())
        first = datetime.combine(date.fromisoformat(start), time.min, zone)
        events = await self.between(first, first + timedelta(days=days), member)
        marked = await self.highlights()
        return {
            "source": self.ctx.config["calendar_url"], "timezone": zone.key,
            "range": [first.isoformat(), (first + timedelta(days=days)).isoformat()],
            "events": [{"uid": event.source_uid, "start": event.start_at.astimezone(zone).isoformat(),
                        "end": None if event.end_at is None else event.end_at.astimezone(zone).isoformat(),
                        "title": event.title, "host": event.host_signature, "url": event.url,
                        "special_follow": highlight_key(event) in marked} for event in events],
            "note": "special_follow 是群友手动标记的特别关注。",
        }

    @background(every="1m")
    async def remind(self, ctx: PluginContext) -> None:
        minutes = ctx.config["remind_minutes"]
        if minutes == 0 or not ctx.scenes:
            return
        now = datetime.fromtimestamp(ctx.now(), self.calendar_zone)
        upcoming = await self.between(now, now + timedelta(minutes=minutes), None)
        reminded = json.loads(self.reminded_path.read_text(encoding="utf-8")) if self.reminded_path.exists() else []
        marked = await self.highlights()
        for event in upcoming:
            key = f"{event.source_uid}|{event.recurrence_id or ''}|{event.start_at.isoformat()}"
            if event.start_at <= now or key in reminded:
                continue
            follow = "群友把这场设为了特别关注。" if highlight_key(event) in marked else ""
            for scene in ctx.scenes:
                zone = ZoneInfo(ctx.timezone(scene))
                left = max(1, round((event.start_at - now).total_seconds() / 60))
                await ctx.emit_event(scene, f"日历显示：{self.line(event, zone)}，大约还有 {left} 分钟开始。{follow}")
            reminded = (reminded + [key])[-KEEP_REMINDED:]
            Path(self.reminded_path).write_text(json.dumps(reminded, ensure_ascii=False), encoding="utf-8")
