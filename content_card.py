"""Image-led A-SOUL cards using LenBot's panel palette and typography scale."""
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from functools import lru_cache
import json
import re
from zoneinfo import ZoneInfo

from PIL import Image, ImageOps
import qrcode

from .card_kit import (CHIP_HEIGHT, Card, Fonts, INK, MUTED, PINK, PINK_LINE, SURFACE, Style, compact, circle, chip_width,
                       divider, draw_chip, draw_lines, draw_text, fill, fit, flatten, layout, px, qr_block, rounded, Run,
                       signature, title_header)
from .models import Dynamic, Fanart

BODY = Style(17.5, color=INK)
BODY_RATIO = 1.66
SITE = 'len5010.top/dynamics'


@dataclass
class Story:
    author: str
    avatar: str
    text: str
    source: str
    stamp: str = ''
    tags: str = ''
    images: list[str] = field(default_factory=list)
    metrics: str = ''
    original: str = ''


@dataclass
class Page:
    data: bytes
    text: str


@lru_cache(maxsize=1)
def emoji_map():
    return json.loads((Path(__file__).parent/'assets/emojis.json').read_text())


def emoji_sources(item: Dynamic | Fanart) -> dict[str, str]:
    known = emoji_map().copy()
    if isinstance(item, Dynamic):
        media = [*item.media, *(item.orig.media or [] if item.orig else [])]
        known.update({part.label: part.url for part in media if part.kind == 'emoji' and part.label and part.url})
    text = item.contentText if isinstance(item,Dynamic) else item.text
    if isinstance(item,Dynamic) and item.orig:
        text += item.orig.text
    return {label: known.get(label,known.get('['+label.strip('[]').strip()+']',''))
            for label in re.findall(r'\[[^\]]+\]',text)
            if known.get(label) or known.get('['+label.strip('[]').strip()+']')}


def rich_lines(item, fonts, width, pictures):
    raw = story(item)
    text = raw.text + ('\n\n转发原文 · '+raw.original if raw.original else '')
    text = re.sub(r'\n\s*\n+', '\n\n', text.strip())   # Runs of blank lines become one paragraph break.
    emojis = emoji_sources(item)
    runs = []
    alt = {}
    for part in re.split(r'(\[[^\]]+\])',text):
        url = emojis.get(part)
        if url and url in pictures:
            picture = pictures[url]
            alt[id(picture)] = part
            runs.append(Run(image=picture))
        else:
            runs.append(Run(part))
    return layout(fonts,runs,BODY,width), alt


def picture_urls(item: Dynamic | Fanart) -> list[str]:
    urls = list(item.images)
    if isinstance(item, Dynamic):
        urls += [media.url for media in item.media if media.url and media.kind in {'image', 'cover', 'video'}]
        if item.orig:
            urls += item.orig.images
            urls += [media.url for media in item.orig.media or [] if media.url and media.kind in {'image', 'cover', 'video'}]
    return list(dict.fromkeys(urls))


def story(item: Dynamic | Fanart) -> Story:
    if isinstance(item, Dynamic):
        stamp = datetime.fromisoformat(item.publishedAt).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y.%m.%d %H:%M') if item.publishedAt else ''
        kinds = {'text': '文字动态', 'image': '图文动态', 'video': '视频', 'forward': '转发', 'article': '专栏', 'live': '直播'}
        return Story(item.member.name, item.member.avatarUrl, item.contentText, item.url, stamp,
                     kinds.get(item.type, '动态'), picture_urls(item),
                     f'点赞 {compact(item.likeCount)}  ·  评论 {compact(item.commentCount)}  ·  转发 {compact(item.forwardCount)}',
                     f'{item.orig.authorName}：{item.orig.text}' if item.orig else '')
    metrics = []
    if item.viewCount is not None:
        metrics.append('播放 ' + compact(item.viewCount))
    if item.favoriteCount is not None:
        metrics.append('收藏 ' + compact(item.favoriteCount))
    return Story(item.authorName, item.authorAvatarUrl, item.text, item.sourceDynamicUrl,
                 tags=' · '.join([*item.characterTags, item.category]), images=picture_urls(item), metrics='  ·  '.join(metrics))


def image_grid(card: Card, pictures: list[Image.Image], total: int) -> None:
    if not pictures:
        return
    pictures = [flatten(picture) for picture in pictures[:3]]
    columns = len(pictures)
    gap = px(6)
    if columns == 1:
        picture = pictures[0]
        # Wide pictures fill the column; tall ones keep their shape and stay left-aligned.
        height = min(px(340), round(card.inner * picture.height / picture.width))
        width = min(card.inner, round(height * picture.width / picture.height))
        boxes = [(0, width, height)]
    else:
        cell = (card.inner - (columns - 1) * gap) // columns
        height = round(cell * (0.75 if columns == 2 else 1))
        boxes = [(index * (cell + gap), cell, height) for index in range(columns)]
    more = total - columns

    def paint(canvas, x, y, width):
        for index, (picture, (left, w, h)) in enumerate(zip(pictures, boxes)):
            tile = ImageOps.fit(picture, (w, h), Image.Resampling.LANCZOS)
            if index == columns - 1 and more > 0:
                tile = Image.blend(tile, Image.new('RGB', tile.size, INK), 0.45)
            canvas.alpha_composite(rounded(tile), (x + left, y))
            if index == columns - 1 and more > 0:
                draw_text(canvas, card.fonts, x + left + w / 2, y + h / 2, f'+{more}', Style(22, weight=700, color=SURFACE),
                          anchor='mm')
    card.add(height, paint, gap=12)


