"""Schedule card: day groups, then one tile per live with time, category, title, member chips and a sticker.

A tile carries a thin bar in its first member's color. Special follows tint the tile and use the
highlight color for the bar and time, as the panel marks a selected item.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageOps

from .card_kit import (BRAND_SOFT, Card, ERROR, ERROR_BG, FILL, Fonts, IDLE, INK, MUTED, PRIMARY, SUBTLE, SUCCESS,
                       SUCCESS_BG, TINTS, Style, draw_chip, draw_text, flow, footer, header, line_height, measure, px,
                       wrap)

# Members' official colors; others take a panel avatar tint chosen by name.
MEMBER_COLORS = {"嘉然": "#e799b0", "贝拉": "#db7d74", "乃琳": "#576690", "向晚": "#9ac8e2", "珈乐": "#b8a6d9"}
WEEKDAYS = "一二三四五六日"
HIGHLIGHTS = {"pink": (PRIMARY, BRAND_SOFT), "red": (ERROR, ERROR_BG), "platinum": ("#8b713e", "#f6f1e4")}


def shade(color: str, factor: float) -> str:
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return f"#{round(r * factor):02x}{round(g * factor):02x}{round(b * factor):02x}"


def tint(color: str, amount: float) -> str:
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    m = lambda c: round(c + (255 - c) * amount)
    return f"#{m(r):02x}{m(g):02x}{m(b):02x}"


def member_style(name: str) -> tuple[str, str]:
    """(text, background) for a member chip, keeping text readable on its tint."""
    if name in MEMBER_COLORS:
        base = MEMBER_COLORS[name]
        return (base if name == "乃琳" else shade(base, 0.62)), tint(base, 0.84)
    background, text = TINTS[sum(map(ord, name)) % len(TINTS)]
    return text, background


def member_color(name: str) -> str:
    return MEMBER_COLORS.get(name) or member_style(name)[0]


@dataclass
class Entry:
    start: datetime
    title: str
    category: str = ""
    members: list[str] = field(default_factory=list)
    highlight: bool = False
    highlight_style: str = "pink"
    cancelled: bool = False
    live_now: bool = False


@dataclass
class Day:
    day: date
    entries: list[Entry]
    today: bool = False


def render_schedule(title: str, subtitle: str, days: list[Day], fonts: Fonts, *,
                    stickers: dict[str, list[Path]], source: str, compact: bool = False) -> bytes:
    card = Card(fonts)
    chooser = random.Random()
    used: set[Path] = set()

    def sticker(members: list[str]) -> Image.Image | None:
        # Each row draws its own sticker; within one card a member's stickers do not repeat until used up.
        pool = [path for name in members for path in stickers.get(name, [])]
        fresh = [path for path in pool if path not in used] or pool
        if not fresh:
            return None
        path = chooser.choice(fresh)
        used.add(path)
        return Image.open(path)

    header(card, "直播日历", title, subtitle)
    previous_empty = False
    for index, day in enumerate(days):
        empty = not day.entries

        def paint_day(canvas, x, y, width, day=day, empty=empty):
            date_style = Style(15, weight=700, color=SUBTLE if empty else INK)
            right = draw_text(canvas, fonts, x, y + px(11), f"{day.day.month}月{day.day.day}日", date_style, anchor="lm")
            right = draw_text(canvas, fonts, right + px(7), y + px(11), "周" + WEEKDAYS[day.day.weekday()],
                              Style(13, color=SUBTLE if empty else MUTED), anchor="lm")
            if day.today:
                draw_chip(canvas, fonts, right + px(8), y + px(1), "今天", PRIMARY, BRAND_SOFT)
            if empty:
                draw_text(canvas, fonts, x + width, y + px(11), "无直播", Style(12.5, color=SUBTLE), anchor="rm")

        # Runs of empty days stay close together; a day with lives opens a new section.
        gap = 24 if index == 0 else 8 if empty and previous_empty else 20
        card.add(px(22), paint_day, gap=gap)
        for position, entry in enumerate(day.entries):
            row(card, entry, sticker(entry.members), compact, first=position == 0)
        previous_empty = empty

    footer(card, "日程", source)
    return card.render()


def row(card: Card, entry: Entry, art: Image.Image | None, compact: bool, *, first: bool = False) -> None:
    fonts = card.fonts
    pad = px(14)
    bar_x = px(10)
    time_x = px(22)
    art_size = px(60 if compact else 76)
    time_style = Style(18 if compact else 20, weight=700)
    text_x = time_x + measure(fonts, "00:00", time_style) + px(14)
    text_w = card.inner - text_x - pad - (art_size + px(8) if art is not None else 0)

    accent, background = HIGHLIGHTS.get(entry.highlight_style, HIGHLIGHTS["pink"])
    if not entry.highlight:
        background = FILL
        accent = member_color(entry.members[0]) if entry.members else IDLE
    if entry.cancelled:
        accent = IDLE

    title_style = Style(15 if compact else 16.5, weight=600, color=SUBTLE if entry.cancelled else INK)
    title_step = line_height(title_style, 1.45)
    lines = wrap(fonts, entry.title, title_style, text_w, max_lines=3)

    status = []
    if entry.live_now:
        status.append(("直播中", SUCCESS, SUCCESS_BG))
    if entry.cancelled:
        status.append(("已取消", ERROR, ERROR_BG))
    if entry.highlight:
        status.append(("特别关注", accent, "#ffffff"))
    status_pos, status_h = flow(fonts, status, text_w)
    members = [(name, *member_style(name)) for name in entry.members]
    member_pos, member_h = flow(fonts, members, text_w)

    content_h = (status_h + px(8) if status else 0) + len(lines) * title_step + (px(8) + member_h if members else 0)
    time_style = Style(time_style.size, weight=700, color=SUBTLE if entry.cancelled else
                       PRIMARY if entry.highlight and entry.highlight_style == "pink" else
                       accent if entry.highlight else INK)
    time_h = px(22 + (20 if entry.category else 0))
    height = max(content_h, art_size, time_h) + 2 * pad

    def paint(canvas, x, y, width):
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle((x, y, x + width, y + height), radius=px(10), fill=background)
        draw.rounded_rectangle((x + bar_x, y + pad + px(2), x + bar_x + px(3), y + height - pad - px(2)),
                               radius=px(1.5), fill=accent)
        draw_text(canvas, fonts, x + time_x, y + pad + px(3), f"{entry.start:%H:%M}", time_style)
        if entry.category:
            draw_text(canvas, fonts, x + time_x, y + pad + px(28), entry.category[:4], Style(11.5, color=MUTED))

        top = y + (height - content_h) // 2
        for cx, cy, label, fg, bg in status_pos:
            draw_chip(canvas, fonts, x + text_x + cx, top + cy, label, fg, bg,
                      outline=fg if bg == "#ffffff" else None)
        ty = top + (status_h + px(8) if status else 0)
        for text in lines:
            right = draw_text(canvas, fonts, x + text_x, ty + (title_step - px(title_style.size)) // 2, text, title_style)
            if entry.cancelled:
                mid = ty + title_step // 2
                draw.line((x + text_x, mid, right, mid), fill=MUTED, width=px(1.5))
            ty += title_step
        ty += px(8)
        for cx, cy, label, fg, bg in member_pos:
            draw_chip(canvas, fonts, x + text_x + cx, ty + cy, label, fg, bg)

        if art is not None:
            picture = ImageOps.contain(art.convert("RGBA"), (art_size, art_size), Image.Resampling.LANCZOS)
            if entry.cancelled:
                picture.putalpha(picture.getchannel("A").point(lambda a: a * 45 // 100))
            canvas.alpha_composite(picture, (x + width - pad - art_size + (art_size - picture.width) // 2,
                                             y + (height - picture.height) // 2))

    card.add(height, paint, gap=12 if first else 8)
