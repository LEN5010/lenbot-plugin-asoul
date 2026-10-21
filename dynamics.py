"""Dynamics: dedicated public-site queries and explicit card delivery through the scene outlet."""

import asyncio
from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Literal
from pydantic import Field
from zoneinfo import ZoneInfo

from len_bot.plugin import Image, Invocation, PluginContext, Text, tool
from len_bot.text_cards import CardSection, TextCards

from .cards import dynamic_sections, fanart_sections
from .schedule import FONT
from .client import Client, Response
from .requests import DynamicsRequest, FanartRequest, CardRequest
from .models import Dynamic, DynamicPage, Fanart, FanartPage, HistoricalDay, Members


class DynamicsFeature:
    def _init_dynamics(self, ctx: PluginContext) -> None:
        self.dynamics_cards = TextCards(FONT)
        self.dynamics_client = Client(ctx.config['dynamics_api_url'], timeout=ctx.config['request_timeout_seconds'],
                                      ttl=ctx.config['dynamics_cache_seconds'])

    async def _stop_dynamics(self) -> None:
        await self.dynamics_client.close()

    @tool('asoul_dynamics', '读取成员、查询或读取动态、查询往年今日；request.action 选择操作。'
          '成员可用源站 ID 或列表中的完整名称，分页游标原样传递。查询数据，不发送。',
          summary='查询 A-SOUL 成员和动态')
    async def query_dynamics(self, ctx: Invocation,
                             request: Annotated[DynamicsRequest, Field(description='成员、动态搜索、详情或往年今日请求')]) -> dict:
        values = request.model_dump(exclude={'action'})
        if 'member' in values:
            values['member'] = await self.member_id(values['member'])
        if request.action == 'members':
            return await self.members(ctx)
        if request.action == 'search':
            return await self.search(ctx, **values)
        if request.action == 'read':
            return await self.read(ctx, **values)
        return await self.history(ctx, **values)

    @tool('asoul_fanart', '搜索二创/物料或随机查询；request.action 为 search 或 random。'
          '列表返回真实 sourceDynamicId 和游标。',
          summary='搜索或随机查询 A-SOUL 二创')
    async def query_fanart(self, ctx: Invocation,
                           request: Annotated[FanartRequest, Field(description='二创搜索或随机请求')]) -> dict:
        values = request.model_dump(exclude={'action'})
        if request.action == 'search':
            return await self.fanart(ctx, **values)
        return await self.random_fanart(ctx, **values)

    @tool('asoul_send_card', '按真实来源 ID 重新读取动态或二创并发送卡片；request.action 选择 dynamic 或 fanart。'
          '可附来源原图；结果 delivery 是实际发送回执，不重复发送。', summary='发送 A-SOUL 动态或二创卡片')
    async def card(self, ctx: Invocation,
                   request: Annotated[CardRequest, Field(description='要发送的动态或二创及其来源 ID')]) -> dict:
        values = request.model_dump(exclude={'action'})
        if request.action == 'dynamic':
            values['member'] = await self.member_id(values['member'])
            return await self.send_dynamic(ctx, **values)
        return await self.send_fanart(ctx, **values)

    async def member_id(self, member: str | None) -> str | None:
        if member is None or member.startswith('uid:'):
            return member
        response = await self.dynamics_client.query('members', Members)
        matches = [item.id for item in response.data.members if item.name == member]
        if len(matches) != 1:
            raise ValueError(f'成员名称未唯一匹配源站列表：{member!r}；原列表={response.data.model_dump()}')
        return matches[0]

    async def members(
        self,
        ctx: Invocation,
    ) -> dict:
        return (await self.dynamics_client.query('members', Members)).output()

    async def search(
        self,
        ctx: Invocation,
        query: str,
        member: str | None = None,
        dynamic_type: Literal['text', 'image', 'video', 'forward', 'article', 'live', 'other'] | None = None,
        start: str | None = None,
        end: str | None = None,
        sort: Literal['newest', 'oldest', 'likes', 'comments'] = 'newest',
        limit: int = 10,
        cursor: str | None = None,
    ) -> dict:
        return (await self.dynamics_client.query('search', DynamicPage,
                       {'q': query, 'member': member, 'type': dynamic_type, 'from': start, 'to': end,
                        'sort': sort, 'limit': limit, 'cursor': cursor})).output()

    async def read(
        self,
        ctx: Invocation,
        dynamic_id: str,
        member: str | None = None,
    ) -> dict:
        return (await self.dynamics_client.dynamic(dynamic_id, member)).output()

    async def history(
        self,
        ctx: Invocation,
        month_day: str | None = None,
        sort: Literal['hot', 'likes', 'comments'] = 'hot',
        limit: int = 8,
    ) -> dict:
        day = month_day if month_day is not None else datetime.fromtimestamp(ctx.now(), ZoneInfo(ctx.timezone())).strftime('%m-%d')
        return (await self.dynamics_client.query('on-this-day', HistoricalDay,
                       {'monthDay': day, 'sort': sort, 'limit': limit})).output()

    async def fanart(
        self,
        ctx: Invocation,
        query: str = '',
        character: str | None = None,
        content_type: Literal['all', 'image', 'video', 'text', 'other'] = 'all',
        kind: Literal['all', 'fanart', 'material'] = 'fanart',
        category: str = 'all',
        source: Literal['all', 'bilibili', 'douban'] = 'all',
        sort: Literal['newest', 'oldest', 'views', 'favorites'] = 'newest',
        limit: int = 10,
        cursor: str | None = None,
    ) -> dict:
        return (await self.dynamics_client.query('fanart', FanartPage,
                       {'q': query, 'character': character, 'contentType': content_type, 'kind': kind,
                        'category': category, 'source': source, 'sort': sort, 'limit': limit, 'cursor': cursor})).output()

    async def random_fanart(
        self,
        ctx: Invocation,
        query: str = '',
        character: str | None = None,
        content_type: Literal['all', 'image', 'video', 'text', 'other'] = 'all',
        kind: Literal['all', 'fanart', 'material'] = 'fanart',
        source: Literal['all', 'bilibili', 'douban'] = 'all',
        limit: int = 1,
    ) -> dict:
        return (await self.dynamics_client.query('fanart', FanartPage,
                       {'q': query, 'character': character, 'contentType': content_type, 'kind': kind,
                        'source': source, 'limit': limit, 'random': '1'}, cached=False)).output()

    async def send_dynamic(
        self,
        ctx: Invocation,
        dynamic_id: str,
        member: str | None = None,
        include_images: bool = True,
    ) -> dict:
        response = await self.dynamics_client.dynamic(dynamic_id, member)
        return await self.send(ctx, response, dynamic_sections(response.data), response.data.url, include_images)

    async def send_fanart(
        self,
        ctx: Invocation,
        source_dynamic_id: str,
        include_images: bool = True,
    ) -> dict:
        response = await self.dynamics_client.fanart(source_dynamic_id)
        return await self.send(ctx, response, fanart_sections(response.data), response.data.sourceDynamicUrl, include_images)

    async def send(self, ctx: Invocation, response: Response[Dynamic] | Response[Fanart],
                   document: tuple[str, str, list[CardSection], list[str]], source: str, include_images: bool) -> dict:
        title, subtitle, sections, urls = document
        if include_images and len(urls) > 16:
            raise ValueError(f'来源有 {len(urls)} 张图片，超过单次16张；可明确 include_images=false 只发正文卡片')
        if response.degraded is not None:
            sections.insert(0, CardSection('部分数据缺失', response.degraded))
        if urls and not include_images:
            sections.append(CardSection('图片链接', '\n'.join(urls)))
        pages = await asyncio.to_thread(self.dynamics_cards.render, title, subtitle, sections, source=source)
        parts = [Image(page.data, f'{title} · 第 {index} 页\n{page.text}') for index, page in enumerate(pages, 1)]
        if include_images:
            for index, url in enumerate(urls, 1):
                parts.append(Image(await self.dynamics_client.image(url), f'{title} · 来源原图 {index}: {url}；未做视觉分析'))
        parts.append(Text(source))
        sent = await ctx.reply_parts(parts)
        return {'delivery': {**asdict(sent), 'message_ids': list(sent.message_ids)}, 'card_pages_prepared': len(pages),
                       'source_images_prepared': len(urls) if include_images else 0,
                       'source_images_omitted': [] if include_images else urls,
                       'source': response.source, 'fetched_at': response.fetched_at,
                       'degraded_sources': response.degraded}
