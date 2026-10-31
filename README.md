# lenbot-plugin-asoul

LenBot 插件接口 1 的 A-SOUL 合集，插件名 `asoul`。包含两部分：

- **日程**：读取一个 ICS 日历（默认枝江站 `https://asoul.love/calendar.ics`），`/日程` 命令和「今日直播」全文直接发日程卡片，可以把某场设为特别关注，`live_schedule` 工具按日期查询，开播前向启用的群发场景事件。
- **动态**：访问 A-SOUL 动态查询站（默认 `https://len5010.top/dynamics/api`）的公开接口，查询成员、动态、历史同日和二创，并能把正文卡片和来源原图发到本群。

## 安装

在 LenBot 面板「插件」填写本仓库的 Git 地址，或导入发布页的 ZIP，应用后配置参数并选择启用的群。也可以把仓库目录直接放进实例的 `plugins/`。

根配置的局部示例（不要覆盖完整根配置）：

```json
{
  "plugins": {
    "asoul": {
      "live_keywords": ["直播"]
    }
  },
  "scenes": {"onebot:group:10001": {"plugins": ["asoul"]}}
}
```

角色 `tools` 还需放行相应工具及 `tool_search`。

### 从旧的两个独立插件迁移

旧插件 `asoul_calendar` 与 `asoul_dynamics` 合并为 `asoul`，命令和工具名不变：

| 旧字段 | 新字段 |
|---|---|
| `asoul_calendar.source_url` | `calendar_url` |
| `asoul_calendar.cache_seconds` | `calendar_cache_seconds` |
| `asoul_calendar.user_agent` | `calendar_user_agent` |
| `asoul_dynamics.api_base_url` | `dynamics_api_url` |
| `asoul_dynamics.cache_seconds` | `dynamics_cache_seconds` |
| 两者的 `request_timeout_seconds` | 共用同名字段 |
| 两者的 `card_font` | 删除，卡片改用随插件分发的字体 |

其余日程字段（`calendar_timezone`、`live_keywords`、`non_live_keywords`、`include_all_day`、`remind_minutes`、`card_mode`）名称不变。场景 `plugins` 列表里的旧名字换成 `asoul`。旧数据目录里只有 `asoul_calendar/reminded.json` 需要移到新插件数据目录 `asoul/`，不移也只会在重启后对即将开始的条目重新提醒一次。

## 日程

- `/日程`、`/日程 明天`、`/日程 本周`，以及全文「今日直播」：插件直接回复，不叫醒大脑。`card_mode=image`（默认）发日程卡片，`text` 发逐行列表。
- 卡片按天分组，每场显示时间、分类、成员和标题，配一张对应成员的表情；正在播的标「直播中」，取消的场次划掉保留。本周卡片用紧凑排版。
- 特别关注：`/日程高亮 日期` 列出当天各场的序号，`/日程高亮 日期 序号` 标记，`/取消日程高亮 日期 序号` 取消，`/日程高亮列表` 查看还没过去的。日期写 `今天`、`明天`、`后天`、`10-07` 或 `2026-10-07`。标记的场次在卡片上用品牌色高亮，记录按日历条目的 UID 存在插件 KV，开播一周后自动清掉。
- 低频工具 `live_schedule(start, days, member)`：大脑经 `tool_search` 发现后按日期查询，`member` 按日历原文包含的文字筛选，结果里带 `special_follow`。
- 后台每分钟检查一次，开播前 `remind_minutes` 分钟向启用的群发一条场景事件，由大脑决定要不要提醒大家；特别关注的场次会在事件里说明。已提醒的条目记在插件数据目录的 `reminded.json`，重启不重复提醒。`remind_minutes=0` 关闭提醒。

日历读取失败时回复「暂时没取到，稍后再试」，原始错误进面板的插件错误；当天没有条目时回复「暂无直播」。

## 动态

- `asoul_dynamics(request)`：action 为 members、search、read、history；最近动态用 search 并省略 query。member 可用源站 ID 或完整名称，按成员表精确匹配。nextCursor 原样续页。
- `asoul_fanart(request)`：action 为 search 或 random。搜索支持分页、来源和分类；随机查询每次重新请求，没有分页游标。
- `asoul_send_card(request)`：action 为 dynamic 或 fanart，各自要求来源 dynamicId／sourceDynamicId；include_images=false 只发正文与链接。

连同 `live_schedule` 共四项能力。每个操作的必填、可选字段由 requests.py 的类型分支说明；未知字段直接报错。查询与发送分开。

发卡片会重新查询源项，正文、转发原文、指标和媒体信息分页排版，长文完整保留。原图按来源顺序发送，保留 GIF，重复 URL 只发一次。全部内容准备好才开始发送；平台发送中途失败时停止，已确认的部分保留。返回的 `delivery` 是实际发送状态。

HTTP 请求直接连接源站，每次只发一次。成功的查询页最多缓存 16 页，缓存过期后请求失败就报错；源站返回的 409（快照已变化）原文返回。

## 字体与表情

卡片字体用随插件分发的更纱黑体（Sarasa Mono SC），缺字的符号回退到系统里的 Arial Unicode、DejaVu Sans 或 Noto 字体。日程卡片的成员表情放在 `assets/stickers/<成员名>/`，按日历描述里的主播名挑选，同一张卡片里尽量不重复；没有表情的成员不配图。加新成员只需新建同名目录放 WebP 图片。

## 开发

在与 LenBot 同级的目录里，用宿主的开发环境运行测试：

```sh
uv run --project ../LenBot --no-sync pytest -q
```

测试用本地 HTTP 服务模拟日历和动态站。

许可证：GNU AGPL v3 或更新版本，见 [LICENSE](LICENSE)；来源说明见 [SOURCE.md](SOURCE.md)。查询和转发的内容版权归原作者。

## 工具接口

工具采用接口 1 的显式简介、Field 参数说明与 `prompts/tools.md` 共享指南，返回原生 JSON 或文本。用 `PluginTest.preview_tools()` 查看模型说明、参数与可用性；测试里模型服务默认关闭。兼容和更新事项见 [CHANGELOG](CHANGELOG.md)。

CI 调用 LenBot 的可复用工作流，跟随宿主 master 测试。catalog-entry.json 记录目录条目的安装来源。

本机生成 ZIP（LenBot 仓库与本仓库放在同一目录下）：`uv run --no-project --python 3.13 python ../LenBot/scripts/package_plugin.py . /tmp/plugin.zip`。打包取 Git 已跟踪的运行源码和资源，新增文件需先加入 Git。

## 宿主能力

清单声明 `send`、`events`。这些权限约束宿主提供的能力，插件自行执行的 Python 与网络访问不受其约束。插件运行在宿主进程中，当前功能使用工具或后台协程，`isolation = "inline"`。
