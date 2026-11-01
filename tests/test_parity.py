"""Upstream chat behavior through the actual LenBot matcher and sender."""
from datetime import datetime, timedelta
from pathlib import Path
import json

import pytest
from len_bot.plugin import Image, Text
from len_bot.plugin_testing import PluginTest

from .test_calendar import calendar, config

PACKAGE = Path(__file__).parents[1]
NOW = datetime.fromisoformat('2026-10-30T12:00:00+08:00')
MEMBER = {'id':'uid:672328094','bilibiliUid':'672328094','name':'嘉然今天吃什么','avatarUrl':''}


def dynamic(text='今晚七点见',identifier='1'):
    return {'id':identifier,'dynamicId':identifier,'member':MEMBER,'type':'text','contentText':text,
            'publishedAt':'2022-08-16T12:00:00+08:00','url':'https://t.bilibili.com/'+identifier,
            'images':[],'media':[],'likeCount':1234,'commentCount':56,'forwardCount':78}


def fanart():
    return {'sourceDynamicId':'2','sourceDynamicUrl':'https://t.bilibili.com/2','kind':'fanart','contentType':'video',
            'mediaUrl':'https://www.bilibili.com/video/BV1xx411c7mD','category':'剪辑·AMV','authorUid':'123',
            'authorName':'枝江剪辑','authorAvatarUrl':'','authorSpaceUrl':'https://space.bilibili.com/123',
            'characterTags':['嘉然'],'text':'嘉然生日剪辑','images':[],'viewCount':520,'favoriteCount':33,'statsFetchedAt':None}


def routes(source):
    source.json('/api/members',{'members':[MEMBER]})
    source.json('/api/search',{'items':[dynamic()],'total':1,'nextCursor':None,'prevCursor':None})
    source.json('/api/on-this-day',{'monthDay':'08-16','sort':'hot','items':[dynamic()]})
    source.json('/api/fanart',{'items':[fanart(),fanart()],'total':1,'nextCursor':None,'prevCursor':None,
                               'snapshot':{'id':'fixture','activatedAt':'2026-10-30T00:00:00Z'}})


@pytest.mark.asyncio
@pytest.mark.parametrize('name',['历史上的今天','那年今日'])
async def test_history_commands_parse_dates_and_keep_public_statistics(source,name):
    routes(source)
    async with PluginTest(PACKAGE,config=config(source,remind_minutes=0,render_cards=False),now=NOW.timestamp) as bot:
        assert await bot.message(f'/{name} 8月16日 5')
        assert source.requests[-1][1]=={'monthDay':['08-16'],'sort':['hot'],'limit':['5']}
        text=bot.deliveries[-1].text
        assert '今晚七点见' in text and '点赞 1234' in text and '转发 78' in text
        assert 'https://t.bilibili.com/1' in text


@pytest.mark.asyncio
@pytest.mark.parametrize('name',['历史上的今天','那年今日'])
async def test_plain_history_triggers_use_the_business_timezone(source,name):
    routes(source)
    async with PluginTest(PACKAGE,config=config(source,remind_minutes=0,render_cards=False),now=NOW.timestamp) as bot:
        assert await bot.message(name)
        assert source.requests[-1][1]['monthDay']==['10-30']
        assert source.requests[-1][1]['limit']==['3']
        await bot.message(name)
        assert len([path for path,_ in source.requests if path=='/api/on-this-day'])==1


@pytest.mark.asyncio
@pytest.mark.parametrize('name,args,expected',[
    ('随机二创','拉姐 剪辑',{'character':['贝拉'],'category':['剪辑·AMV']}),
    ('二创','嘉然 图片',{'character':['嘉然'],'contentType':['image']}),
    ('随机图片二创','心宜思诺',{'character':['心宜&思诺'],'contentType':['image']}),
    ('随机视频二创','乃琳',{'character':['乃琳'],'contentType':['video']}),
])
async def test_random_aliases_forward_the_upstream_filters(source,name,args,expected):
    routes(source)
    async with PluginTest(PACKAGE,config=config(source,remind_minutes=0,render_cards=False)) as bot:
        assert await bot.message(f'/{name} {args}')
        params=source.requests[-1][1]
        assert params['random']==['1'] and params['limit']==['1']
        assert all(params[key]==value for key,value in expected.items())
        assert bot.deliveries[-1].text.count('嘉然生日剪辑')==1
        assert 'https://www.bilibili.com/video/BV1xx411c7mD' in bot.deliveries[-1].text


