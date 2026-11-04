# A-SOUL 日程与动态

LenBot 插件接口 1，插件名 `asoul`。迁移自 LEN5010 的 [枝江自动推送](https://github.com/LEN5010/astrbot_plugin_asoul)中 A-SOUL 日程部分，以及[动态查询站插件](https://github.com/LEN5010/astrbot_plugin_dynamic_asoul)。日程、历史动态和二创在本插件中提供；主播评论与回复、动态、视频和直播状态监控由 `bilibili` 插件提供。

## 安装

在面板「插件」填写 `https://github.com/LEN5010/lenbot-plugin-asoul`，或导入发布 ZIP，应用后选择启用的群。

```json
{
  "owners": ["onebot:70001"],
  "plugins": {"asoul": {}},
  "scenes": {"onebot:group:10001": {"plugins": ["asoul"]}}
}
```

日历默认来自 `https://asoul.love/calendar.ics`，动态站默认来自 `https://len5010.top/dynamics/api`。

## 聊天命令

| 命令 | 行为 |
|---|---|
| `今日直播`、`明日直播`、`本周直播` | 发送当天、明天或本周剩余日程；支持 `/` 前缀 |
| `今日直播 -a`、`明日直播 -a`、`本周直播 -a` | 筛除心宜和思诺，联合节目保留其余成员 |
| `/日程`、`/日程 明天`、`/日程 本周` | 日程快捷命令，同样支持 `-a` |
| `/日程高亮 日期` | 主人列出当天节目序号 |
| `/日程高亮 日期 序号 [粉色\|红色\|白金色]` | 主人标记全局特别关注，默认白金色 |
| `/取消日程高亮 日期 序号` | 主人取消节目高亮 |
| `/日程高亮列表` | 主人列出全部保存记录 |
| `/取消日程高亮记录 序号` | 主人删除列表中的记录，适用于已从日历消失的节目 |
| `/历史上的今天 [MM-DD] [条数]`、`/那年今日 ...` | 默认 3 条往年同日动态；日期支持 `8-16`、`8/16`、`8月16日` |
| `历史上的今天`、`那年今日` | 纯文本触发今日历史动态卡片 |
| `/随机二创 [角色] [分类/类型]`、`/二创 ...` | 随机发送一条二创卡片 |
| `/随机图片二创 [角色]`、`/随机视频二创 [角色]` | 固定图片或视频类型 |
| `/二创搜索 关键词 [角色]`、`/搜二创 ...` | 搜索二创与物料 |
| `/搜动态 关键词 [成员] [排序]`、`/动态搜索 ...` | 搜索历史动态，排序支持 newest、oldest、likes、comments |

常用昵称包括然然、拉姐、队长、奶琳、晚晚及 Diana、Bella、Eileen 等。二创角色支持嘉然、贝拉、乃琳、心宜&思诺；分类支持普通、物料、手书、动画、剪辑、AMV、MMD、3D 等上游别名。

日程按上游规则合并同时间、同内容节目；A-SOUL 团体展开为嘉然、乃琳、贝拉。本周从今天显示至周日；周日查询明日返回「还没有下周的直播排表哦」。聊天命令使用 `calendar_timezone`，默认北京时间。高亮全局保存，由 LenBot `owners` 管理，对应原插件的管理员操作；已有高亮记录继续可读。

Telegram 使用中文命令和纯文本触发时，在 BotFather `/setprivacy` 关闭隐私模式或将机器人设为管理员。

## 主 Agent 工具

插件启用后，这五个工具由宿主注册，并带有简介、类型参数和共享指南。角色 `tools` 使用明确名单时，放行下列名称及 `tool_search`；使用 `all` 时按宿主统一发现。

| 工具 | 操作 |
|---|---|
| `live_schedule` | 按日期查询日历；`items` 给出合并后的日程及当天序号，`events` 保留原始条目 |
| `asoul_dynamics` | request.action 为 members、search、read、history |
| `asoul_fanart` | request.action 为 search、random，支持角色、类型、分类和来源 |
| `asoul_send_card` | request.action 为 schedule、history、random_fanart、dynamic_search、fanart_search、dynamic、fanart |
| `asoul_schedule_highlight` | 主人通过真实 `source_message_id` 执行 list、mark、unmark、remove |

示例业务参数：

```json
{"request": {"action": "history", "month_day": "08-16", "limit": 3}}
```

```json
{"request": {"action": "random_fanart", "character": "嘉然", "content_type": "video", "category": "剪辑·AMV"}}
```

```json
{"request": {"action": "schedule", "period": "week", "exclude_filtered_hosts": true}}
```

查询工具返回数据与来源；发送工具通过当前群出口交付卡片，并返回实际 `delivery` 回执。`live_schedule` 的日期按当前群时区解释；高亮使用其 `items.date/index`。

## 卡片与配置

卡片与 B 站推送卡片同一套样式：白底、粉色细线和粉色标题。日程展示成员表情、节目类型、开播时间、特别关注与取消状态，成员名前有代表色圆点；动态和二创展示头像、正文、转发原文、封面/图片、内联 B 站表情、公开互动统计、原文链接和二维码。长文卡片自动分页，搜索卡片展示正文摘要。

| 配置 | 默认值 | 用途 |
|---|---|---|
| `card_mode` | image | 日程图片或文字 |
| `calendar_timezone` | Asia/Shanghai | 日历与聊天日期时区 |
| `calendar_cache_seconds` | 1800 | 日历缓存秒数 |
| `remind_minutes` | 10 | 开播前向场景发日历事件；0 关闭 |
| `on_this_day_default_limit` | 3 | 历史同日默认条数 |
| `default_search_limit` | 5 | 搜索命令默认条数 |
| `on_this_day_cache_minutes` | 30 | 历史同日缓存分钟数 |
| `render_cards` | true | 动态站命令图片或正文输出 |
| `dynamics_cache_seconds` | 120 | 普通查询缓存；随机查询每次取样 |
| `request_timeout_seconds` | 15 | 单次 HTTP 超时 |

默认日历读取 ICS。高亮按节目身份保存在插件 KV；旧 UID 高亮继续匹配。开播前事件的已提醒条目保存在 `reminded.json`。

## 开发与验证

运行依赖 `qrcode>=8.2,<9`，Pillow、httpx、regex 使用宿主依赖。在与 LenBot 同级的目录内运行：

```sh
uv pip install --python ../LenBot/.venv/bin/python 'qrcode>=8.2,<9'
uv run --project ../LenBot --no-sync pytest -q
```

测试通过实际 `PluginTest` 匹配器、模型工具分派器、KV 和模拟发送出口，覆盖上游命令、昵称、筛选、高亮持久化、卡片与主 Agent 调用。`PluginTest.preview_tools()` 可查看工具参数、说明与可用性。

打包：`uv run --no-project --python 3.13 python ../LenBot/scripts/package_plugin.py . /tmp/asoul.zip`。新运行文件和素材加入 Git 后打包。

来源与素材见 [SOURCE.md](SOURCE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。许可证为 GNU AGPL v3 或更新版本。

## 在聊天中调整提醒

需要 LenBot 0.2.1。主人可以让 Bot 提前五分钟提醒、关闭开播提醒，或查看当前设置。`asoul_schedule_settings` 使用 `action=get` 查询，`action=set, minutes=5` 保存，`minutes=0` 关闭。提醒时间供全部启用插件的群共用。角色工具名单加入 `asoul_schedule_settings` 并保留 `tool_search`。单场特别关注仍用 `asoul_schedule_highlight`，先由 `live_schedule` 取得日期和序号。
