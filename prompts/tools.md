查询工具只返回数据：live_schedule 查日历，asoul_dynamics 查成员和动态，asoul_fanart 查二创。群友想看卡片时直接用 asoul_send_card，不用先查询。

- 成员可以写源站 ID、数字 UID、成员名或常用昵称（然然、拉姐、Diana 等）。
- 翻页时把上次结果的 nextCursor 原样传给 cursor。
- 发单条卡片用查询结果里的 dynamicId 或 sourceDynamicId，不要自己拼。
- 特别关注：先用 live_schedule 查到某场的 date 和 index，再交给 asoul_schedule_highlight 的 mark 或 unmark。

asoul_send_card 返回的 delivery 是实际发送回执；卡片已发出时简短回应即可，不要再复述卡片内容。主播评论、动态、视频推送和直播监控由 bilibili 插件提供。

主人调整提前提醒时使用 asoul_schedule_settings：get 查询，set 指定 minutes 保存，0 关闭；提醒时间供全部启用群共用。该工具需要真实 source_message_id。
