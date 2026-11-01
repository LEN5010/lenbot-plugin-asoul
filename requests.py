"""Business requests for the model tools; each action accepts only its own fields."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

MEMBER = '成员：源站 member ID、数字 UID、成员名或常用昵称（然然、拉姐、Diana 等）；省略不限制'


class Request(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')


class MembersQuery(Request):
    action: Literal['members']


class DynamicQuery(Request):
    action: Literal['search']
    query: Annotated[str, Field(description='全文关键词；空文本按排序列出动态')] = ''
    member: Annotated[str | None, Field(description=MEMBER, examples=['uid:672328094', '嘉然', '然然'])] = None
    dynamic_type: Annotated[Literal['text', 'image', 'video', 'forward', 'article', 'live', 'other'] | None, Field(description='按源站动态类型筛选；省略不限制')] = None
    start: Annotated[str | None, Field(description='发布时间起点，ISO 8601 含时区', examples=['2026-10-01T00:00:00+08:00'])] = None
    end: Annotated[str | None, Field(description='发布时间终点，ISO 8601 含时区', examples=['2026-10-31T23:59:59+08:00'])] = None
    sort: Annotated[Literal['newest', 'oldest', 'likes', 'comments'], Field(description='newest 最新、oldest 最早、likes 点赞最多、comments 评论最多')] = 'newest'
    limit: Annotated[int, Field(description='抽取条数', ge=1, le=100)] = 10
    cursor: Annotated[str | None, Field(description='翻页时传上次结果的 nextCursor，原样传递')] = None


class DynamicRead(Request):
    action: Literal['read']
    dynamic_id: Annotated[str, Field(description='查询结果里的 dynamicId，原样传递')]
    member: Annotated[str | None, Field(description='动态所属成员，用于核对归属；省略不核对')] = None


class HistoricalQuery(Request):
    action: Literal['history']
    month_day: Annotated[str | None, Field(description='月日 MM-DD；省略为今天', examples=['08-16'])] = None
    sort: Annotated[Literal['hot', 'likes', 'comments'], Field(description='hot 综合热度、likes 点赞最多、comments 评论最多')] = 'hot'
    limit: Annotated[int, Field(description='最多条数', ge=1, le=100)] = 8


class FanartQuery(Request):
    action: Literal['search']
    query: Annotated[str, Field(description='关键词，匹配正文和标签；空文本不筛选')] = ''
    character: Annotated[str | None, Field(description='角色：贝拉、嘉然、乃琳、心宜&思诺，多个用逗号分隔；省略不筛选')] = None
    content_type: Annotated[Literal['all', 'image', 'video', 'text', 'other'], Field(description='image 图片、video 视频、text 文字、other 其他；all 不筛选')] = 'all'
    kind: Annotated[Literal['all', 'fanart', 'material'], Field(description='fanart 二创、material 官方物料；all 两者都要')] = 'fanart'
    category: Annotated[str, Field(description='源站分类；all 不筛选')] = 'all'
    source: Annotated[Literal['all', 'bilibili', 'douban'], Field(description='来源平台 bilibili 或 douban；all 不筛选')] = 'all'
    sort: Annotated[Literal['newest', 'oldest', 'views', 'favorites'], Field(description='newest 最新、oldest 最早、views 播放最多、favorites 收藏最多')] = 'newest'
    limit: Annotated[int, Field(description='抽取条数', ge=1, le=100)] = 10
    cursor: Annotated[str | None, Field(description='翻页时传上次结果的 nextCursor，原样传递')] = None


class RandomFanart(Request):
    action: Literal['random']
    query: Annotated[str, Field(description='关键词，匹配正文和标签；空文本不筛选')] = ''
    character: Annotated[str | None, Field(description='角色：贝拉、嘉然、乃琳、心宜&思诺，多个用逗号分隔；省略不筛选')] = None
    content_type: Annotated[Literal['all', 'image', 'video', 'text', 'other'], Field(description='image 图片、video 视频、text 文字、other 其他；all 不筛选')] = 'all'
    kind: Annotated[Literal['all', 'fanart', 'material'], Field(description='fanart 二创、material 官方物料；all 两者都要')] = 'fanart'
    category: Annotated[str, Field(description='源站分类；all 不筛选')] = 'all'
    source: Annotated[Literal['all', 'bilibili', 'douban'], Field(description='来源平台 bilibili 或 douban；all 不筛选')] = 'all'
    limit: Annotated[int, Field(description='抽取条数', ge=1, le=100)] = 1


class DynamicCard(Request):
    action: Literal['dynamic']
    dynamic_id: Annotated[str, Field(description='查询结果里的 dynamicId，原样传递')]
    member: Annotated[str | None, Field(description='动态所属成员，用于核对归属；省略不核对')] = None
    include_images: Annotated[bool, Field(description='卡片之后再发原图；false 只发卡片和链接')] = True


class FanartCard(Request):
    action: Literal['fanart']
    source_dynamic_id: Annotated[str, Field(description='asoul_fanart 结果里的 sourceDynamicId，保留 bilibili: 或 douban: 前缀')]
    include_images: Annotated[bool, Field(description='卡片之后再发原图；false 只发卡片和链接')] = True


DynamicsRequest = Annotated[MembersQuery | DynamicQuery | DynamicRead | HistoricalQuery, Field(discriminator='action')]
FanartRequest = Annotated[FanartQuery | RandomFanart, Field(discriminator='action')]


class HistoryCard(Request):
    action: Literal['history']
    month_day: Annotated[str | None, Field(description='月日 MM-DD；省略为今天', examples=['08-16'])] = None
    sort: Annotated[Literal['hot','likes','comments'], Field(description='hot 综合热度、likes 点赞最多、comments 评论最多')] = 'hot'
    limit: Annotated[int, Field(description='卡片展示条数',ge=1,le=20)] = 3


class DynamicSearchCard(DynamicQuery):
    action: Literal['dynamic_search']


class FanartSearchCard(FanartQuery):
    action: Literal['fanart_search']


class RandomFanartCard(RandomFanart):
    action: Literal['random_fanart']


class ScheduleCard(Request):
    action: Literal['schedule']
    period: Annotated[Literal['today','tomorrow','week'], Field(description='today 今天、tomorrow 明天、week 本周（今天到周日）')] = 'today'
    exclude_filtered_hosts: Annotated[bool, Field(description='去掉心宜和思诺的场次，同聊天命令的 -a')] = False


class HighlightList(Request):
    action: Literal['list']


class HighlightMark(Request):
    action: Literal['mark']
    date: Annotated[str, Field(description='live_schedule 结果 items 里的 date（YYYY-MM-DD），也可写今天或明天')]
    index: Annotated[int, Field(description='live_schedule 结果 items 里同一 date 的 index',ge=1)]
    style: Annotated[Literal['pink','red','platinum'],Field(description='高亮颜色：pink 粉色、red 红色、platinum 白金色')] = 'platinum'


class HighlightUnmark(Request):
    action: Literal['unmark']
    date: Annotated[str, Field(description='live_schedule 结果 items 里的 date（YYYY-MM-DD），也可写今天或明天')]
    index: Annotated[int, Field(description='live_schedule 结果 items 里同一 date 的 index',ge=1)]


class HighlightRemove(Request):
    action: Literal['remove']
    index: Annotated[int, Field(description='list 结果 records 里的 index',ge=1)]


CardRequest = Annotated[DynamicCard | FanartCard | HistoryCard | DynamicSearchCard | FanartSearchCard | RandomFanartCard | ScheduleCard, Field(discriminator='action')]
HighlightRequest = Annotated[HighlightList | HighlightMark | HighlightUnmark | HighlightRemove, Field(discriminator='action')]
