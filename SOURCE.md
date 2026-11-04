# 来源

## A-SOUL 日程

- 上游：[LEN5010/astrbot_plugin_asoul](https://github.com/LEN5010/astrbot_plugin_asoul)，提交 `5a945f695ecaa434ff71d402a344f8e9e40feab0`。
- `schedule_logic.py` 移植 `asoul_schedule.py` 的节目合并、成员识别、内容提取和分类规则。
- `schedule.py` 迁移今日/明日/本周、`-a` 成员筛选、多色全局特别关注和保存记录删除；节目身份沿用上游的日期、内容、分类哈希。管理员操作映射至 LenBot `owners`。
- `ics.py` 的折行、转义与日期解析沿用同一上游及 LenBot 既有日历实现。
- 主播评论与回复、动态、视频和直播监控由独立的 `lenbot-plugin-bilibili` 承接。

## 动态查询站

- 上游：[LEN5010/astrbot_plugin_dynamic_asoul](https://github.com/LEN5010/astrbot_plugin_dynamic_asoul)，提交 `7ccd9007b12d3cabdd174d7a53fefefd525ce4f8`。
- `commands.py` 迁移历史上的今天、随机二创、二创搜索、历史动态搜索及命令别名；`command_args.py` 移植成员昵称、角色、分类和内容类型筛选。
- `client.py`、`models.py` 对接公开接口：https://len5010.top/dynamics/api 。详情查询保留源 ID 核对和分页语义。
- `assets/emojis.json` 来自该上游，渲染时优先使用接口返回的表情标签和地址。
- 2026-11-01 实际读取并核对默认日历、members、on-this-day、search、fanart 的公开响应。

## 卡片与素材

- 卡片样式来自仓库所有者的 `astrbot_plugin_asoul`：B 站卡片的 HTML 模板用 Pillow 重写，日程保留 `asoul_render.py` 的行布局和特别关注配色。`content_card.py`、`schedule_card.py` 使用 Pillow 和 `card_kit.py` 排版；`card_kit.py` 与 `lenbot-plugin-bilibili`、`lenbot-plugin-group-digest` 共用同一份，三个仓库一起修改。动态站原文、媒体、公开统计与二维码采用上游功能。
- `assets/NotoSansSC.ttf` 为 Google Fonts 分发的 Noto Sans SC 可变字重字体，按 SIL Open Font License 1.1 分发，许可证见 `assets/NotoSansSC-OFL.txt`。卡片按字重 400 至 900 取用。
- `assets/stickers/<成员名>/` 来自日程上游的成员表情，缩放至 160 像素并转换为 WebP。内容和素材的权利归各原权利人。
- 插件代码按 GNU AGPL v3 或更新版本分发，见 [LICENSE](LICENSE)。
