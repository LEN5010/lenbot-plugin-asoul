"""Calendar: live schedule from one ICS calendar, schedule card, special follows, schedule tool and pre-live scene events."""

from __future__ import annotations
from typing import Annotated, Literal
from pydantic import Field

import asyncio
from datetime import date, datetime, time, timedelta
import json
import hashlib
from pathlib import Path
import re
import time as clock
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx

from len_bot.plugin import Image, Invocation, PluginContext, background, command, regex, tool

from .card_kit import Fonts
from .ics import CalendarEvent, parse_calendar
from .schedule_card import Day, Entry, render_schedule
from .schedule_logic import ScheduleService, ScheduleItem
from .requests import HighlightRequest


WEEKDAYS = "一二三四五六日"
KEEP_REMINDED = 500
ASSETS = Path(__file__).parent / "assets"
FONT = ASSETS / "NotoSansSC.ttf"
# Symbols and kaomoji the bundled font lacks; only fonts present on this machine are used.
FALLBACK_FONTS = ("/Library/Fonts/Arial Unicode.ttf", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                  "/System/Library/Fonts/Apple Symbols.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                  "/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf",
                  "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
HIGHLIGHTS = "highlights"


def card_fonts() -> Fonts:
    return Fonts(FONT, fallbacks=tuple(Path(path) for path in FALLBACK_FONTS if Path(path).is_file()))


def item_for(event: CalendarEvent | ScheduleItem) -> ScheduleItem:
    return event if isinstance(event, ScheduleItem) else ScheduleService().build_schedule_items([event])[0]


def highlight_key(event: CalendarEvent | ScheduleItem) -> str:
    item = item_for(event)
    identity = {'start': item.start.astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%dT%H:%M'),
                'content': ' '.join(item.content.split()), 'label': ' '.join(item.label.split())}
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()[:24]


def record_for(event: CalendarEvent | ScheduleItem, marked: dict) -> dict | None:
    item = item_for(event)
    return marked.get(highlight_key(item)) or next((marked[key] for key in item.source_keys if key in marked), None)


class CalendarFeature:
    def _init_calendar(self, ctx: PluginContext) -> None:
        url = urlsplit(ctx.config["calendar_url"])
        if url.scheme not in {"http", "https"} or not url.netloc:
            raise ValueError("calendar_url 必须是完整的 HTTP(S) 地址")
        self.schedule_service = ScheduleService()
        self.highlights_lock = asyncio.Lock()
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

    @tool('asoul_schedule_settings', '主人查询或调整 A-SOUL 开播前提醒，所有启用插件的群共用。'
          'action=get 查看当前设置；action=set 按 minutes 指定提前多少分钟提醒，0 表示关闭。'
          '保存后立即生效。单场特别关注用 asoul_schedule_highlight。',
          summary='由主人调整 A-SOUL 开播前提醒', needs_source=True)
    async def schedule_settings(self, ctx: Invocation,
                                action: Annotated[Literal['get', 'set'], Field(description='get 查询；set 保存提醒时间')],
                                minutes: Annotated[int | None, Field(ge=0, description='提前提醒的分钟数；0 关闭')] = None) -> dict:
        ctx.require_owner()
        if action == 'set':
            if minutes is None:
                raise ValueError('调整提醒时需要指定 minutes；0 表示关闭')
            await ctx.update_config({'remind_minutes': minutes})
        elif minutes is not None:
            raise ValueError('查询设置只需要 action=get')
        return {'remind_minutes': self.ctx.config['remind_minutes'], 'scope': 'all_enabled_scenes'}

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

    @regex(r"/?(今日直播|明日直播|本周直播)(?:\s+(-a))?", "查询今天、明天或本周直播，-a 筛除心宜和思诺")
    async def live_command(self, ctx: Invocation, match: re.Match[str]) -> None:
        label = {'今日直播': '今天', '明日直播': '明天', '本周直播': '本周'}[match[1]]
        await self.send_schedule(ctx, label + (' -a' if match[2] else ''))

    async def schedule_items(self, start: datetime, end: datetime, *, cancelled: bool = False,
                             exclude: bool = False) -> list[ScheduleItem]:
        events = [event for event in await self.between(start, end, None, cancelled=cancelled)
                  if start <= event.start_at < end]
        items = self.schedule_service.build_schedule_items(events)
        return self.schedule_service.exclude_hosts(items, {'心宜', '思诺'}) if exclude else items

    @command("日程", "查看直播日程：/日程、/日程 明天、/日程 本周；-a 筛除心宜和思诺")
    async def schedule(self, ctx: Invocation, args: str) -> None:
        await self.send_schedule(ctx,args)

    async def send_schedule(self, ctx: Invocation, args: str):
        zone = self.calendar_zone
        now = datetime.fromtimestamp(ctx.now(), zone)
        today = now.date()
        words = args.split()
        exclude = '-a' in words
        words = [word for word in words if word != '-a']
        label = words[0] if words else '今天'
        if len(words) > 1 or label not in {'今天', '明天', '本周'}:
            return await ctx.reply('用法：/日程、/日程 明天、/日程 本周，可加 -a')
        if label == '明天' and today.weekday() == 6:
            return await ctx.reply('还没有下周的直播排表哦')
        first = today + timedelta(days=1) if label == '明天' else today
        days = 7 - today.weekday() if label == '本周' else 1
        start = datetime.combine(first, time.min, zone)
        try:
            items = await self.schedule_items(start, start + timedelta(days=days),
                                              cancelled=self.ctx.config['card_mode'] == 'image', exclude=exclude)
            marked = await self.highlights()
        except Exception:
            await ctx.reply(f'{label}日程暂时没取到，稍后再试。')
            raise
        lines = [self.line(item, zone) + ('（特别关注）' if record_for(item, marked) else '')
                 + ('（已取消）' if item.cancelled else '') for item in items]
        if self.ctx.config['card_mode'] == 'text':
            return await ctx.reply(f'{label}直播安排：\n' + '\n'.join(lines) if items else f'{label}暂无直播。')
        groups = []
        for offset in range(days):
            day = first + timedelta(days=offset)
            entries = []
            for item in items:
                begin = item.start.astimezone(zone)
                if begin.date() != day:
                    continue
                record = record_for(item, marked)
                entries.append(Entry(begin, item.content, item.label, item.hosts,
                    highlight=record is not None, highlight_style=(record or {}).get('style', 'pink'),
                    cancelled=item.cancelled,
                    live_now=(not item.cancelled and item.end_at is not None and item.start <= now < item.end_at)))
            groups.append(Day(day, entries, today=day == today))
        live = sum(not item.cancelled for item in items)
        zone_text = '北京时间' if zone.key in {'Asia/Shanghai', 'Asia/Chongqing', 'PRC'} else zone.key
        subtitle = f'{first.month}月{first.day}日 周{WEEKDAYS[first.weekday()]} · {live} 场安排 · {zone_text}'
        if days > 1:
            last = first + timedelta(days=days - 1)
            subtitle = f'{first.month}月{first.day}日 – {last.month}月{last.day}日 · {live} 场安排'
        try:
            data = await asyncio.to_thread(render_schedule, f'{label}直播', subtitle, groups, self.card_fonts,
                stickers=self.stickers, source=urlsplit(self.ctx.config['calendar_url']).netloc, compact=days > 1)
        except Exception as error:
            self.ctx.report_error('日程卡片渲染', error)
            return await ctx.reply(f'{label}直播安排：\n' + '\n'.join(lines) if items else f'{label}暂无直播。')
        return await ctx.reply_parts([Image(data, f'{label}直播安排卡片：\n' + '\n'.join(lines))])

    @command('日程高亮', '主人设置全局特别关注：/日程高亮 日期 序号 [粉色|红色|白金色]')
    async def mark(self, ctx: Invocation, args: str) -> None:
        ctx.require_owner()
        await self.change_mark(ctx, args, True)

    @command('取消日程高亮', '主人取消全局特别关注：/取消日程高亮 日期 序号')
    async def unmark(self, ctx: Invocation, args: str) -> None:
        ctx.require_owner()
        await self.change_mark(ctx, args, False)

    async def change_mark(self, ctx: Invocation, args: str, marking: bool) -> None:
        name = '日程高亮' if marking else '取消日程高亮'
        zone = self.calendar_zone
        today = datetime.fromtimestamp(ctx.now(), zone).date()
        words = args.split()
        day = self.day_of(words[0], today) if words else None
        if day is None or len(words) > (3 if marking else 2) or (len(words) >= 2 and not words[1].isdigit()):
            await ctx.reply(f'用法：/{name} 日期 序号；日期写 今天、明天、10-07 或 2026-10-07，只写日期先看序号。')
            return
        styles = {'粉': 'pink', '粉色': 'pink', 'pink': 'pink', '红': 'red', '红色': 'red', 'red': 'red',
                  '白金': 'platinum', '白金色': 'platinum', 'platinum': 'platinum'}
        style = styles.get(words[2].lower(), '') if len(words) == 3 else 'platinum'
        if not style:
            await ctx.reply('高亮颜色支持：粉色、红色、白金色。')
            return
        start = datetime.combine(day, time.min, zone)
        items = await self.schedule_items(start, start + timedelta(days=1))
        if not items:
            await ctx.reply(f'{day.month}月{day.day}日暂无直播。')
            return
        marked = await self.highlights()
        if len(words) == 1:
            rows = [f'{index}. {self.line(item, zone)}' + ('（特别关注）' if record_for(item, marked) else '')
                    for index, item in enumerate(items, 1)]
            await ctx.reply(f'{day.month}月{day.day}日的直播：\n' + '\n'.join(rows) + f'\n用 /{name} {words[0]} 序号 选择。')
            return
        index = int(words[1])
        if not 1 <= index <= len(items):
            await ctx.reply(f'序号要在 1 到 {len(items)} 之间。')
            return
        item = items[index - 1]
        changed = await self.update_highlight(item,style if marking else None)
        if not changed:
            await ctx.reply('这场本来就不是特别关注。')
            return
        await ctx.reply(('已设为特别关注：' if marking else '已取消特别关注：') + self.line(item, zone))

    async def update_highlight(self,item: ScheduleItem,style: str | None) -> bool:
        async with self.highlights_lock:
            marked = await self.highlights()
            keys = [highlight_key(item),*item.source_keys]
            existed = any(key in marked for key in keys)
            for key in keys:
                marked.pop(key,None)
            if style is not None:
                marked[highlight_key(item)] = {'start':item.start.isoformat(),'title':item.content,
                                               'hosts':item.hosts_text,'style':style}
            elif not existed:
                return False
            await self.ctx.set_kv(HIGHLIGHTS,marked)
        return True

    async def saved_marks(self):
        return sorted((await self.highlights()).items(), key=lambda pair: (pair[1]['start'], pair[1]['title']))

    @command('日程高亮列表', '主人查看全局特别关注和保存的历史记录')
    async def list_marks(self, ctx: Invocation, args: str) -> None:
        ctx.require_owner()
        rows = await self.saved_marks()
        if not rows:
            await ctx.reply('现在没有特别关注的直播。')
            return
        labels = {'pink': '粉色', 'red': '红色', 'platinum': '白金色'}
        await ctx.reply('特别关注：\n' + '\n'.join(
            f"{index}. {datetime.fromisoformat(value['start']).astimezone(self.calendar_zone):%Y-%m-%d %H:%M} "
            f"{value['title']}（{value['hosts']}） · {labels.get(value.get('style', 'pink'), '粉色')}"
            for index, (_, value) in enumerate(rows, 1)))

    @command('取消日程高亮记录', '主人按日程高亮列表序号删除保存记录')
    async def remove_mark_record(self, ctx: Invocation, args: str) -> None:
        ctx.require_owner()
        async with self.highlights_lock:
            rows = await self.saved_marks()
            if not args.isdigit() or not 1 <= int(args) <= len(rows):
                await ctx.reply(f'用法：/取消日程高亮记录 序号（当前共 {len(rows)} 条）')
                return
            key, value = rows[int(args)-1]
            marked = await self.highlights()
            del marked[key]
            await self.ctx.set_kv(HIGHLIGHTS, marked)
        await ctx.reply('已取消特别关注：' + value['title'])

    @tool('asoul_schedule_highlight', '主人管理日程特别关注，所有群共用，日程卡片和开播提醒都会标出。request.action：'
          'list 列出保存记录；mark 把某场设为特别关注并选颜色；unmark 取消某场；remove 按 list 的 index 删除记录。'
          'mark/unmark 的 date 和 index 先用 live_schedule 查。只有主人发起的请求能执行。',
          summary='管理 A-SOUL 日程的全局特别关注', needs_source=True)
    async def highlight_tool(self,ctx: Invocation,
                             request: Annotated[HighlightRequest,Field(description='特别关注的读取、标记或删除操作')]) -> dict:
        ctx.require_owner()
        if request.action == 'list':
            return {'records':[{'index':index,**value} for index,(_,value) in enumerate(await self.saved_marks(),1)]}
        if request.action == 'remove':
            async with self.highlights_lock:
                rows = await self.saved_marks()
                if request.index > len(rows):
                    raise ValueError(f'保存记录序号要在 1 到 {len(rows)} 之间')
                key,value = rows[request.index-1]
                marked = await self.highlights()
                del marked[key]
                await self.ctx.set_kv(HIGHLIGHTS,marked)
            return {'status':'removed','record':value}
        today = datetime.fromtimestamp(ctx.now(),self.calendar_zone).date()
        day = self.day_of(request.date,today)
        if day is None:
            raise ValueError('日期写成 YYYY-MM-DD、今天或明天')
        start = datetime.combine(day,time.min,self.calendar_zone)
        items = await self.schedule_items(start,start+timedelta(days=1))
        if request.index > len(items):
            raise ValueError(f'当天日程序号要在 1 到 {len(items)} 之间')
        item = items[request.index-1]
        style = request.style if request.action == 'mark' else None
        changed = await self.update_highlight(item,style)
        return {'status':'updated' if changed else 'already_unmarked','date':day.isoformat(),
                'title':item.content,'hosts':item.hosts,'style':style}

    @tool("live_schedule", "查询 A-SOUL 直播日历，只返回数据，不发消息。items 是按节目合并的日程，"
          "每条的 date 和 index 供 asoul_schedule_highlight 使用，special_follow 表示特别关注；events 是日历原始条目。"
          "要发日程卡片用 asoul_send_card 的 schedule。", summary='查询 A-SOUL 指定日期的直播日历')
    async def lookup(
        self,
        ctx: Invocation,
        start: Annotated[
            str,
            Field(description='起始日期 YYYY-MM-DD，按日历时区', examples=['2026-10-06']),
        ],
        days: Annotated[
            int,
            Field(description='从 start 开始查询的天数', ge=1, le=31),
        ] = 1,
        member: Annotated[
            str | None,
            Field(description='成员名，按日历原文包含的文字筛选；省略不筛选'),
        ] = None,
    ) -> dict:
        zone = ZoneInfo(ctx.timezone())
        # Days follow the calendar zone, so date and index match asoul_schedule_highlight.
        first = datetime.combine(date.fromisoformat(start), time.min, self.calendar_zone)
        events = await self.between(first, first + timedelta(days=days), member)
        marked = await self.highlights()
        grouped = self.schedule_service.build_schedule_items(events)
        numbers = {}
        numbered = []
        for item in grouped:
            day = item.start.astimezone(self.calendar_zone).date().isoformat()
            numbers[day] = numbers.get(day,0)+1
            record = record_for(item,marked)
            numbered.append({'date':day,'index':numbers[day],'start':item.start.astimezone(zone).isoformat(),
                             'title':item.content,'hosts':item.hosts,'category':item.label,
                             'special_follow':record is not None,'highlight_style':(record or {}).get('style')})
        return {
            'items':numbered,
            "source": self.ctx.config["calendar_url"], "timezone": zone.key,
            "range": [first.isoformat(), (first + timedelta(days=days)).isoformat()],
            "events": [{"uid": event.source_uid, "start": event.start_at.astimezone(zone).isoformat(),
                        "end": None if event.end_at is None else event.end_at.astimezone(zone).isoformat(),
                        "title": event.title, "host": event.host_signature, "url": event.url,
                        "special_follow": record_for(event, marked) is not None} for event in events],
            "note": "items 按日程卡片分组，index 是对应日期的日程序号；special_follow 表示全局特别关注。",
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
            follow = "群友把这场设为了特别关注。" if record_for(event, marked) is not None else ""
            for scene in ctx.scenes:
                zone = ZoneInfo(ctx.timezone(scene))
                left = max(1, round((event.start_at - now).total_seconds() / 60))
                await ctx.emit_event(scene, f"日历显示：{self.line(event, zone)}，大约还有 {left} 分钟开始。{follow}")
            reminded = (reminded + [key])[-KEEP_REMINDED:]
            Path(self.reminded_path).write_text(json.dumps(reminded, ensure_ascii=False), encoding="utf-8")