def add_story(card: Card, item: Story, lines: list, pictures: dict[str, Image.Image], *, first: bool, opening: bool) -> None:
    fonts = card.fonts
    avatar_size = px(46)
    chip = item.tags[:5] if item.tags and item.stamp else ''

    def author(canvas, x, y, width):
        avatar = pictures.get(item.avatar)
        if avatar:
            canvas.alpha_composite(circle(avatar, avatar_size), (x, y))
        else:
            fill(canvas, (x, y, x + avatar_size, y + avatar_size), avatar_size // 2, PINK_LINE)
            draw_text(canvas, fonts, x + avatar_size // 2, y + avatar_size // 2, item.author[:1],
                      Style(17, weight=800, color=PINK), anchor='mm')
        name_w = width - px(58) - (chip_width(fonts, chip) + px(8) if chip else 0)
        name_style = Style(18, weight=800, color=PINK)
        draw_text(canvas, fonts, x + px(58), y + px(4), fit(fonts, item.author, name_style, name_w), name_style)
        draw_text(canvas, fonts, x + px(58), y + px(29), item.stamp or item.tags, Style(13.5, color=MUTED))
        if chip:
            draw_chip(canvas, fonts, x + width - chip_width(fonts, chip), y + (avatar_size - px(CHIP_HEIGHT)) // 2, chip)

    card.add(avatar_size, author, gap=26 if opening else 18)

    def body(canvas, x, y, width):
        draw_lines(canvas, fonts, lines, x, y, BODY, ratio=BODY_RATIO)
    if lines:
        card.add(len(lines) * px(BODY.size * BODY_RATIO), body, gap=12)
    if first:
        image_grid(card, [pictures[url] for url in item.images[:3] if url in pictures], len(item.images))
        if item.metrics:
            card.add(px(18), lambda canvas, x, y, w: draw_text(canvas, fonts, x, y + px(2), item.metrics,
                                                                Style(14, color="#686873")), gap=13)


def qr_image(source: str) -> Image.Image:
    code = qrcode.QRCode(box_size=4, border=1)
    code.add_data(source)
    code.make(fit=True)
    return code.make_image(fill_color=INK, back_color=SURFACE).convert('RGB')


def close(card: Card, source: str, many: bool) -> None:
    def details(canvas, x, y, width, height):
        fonts = card.fonts
        draw_text(canvas, fonts, x, y + px(24), 'A-SOUL 动态站', Style(17, weight=800, color=PINK), anchor='lm')
        draw_text(canvas, fonts, x, y + px(47), SITE, Style(13, color=MUTED), anchor='lm')
        draw_text(canvas, fonts, x, y + px(68), '扫码看第一条' if many else '扫码看原动态', Style(13, color=MUTED), anchor='lm')

    qr_block(card, details, px(92), qr_image(source))
    signature(card)


def render_collection(title: str, subtitle: str, items: list[Dynamic | Fanart], fonts: Fonts,
                      pictures: dict[str, Image.Image], *, summary: bool = False) -> list[Page]:
    pages = []
    card = Card(fonts)
    title_header(card, 'A-SOUL 动态查询站', title, subtitle)
    source = items[0].url if isinstance(items[0], Dynamic) else items[0].sourceDynamicUrl
    descriptions = []
    for raw in items:
        item = story(raw)
        lines, alt = rich_lines(raw,fonts,card.inner,pictures)
        if summary and len(lines)>6:
            lines = lines[:6]
        chunks = [lines[start:start+22] for start in range(0,len(lines),22)] or [[]]
        for index, chunk in enumerate(chunks):
            estimate = px(100+len(chunk)*29+(340 if item.images and index==0 else 0))
            if descriptions and sum(h+gap for h,_,gap in card.blocks)+estimate>px(1100):
                close(card, source, len(items) > 1)
                pages.append(Page(card.render(),'\n\n'.join(descriptions)))
                descriptions=[]
                card=Card(fonts)
                title_header(card, 'A-SOUL 动态查询站', title + ' · 续', subtitle)
            if descriptions:
                divider(card, 22, dashed=True)
            add_story(card,item,chunk,pictures,first=index==0,opening=not descriptions)
            description = ''.join(''.join(unit[1] if unit[0]=='text' else alt.get(id(unit[1]),'') for unit in line)
                                  + ('' if line.soft else '\n') for line in chunk).rstrip('\n')
            descriptions.append(item.author+'\n'+description+'\n'+item.metrics)
    close(card, source, len(items) > 1)
    pages.append(Page(card.render(),'\n\n'.join(descriptions)))
    return pages


def decode_picture(data: bytes) -> Image.Image:
    with Image.open(BytesIO(data)) as picture:
        return ImageOps.exif_transpose(picture).convert('RGBA')
