"""Chat commands matching LEN5010's A-SOUL dynamics plugin."""
from datetime import datetime
import re
import httpx
from .client import SiteError

from len_bot.plugin import Invocation, regex

from .command_args import month_day, parse_fanart_args, MEMBER_NAME_ALIASES, FANART_CHARACTER_OPTIONS
from .models import DynamicPage, FanartPage, HistoricalDay


class DynamicsCommands:
    @regex(r'/?(历史上的今天|那年今日|随机二创|二创|随机图片二创|随机视频二创|二创搜索|搜二创|搜动态|动态搜索)(?:\s+(.*))?',
           '历史上的今天、随机二创、二创搜索和搜动态，支持原插件别名与筛选参数')
    async def dynamics_command(self, ctx: Invocation, match: re.Match[str]) -> None:
        try:
            name, arguments = match[1], (match[2] or '').split()
            if name in {'历史上的今天','那年今日'}:
                await self.history_command(ctx,arguments)
            elif name in {'二创搜索','搜二创'}:
                await self.fanart_search_command(ctx,arguments)
            elif name in {'搜动态','动态搜索'}:
                await self.dynamic_search_command(ctx,arguments)
            else:
                filters=parse_fanart_args(tuple(arguments),name)
                response=await self.dynamics_client.query('fanart',FanartPage,{
                    'random':1,'limit':1,'kind':'fanart','character':filters['character'],
                    'contentType':filters['content_type'],'category':filters['category']},cached=False)
                await self.deliver_collection(ctx,response.data.items[:1],'随机二创',
                    ' · '.join({'image':'图片','video':'视频','text':'文字','other':'其他','all':'全部'}.get(value,value) for value in filters.values() if value),empty='未找到符合条件的二创内容。')

        except SiteError as error:
            self.ctx.report_error('动态站查询',error)
            await ctx.reply(str(error)+'。')
        except httpx.HTTPError as error:
            self.ctx.report_error('动态站连接',error)
            await ctx.reply('动态站连接失败，请稍后重试。')

    async def history_command(self,ctx: Invocation,arguments: list[str]) -> None:
        target=datetime.fromtimestamp(ctx.now(),self.calendar_zone).strftime('%m-%d')
        limit=self.ctx.config['on_this_day_default_limit']
        try:
            for value in arguments:
                if value.isdigit():
                    limit=max(1,min(20,int(value)))
                else:
                    target=month_day(value)
        except ValueError:
            await ctx.reply('用法：/历史上的今天 [MM-DD] [条数]，例如 /历史上的今天 08-16 5')
            return
        response=await self.dynamics_client.query('on-this-day',HistoricalDay,
            {'monthDay':target,'sort':'hot','limit':limit},ttl=self.ctx.config['on_this_day_cache_minutes']*60)
        month,day=(int(part) for part in target.split('-'))
        await self.deliver_collection(ctx,response.data.items,'历史上的今天',f'{month}月{day}日 · 往年同日 · {len(response.data.items)} 条动态',
                                      empty=f'{target} 暂无往年动态记录。')

    async def fanart_search_command(self,ctx: Invocation,arguments: list[str]) -> None:
        if not arguments:
            await ctx.reply('用法：/二创搜索 关键词 [角色]，例如 /二创搜索 生日 嘉然')
            return
        character=None
        query=arguments[0]
        if len(arguments)>1:
            canonical=MEMBER_NAME_ALIASES.get(arguments[1],arguments[1])
            character=next((value for value in FANART_CHARACTER_OPTIONS if canonical in value or value in canonical),None)
        response=await self.dynamics_client.query('fanart',FanartPage,{
            'q':query,'character':character,'sort':'newest','limit':self.ctx.config['default_search_limit']})
        await self.deliver_collection(ctx,response.data.items,'二创搜索',
            f'{query}'+(f' · {character}' if character else '')+f' · 共 {response.data.total} 条',
            summary=True,empty='未找到匹配的二创内容。')

    async def dynamic_search_command(self,ctx: Invocation,arguments: list[str]) -> None:
        if not arguments:
            await ctx.reply('用法：/搜动态 关键词 [成员] [排序]，例如 /搜动态 生日 乃琳 likes')
            return
        query=arguments[0]
        sort=arguments[-1] if arguments[-1] in {'newest','oldest','likes','comments'} and len(arguments)>1 else 'newest'
        members=arguments[1:-1] if len(arguments)>1 and arguments[-1] in {'newest','oldest','likes','comments'} else arguments[1:]
        member=await self.member_id(members[0]) if members else None
        response=await self.dynamics_client.query('search',DynamicPage,{
            'q':query,'member':member,'sort':sort,'limit':self.ctx.config['default_search_limit']})
        await self.deliver_collection(ctx,response.data.items,'历史动态搜索',
            f'{query}'+(f' · {members[0]}' if members else '')+f' · 共 {response.data.total} 条',
            summary=True,empty='未找到相关历史动态。')
