"""Dynamics: dedicated public-site queries and explicit card delivery through the scene outlet."""

import asyncio
from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Literal
from pydantic import Field

from len_bot.plugin import Image, Invocation, PluginContext, Text, tool

from .content_card import render_collection, picture_urls, story, decode_picture, emoji_sources
from .command_args import MEMBER_NAME_ALIASES
from .schedule import card_fonts
from .client import Client, Response
from .requests import DynamicsRequest, FanartRequest, CardRequest
from .models import Dynamic, DynamicPage, Fanart, FanartPage, HistoricalDay, Members


class DynamicsFeature:
    def _init_dynamics(self, ctx: PluginContext) -> None:
        self.dynamics_fonts = card_fonts()
        self.dynamics_client = Client(ctx.config['dynamics_api_url'], timeout=ctx.config['request_timeout_seconds'],
                                      ttl=ctx.config['dynamics_cache_seconds'])

    async def _stop_dynamics(self) -> None:
        await self.dynamics_client.close()

    @tool('asoul_dynamics', '查询 A-SOUL 成员和 B 站动态存档，只返回数据，不发消息。request.action：'
          'members 成员列表；search 按关键词、成员、类型、时间搜索，空关键词按排序列出；read 按 dynamic_id 读取单条；'
          'history 往年同月同日的动态。要把结果发成卡片，用 asoul_send_card。',
          summary='查询 A-SOUL 成员、搜索和读取历史动态')
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

    @tool('asoul_fanart', '搜索或随机抽取 A-SOUL 二创和官方物料，只返回数据，不发消息。request.action：'
          'search 按关键词、角色、类型筛选；random 随机抽取。结果里的 sourceDynamicId 可交给 asoul_send_card 发单条。',
          summary='搜索或随机抽取 A-SOUL 二创')
    async def query_fanart(self, ctx: Invocation,
                           request: Annotated[FanartRequest, Field(description='二创搜索或随机请求')]) -> dict:
        values = request.model_dump(exclude={'action'})
        if request.action == 'search':
            return await self.fanart(ctx, **values)
        return await self.random_fanart(ctx, **values)

    @tool('asoul_send_card', '把 A-SOUL 图片卡片发到当前群，返回发送回执 delivery。request.action：'
          'schedule 今天、明天或本周日程；history 往年同日动态；random_fanart 随机二创；'
          'dynamic_search、fanart_search 搜索结果；dynamic、fanart 按查询结果里的 ID 发单条。'
          '群友想看卡片时直接调用，不用先查询；只需要信息回答时用 live_schedule、asoul_dynamics 或 asoul_fanart。',
          summary='发送 A-SOUL 日程、历史动态或二创卡片')
    async def card(self, ctx: Invocation,
                   request: Annotated[CardRequest, Field(description='卡片类型、筛选条件或真实来源 ID')]) -> dict:
        values = request.model_dump(exclude={'action'})
        if request.action == 'schedule':
            label = {'today':'今天','tomorrow':'明天','week':'本周'}[request.period]
            sent = await self.send_schedule(ctx,label+(' -a' if request.exclude_filtered_hosts else ''))
            return {'delivery':{**asdict(sent),'message_ids':list(sent.message_ids)}}
        if 'member' in values:
            values['member'] = await self.member_id(values['member'])
        if request.action == 'dynamic':
            return await self.send_dynamic(ctx, **values)
        if request.action == 'fanart':
            return await self.send_fanart(ctx, **values)
        if request.action == 'history':
            result = await self.history(ctx,**values)
            items = HistoricalDay.model_validate(result['data']).items
            month, day = (int(part) for part in result['data']['monthDay'].split('-'))
            title, subtitle = '历史上的今天', f'{month}月{day}日 · 往年同日 · {len(items)} 条动态'
        elif request.action == 'dynamic_search':
            result = await self.search(ctx,**values)
            items = DynamicPage.model_validate(result['data']).items
            title, subtitle = '历史动态搜索', ' · '.join(part for part in (request.query, f'共 {result["data"]["total"]} 条') if part)
        elif request.action == 'fanart_search':
            result = await self.fanart(ctx,**values)
            items = FanartPage.model_validate(result['data']).items
            title, subtitle = '二创搜索', ' · '.join(part for part in (request.query, request.character, f'共 {result["data"]["total"]} 条') if part)
        else:
            result = await self.random_fanart(ctx,**values)
            items = FanartPage.model_validate(result['data']).items[:request.limit]
            title, subtitle = '随机二创',request.character or 'A-SOUL 二创'
        sent = await self.deliver_collection(ctx,items,title,subtitle,
                    summary=request.action in {'dynamic_search','fanart_search'})
        return {'delivery':{**asdict(sent),'message_ids':list(sent.message_ids)},'items':len(items),'source':result['source']}

    async def member_id(self, member: str | None) -> str | None:
        if member is None or member.startswith('uid:'):
            return member
        if member.isdigit():
            return 'uid:' + member
        member = MEMBER_NAME_ALIASES.get(member, MEMBER_NAME_ALIASES.get(member.lower(), member))
        response = await self.dynamics_client.query('members', Members)
        matches = [item.id for item in response.data.members if member.casefold() in item.name.casefold()]
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
        day = month_day if month_day is not None else datetime.fromtimestamp(ctx.now(), self.calendar_zone).strftime('%m-%d')
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
        category: str = 'all',
        source: Literal['all', 'bilibili', 'douban'] = 'all',
        limit: int = 1,
    ) -> dict:
        return (await self.dynamics_client.query('fanart', FanartPage,
                       {'q': query, 'character': character, 'contentType': content_type, 'kind': kind,
                        'category': category, 'source': source, 'limit': limit, 'random': '1'}, cached=False)).output()

    async def send_dynamic(
        self,
        ctx: Invocation,
        dynamic_id: str,
        member: str | None = None,
        include_images: bool = True,
    ) -> dict:
        response = await self.dynamics_client.dynamic(dynamic_id, member)
        return await self.send_entry(ctx, response, response.data, include_images)

    async def send_fanart(
        self,
        ctx: Invocation,
        source_dynamic_id: str,
        include_images: bool = True,
    ) -> dict:
        response = await self.dynamics_client.fanart(source_dynamic_id)
        return await self.send_entry(ctx, response, response.data, include_images)

    async def prepare_media(self, items):
        urls = list(dict.fromkeys(url for item in items for url in [story(item).avatar, *picture_urls(item), *emoji_sources(item).values()] if url))
        semaphore = asyncio.Semaphore(5)
        async def one(url):
            async with semaphore:
                try:
                    data = await self.dynamics_client.image(url)
                    return url, data, await asyncio.to_thread(decode_picture, data)
                except Exception as error:
                    self.ctx.report_error('动态卡片图片', error)
                    return url, None, None
        results = await asyncio.gather(*(one(url) for url in urls))
        return ({url: data for url, data, _ in results if data is not None},
                {url: image for url, _, image in results if image is not None})

    @staticmethod
    def fallback_text(title, items):
        rows = [title]
        for raw in items:
            item = story(raw)
            rows.append('\n'.join(value for value in [item.author, item.stamp or item.tags, item.text,
                        '转发原文 · ' + item.original if item.original else '', item.metrics, item.source,
                        raw.mediaUrl if isinstance(raw,Fanart) and raw.mediaUrl and raw.mediaUrl != item.source else ''] if value))
        return '\n\n'.join(rows)

    async def collection_parts(self, items, title, subtitle, *, summary=False):
        if not self.ctx.config['render_cards']:
            return [Text(self.fallback_text(title,items))], [], {}
        raw_images, pictures = await self.prepare_media(items)
        try:
            pages = await asyncio.to_thread(render_collection,title,subtitle,items,self.dynamics_fonts,pictures,summary=summary)
        except Exception as error:
            self.ctx.report_error('动态卡片渲染',error)
            return [Text(self.fallback_text(title,items))], [], raw_images
        parts = [Image(page.data,title+'\n'+page.text) for page in pages]
        return parts, pages, raw_images

    async def deliver_collection(self,ctx,items,title,subtitle,*,summary=False,empty='暂无相关内容。'):
        if not items:
            return await ctx.reply(empty)
        parts, _, _ = await self.collection_parts(items,title,subtitle,summary=summary)
        links = list(dict.fromkeys(url for item in items for url in [story(item).source,
                    item.mediaUrl if isinstance(item,Fanart) and not summary else None] if url))
        if self.ctx.config['render_cards'] and links:
            parts.append(Text('\n'.join(links)))
        sent = await ctx.reply_parts(parts)
        if sent.status == 'failed':
            raise RuntimeError(sent.report)
        return sent

    async def send_entry(self, ctx: Invocation, response: Response, item: Dynamic | Fanart, include_images: bool) -> dict:
        source_item = story(item)
        title = source_item.author + (' · 动态' if isinstance(item,Dynamic) else ' · 二创')
        parts, pages, raw_images = await self.collection_parts([item],title,source_item.stamp or source_item.tags)
        urls = picture_urls(item)
        if include_images:
            for index,url in enumerate(urls,1):
                data = raw_images.get(url)
                if data is None:
                    data = await self.dynamics_client.image(url)
                parts.append(Image(data,f'{title} · 原图 {index}'))
        links = [source_item.source]
        if isinstance(item,Fanart) and item.mediaUrl and item.mediaUrl != source_item.source:
            links.append(item.mediaUrl)
        if not any(isinstance(part,Text) and source_item.source in part.text for part in parts):
            parts.append(Text('\n'.join(links)))
        sent = await ctx.reply_parts(parts)
        return {'delivery': {**asdict(sent), 'message_ids': list(sent.message_ids)}, 'card_pages_prepared': len(pages),
                'source_images_prepared': len(urls) if include_images else 0,
                'source_images_omitted': [] if include_images else urls,
                'source': response.source, 'fetched_at': response.fetched_at,
                'degraded_sources': response.degraded}