@pytest.mark.asyncio
@pytest.mark.parametrize('name',['搜动态','动态搜索'])
async def test_dynamic_search_resolves_nicknames_and_sort(source,name):
    routes(source)
    async with PluginTest(PACKAGE,config=config(source,remind_minutes=0,render_cards=False)) as bot:
        await bot.message(f'/{name} 生日 然然 likes')
        assert source.requests[-1][1]=={'q':['生日'],'member':['uid:672328094'],'sort':['likes'],'limit':['5']}
        assert '今晚七点见' in bot.deliveries[-1].text


@pytest.mark.asyncio
@pytest.mark.parametrize('name',['二创搜索','搜二创'])
async def test_fanart_search_includes_materials_and_sends_a_card(source,name):
    routes(source)
    async with PluginTest(PACKAGE,config=config(source,remind_minutes=0)) as bot:
        await bot.message(f'/{name} 生日 嘉然')
        assert source.requests[-1][1]=={'q':['生日'],'character':['嘉然'],'sort':['newest'],'limit':['5']}
        card,link=bot.deliveries[-1].parts
        assert isinstance(card,Image) and '收藏 33' in card.description
        assert isinstance(link,Text) and link.text=='https://t.bilibili.com/2'


@pytest.mark.asyncio
async def test_long_dynamic_is_paginated_in_full(source):
    routes(source)
    text='春天的排练记录。'*600+'结尾仍然完整'
    source.json('/api/search',{'items':[dynamic(text)],'total':1,'nextCursor':None,'prevCursor':None})
    async with PluginTest(PACKAGE,config=config(source,remind_minutes=0)) as bot:
        result=json.loads(await bot.tool('asoul_send_card',{'request':{'action':'dynamic','dynamic_id':'1','include_images':False}}))
        assert result['card_pages_prepared']>1
        description=''.join(part.description for part in bot.deliveries[-1].parts if isinstance(part,Image))
        assert '结尾仍然完整' in description
        assert description.count('春天')>=500


@pytest.mark.asyncio
async def test_schedule_groups_shared_streams_and_filters_hosts(source):
    day=NOW.replace(hour=19,minute=0)
    source.text('/calendar.ics',calendar(
        ('a',day,'嘉然直播: 一起唱歌','嘉然'),('b',day,'乃琳直播: 一起唱歌','乃琳'),
        ('c',day+timedelta(hours=1),'心宜直播: 游戏','心宜'),('d',day+timedelta(hours=1),'思诺直播: 游戏','思诺')))
    async with PluginTest(PACKAGE,config=config(source,remind_minutes=0,card_mode='text'),now=NOW.timestamp) as bot:
        await bot.message('今日直播 -a')
        text=bot.deliveries[-1].text
        assert text.count('一起唱歌')==1 and '嘉然 / 乃琳' in text
        assert '心宜' not in text and '思诺' not in text
        await bot.message('本周直播')
        assert '游戏' in bot.deliveries[-1].text


@pytest.mark.asyncio
async def test_sunday_tomorrow_matches_the_upstream_rule(source):
    sunday=datetime.fromisoformat('2026-11-01T12:00:00+08:00')
    async with PluginTest(PACKAGE,config=config(source,remind_minutes=0),now=sunday.timestamp) as bot:
        await bot.message('明日直播')
        assert bot.deliveries[-1].text=='还没有下周的直播排表哦'
        assert not source.requests


@pytest.mark.asyncio
async def test_global_highlight_colors_persist_and_orphans_can_be_removed(source):
    source.text('/calendar.ics',calendar(('a',NOW.replace(hour=19),'嘉然直播: 排练','嘉然')))
    async with PluginTest(PACKAGE,config=config(source,remind_minutes=0),owners=['onebot:70001'],now=NOW.timestamp) as bot:
        await bot.message('/日程高亮 今天 1 红色')
        record=bot.host.plugins['asoul']
        saved=await record.context.get_kv('highlights',{})
        assert list(saved.values())[0]['style']=='red'
        await bot.host.reload('asoul',bot.host.config)
        await bot.message('/日程高亮列表')
        assert '红色' in bot.deliveries[-1].text and '排练' in bot.deliveries[-1].text
        await bot.message('/取消日程高亮记录 1')
        assert await bot.host.plugins['asoul'].context.get_kv('highlights',{})=={}
        await bot.host.plugins['asoul'].context.set_kv('highlights',{'orphan':{
            'start':'2020-01-01T19:00:00+08:00','title':'历史安排','hosts':'嘉然','style':'platinum'}})
        await bot.message('/日程高亮列表')
        assert '历史安排' in bot.deliveries[-1].text
        await bot.message('/取消日程高亮记录 1')
        with pytest.raises(RuntimeError,match='主人'):
            await bot.message('/日程高亮 今天 1',sender='onebot:70002')


