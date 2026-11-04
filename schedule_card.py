"""Schedule card in the shared card design: a title header, then one block per live.

The row keeps the original schedule's layout: a time tile, a category pill and hosts over the title,
and stickers in a fixed slot at the right, one per host and smaller when several share the slot.
Special follows use the original highlight palettes; cancelled lives go gray.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
import random

from PIL import Image, ImageOps

from .card_kit import (CHIP_HEIGHT, Card, Fonts, INK, INK_2, MUTED, PICTURE_FILL, PINK_LINE, PINK_PALE, PINK_TEXT,
                       QUOTE_LINE, RADIUS, SURFACE, Style, divider, draw_chip, draw_text, fill, fit, line_height, px, ring,
                       signature, title_header, wrap)

# Members' official colors, shown as the dot beside each name.
MEMBER_COLORS = {"嘉然": "#e799b0", "贝拉": "#db7d74", "乃琳": "#576690", "向晚": "#9ac8e2", "珈乐": "#b8a6d9",
                 "思诺": "#7252c0", "心宜": "#c93773"}
OTHER_MEMBER = "#c8c6cc"
WEEKDAYS = "一二三四五六日"
HIGHLIGHTS = {
    "pink": {"glow": "#f5d5df", "fill": "#fff5f8", "outline": "#dd668d", "tile": "#f5cede", "badge": "#dd668d"},
    "red": {"glow": "#efd1cb", "fill": "#fff5f2", "outline": "#b84d43", "tile": "#f0d0ca", "badge": "#b84d43"},
    "platinum": {"glow": "#e5dcc9", "fill": "#fffdf6", "outline": "#9f8758", "tile": "#eee4cf", "badge": "#9f8758"},
}
TILE_WIDTH = 78
STICKER_SIZES = {1: 60, 2: 44}    # By stickers in the slot; three or more use STICKER_MIN.
STICKER_MIN = 33
STICKER_GAP = 4


def member_color(name: str) -> str:
    return MEMBER_COLORS.get(name, OTHER_MEMBER)


def sticker_size(count: int) -> int:
    return STICKER_SIZES.get(count, STICKER_MIN)


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

    def sticker(name: str) -> Image.Image | None:
        # Within one card a member's stickers do not repeat until they are used up.
        pool = stickers.get(name, [])
        fresh = [path for path in pool if path not in used] or pool
        if not fresh:
            return None
        path = chooser.choice(fresh)
        used.add(path)
        return Image.open(path)

    title_header(card, "A-SOUL LIVE", title, subtitle)
    previous_empty = False
    for index, day in enumerate(days):
        empty = not day.entries
        if len(days) > 1:
            # Runs of empty days stay close together; a day with lives opens a new section.
            if index and not (empty and previous_empty):
                divider(card, 18, dashed=True)
            day_heading(card, day, 22 if index == 0 else 8 if empty and previous_empty else 16)
        elif empty:
            nothing(card, f"还没有查到{title}安排")
        for position, entry in enumerate(day.entries):
            art = [picture for picture in (sticker(name) for name in entry.members) if picture is not None]
            row(card, entry, art, gap=(22 if len(days) == 1 else 12) if position == 0 else 10)
        previous_empty = empty

    signature(card)
    return card.render()


def nothing(card: Card, text: str) -> None:
    """The whole body of a day with no lives."""
    def paint(canvas, x, y, width):
        box = (x, y, x + width, y + px(84))
        fill(canvas, box, px(RADIUS), PINK_PALE)
        ring(canvas, box, px(RADIUS), PINK_LINE, max(1, px(0.5)))
        draw_text(canvas, card.fonts, x + width // 2, y + px(42), text, Style(16.5, color=MUTED), anchor="mm")

    card.add(px(84), paint, gap=22)


def day_heading(card: Card, day: Day, gap: float) -> None:
    fonts = card.fonts
    count = sum(not entry.cancelled for entry in day.entries)
    empty = not day.entries

    def paint(canvas, x, y, width):
        middle = y + px(13)
        right = draw_text(canvas, fonts, x, middle, f"{day.day.month}月{day.day.day}日",
                          Style(18, weight=800, color=MUTED if empty else INK), anchor="lm")
        right = draw_text(canvas, fonts, right + px(8), middle, "周" + WEEKDAYS[day.day.weekday()],
                          Style(14.5, color=MUTED), anchor="lm")
        if day.today:
            draw_chip(canvas, fonts, right + px(9), y, "今天")
        draw_text(canvas, fonts, x + width, middle, "无直播" if empty else f"{count} 条",
                  Style(14, weight=600, color=MUTED if empty else PINK_TEXT), anchor="rm")

    card.add(px(CHIP_HEIGHT), paint, gap=gap)


def row(card: Card, entry: Entry, art: list[Image.Image], *, gap: float = 10) -> None:
    fonts = card.fonts
    pad = px(11)
    tile_w = px(TILE_WIDTH)
    text_x = pad + tile_w + px(14)
    size = px(sticker_size(len(art)))
    slot_w = (len(art) * size + (len(art) - 1) * px(STICKER_GAP) + px(10)) if art else 0
    text_w = card.inner - text_x - px(12) - slot_w

    colors = HIGHLIGHTS.get(entry.highlight_style, HIGHLIGHTS["pink"]) if entry.highlight else None
    title_style = Style(17, weight=700, color=MUTED if entry.cancelled else INK)
    title_step = line_height(title_style, 1.42)
    lines = wrap(fonts, entry.title, title_style, text_w, max_lines=2)

    pills = []
    if entry.category:
        pills.append((entry.category[:4], INK if not entry.cancelled else MUTED, SURFACE, QUOTE_LINE, None))
    if entry.live_now:
        pills.append(("直播中", SURFACE, PINK_TEXT, None, SURFACE))
    if entry.cancelled:
        pills.append(("已取消", MUTED, PICTURE_FILL, None, None))
    if colors:
        pills.append(("★ 特别关注", SURFACE, colors["badge"], None, None))

    pill_style = Style(12, weight=700)
    pill_h = 23
    content_h = px(pill_h) + px(7) + len(lines) * title_step
    height = max(content_h + 2 * px(13), px(84), size + px(22))

    def paint(canvas, x, y, width):
        box = (x, y, x + width, y + height)
        if colors:
            halo = px(3.5)
            fill(canvas, (x - halo, y - halo, x + width + halo, y + height + halo), px(RADIUS) + halo, colors["glow"])
        fill(canvas, box, px(RADIUS), colors["fill"] if colors else PICTURE_FILL if entry.cancelled else PINK_PALE)
        ring(canvas, box, px(RADIUS), colors["outline"] if colors else QUOTE_LINE if entry.cancelled else PINK_LINE,
             px(1.5) if colors else max(1, px(0.5)))

        tile = (x + pad, y + px(11), x + pad + tile_w, y + height - px(11))
        fill(canvas, tile, px(RADIUS), colors["tile"] if colors else SURFACE)
        draw_text(canvas, fonts, (tile[0] + tile[2]) // 2, (tile[1] + tile[3]) // 2, f"{entry.start:%H:%M}",
                  Style(20, weight=800, color=MUTED if entry.cancelled else INK), anchor="mm")

        top = y + (height - content_h) // 2
        cursor = x + text_x
        for label, fg, bg, edge, dot in pills:
            cursor = draw_chip(canvas, fonts, cursor, top, label, fg, bg, style=pill_style, pad_x=9, height=pill_h,
                               edge=edge, dot=dot) + px(6)
        cursor += px(2)
        limit = x + width - px(12) - slot_w
        middle = top + px(pill_h) // 2
        for name in entry.members:
            room = limit - cursor - px(12)
            if room < px(30):
                break
            r = px(3.5)
            fill(canvas, (cursor, middle - r, cursor + 2 * r, middle + r), r, member_color(name))
            cursor = draw_text(canvas, fonts, cursor + 2 * r + px(5), middle, fit(fonts, name, Style(13.5, weight=500), room),
                               Style(13.5, weight=500, color=MUTED if entry.cancelled else INK_2), anchor="lm") + px(9)

        ty = top + px(pill_h) + px(7)
        for text in lines:
            right = draw_text(canvas, fonts, x + text_x, ty + title_step // 2, text, title_style, anchor="lm")
            if entry.cancelled:
                fill(canvas, (x + text_x, ty + title_step // 2 - px(0.75), right, ty + title_step // 2 + px(0.75)), 1, MUTED)
            ty += title_step

        sticker_x = x + width - px(12) - (slot_w - px(10))
        for picture in art:
            # A fixed square inside the row's padding, so a sticker cannot cross the block's edge.
            fitted = ImageOps.contain(picture.convert("RGBA"), (size, size), Image.Resampling.LANCZOS)
            if entry.cancelled:
                alpha = fitted.getchannel("A").point(lambda a: a * 45 // 100)
                fitted = ImageOps.grayscale(fitted).convert("RGBA")
                fitted.putalpha(alpha)
            canvas.alpha_composite(fitted, (sticker_x + (size - fitted.width) // 2, y + (height - fitted.height) // 2))
            sticker_x += size + px(STICKER_GAP)

    card.add(height, paint, gap=gap)