@pytest.mark.asyncio
@pytest.mark.parametrize('card_request',[
    {'action':'history','month_day':'08-16','limit':3},
    {'action':'random_fanart','character':'嘉然','category':'剪辑·AMV','limit':1},
    {'action':'dynamic_search','query':'生日','member':'然然'},
    {'action':'fanart_search','query':'生日','character':'嘉然'},
    {'action':'schedule','period':'today'},
])
async def test_main_agent_can_call_every_card_action_through_the_host(source,card_request):
    routes(source)
    source.text('/calendar.ics',calendar(('a',NOW.replace(hour=19),'嘉然直播: 排练','嘉然')))
    async with PluginTest(PACKAGE,config=config(source,remind_minutes=0),now=NOW.timestamp) as bot:
        preview = {item['name']:item for item in bot.preview_tools()}
        assert preview['asoul_send_card']['summary'] and preview['asoul_send_card']['instructions']
        result=json.loads(await bot.tool('asoul_send_card',{'request':card_request}))
        assert result['delivery']['status']=='simulated'
        assert any(isinstance(part,Image) for part in bot.deliveries[-1].parts)


@pytest.mark.asyncio
async def test_main_agent_highlight_tools_use_real_owner_and_matching_day_indices(source):
    day=NOW.replace(hour=19)
    source.text('/calendar.ics',calendar(('a',day,'嘉然直播: 合唱','嘉然'),('b',day,'乃琳直播: 合唱','乃琳')))
    async with PluginTest(PACKAGE,config=config(source,remind_minutes=0),owners=['onebot:70001'],now=NOW.timestamp) as bot:
        result=json.loads(await bot.tool('live_schedule',{'start':'2026-10-30'}))
        assert len(result['events'])==2 and len(result['items'])==1
        assert result['items'][0]['index']==1 and result['items'][0]['hosts']==['嘉然','乃琳']
        message=bot.add_message('把合唱标成粉色',sender='onebot:70001')
        args={'source_message_id':message.platform_message_id,
              'request':{'action':'mark','date':'2026-10-30','index':1,'style':'pink'}}
        result=json.loads(await bot.tool('asoul_schedule_highlight',args))
        assert result['status']=='updated' and result['style']=='pink'
        listed=json.loads(await bot.tool('asoul_schedule_highlight',{
            'source_message_id':message.platform_message_id,'request':{'action':'list'}}))
        assert len(listed['records'])==1
        other=bot.add_message('改成红色',sender='onebot:70002')
        with pytest.raises(PermissionError,match='主人'):
            await bot.tool('asoul_schedule_highlight',{**args,'source_message_id':other.platform_message_id})
        removed=json.loads(await bot.tool('asoul_schedule_highlight',{
            'source_message_id':message.platform_message_id,'request':{'action':'remove','index':1}}))
        assert removed['status']=='removed'


@pytest.mark.asyncio
async def test_video_covers_and_inline_emojis_render_inside_the_card(source):
    from io import BytesIO
    from PIL import Image as Picture
    routes(source)
    def png(color,transparent=False):
        output=BytesIO()
        picture=Picture.new('RGBA',(30,30),(0,0,0,0) if transparent else (*color,255))
        if transparent:
            picture.paste((*color,255),(8,8,22,22))
        picture.save(output,format='PNG')
        return output.getvalue()
    source.routes['/cover.png']=(200,'image/png',png((20,30,240),True))
    source.routes['/emoji.png']=(200,'image/png',png((0,230,30)))
    item=dynamic('今晚见[本次表情]')
    item['media']=[{'kind':'video','url':source.url+'/cover.png'},
                   {'kind':'emoji','label':'[本次表情]','url':source.url+'/emoji.png'}]
    source.json('/api/search',{'items':[item],'total':1,'nextCursor':None,'prevCursor':None})
    async with PluginTest(PACKAGE,config=config(source,remind_minutes=0)) as bot:
        await bot.tool('asoul_send_card',{'request':{'action':'dynamic','dynamic_id':'1','include_images':False}})
        card,link=bot.deliveries[-1].parts
        assert '[本次表情]' in card.description
        picture=Picture.open(BytesIO(card.data)).convert('RGB')
        colors=dict((color,count) for count,color in picture.getcolors(picture.width*picture.height))
        assert colors.get((0,230,30),0)>50 and colors.get((20,30,240),0)>100
        assert colors.get((0,0,0),0)==0
        assert isinstance(link,Text)


@pytest.mark.asyncio
async def test_api_rate_limit_is_reported_to_the_invoking_user(source):
    source.json('/api/on-this-day',{'error':'rate limited'},status=429)
    async with PluginTest(PACKAGE,config=config(source,remind_minutes=0)) as bot:
        with pytest.raises(RuntimeError,match='请求较频繁'):
            await bot.message('/历史上的今天')
        assert bot.deliveries[-1].text=='请求较频繁，请稍后重试。'
