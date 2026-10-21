live_schedule 查日历。
asoul_dynamics 的 request.action：members 列成员，search 查最近或关键词动态，read 读真实 dynamicId，history 查往年今日。member 可填源站 ID 或完整名称；名称只按源列表精确匹配，不猜别名。翻页原样传 nextCursor。
asoul_fanart 搜索或随机二创；asoul_send_card 用返回的 dynamicId/sourceDynamicId 重新读取并发送，保留来源前缀。查询只返回数据和来源；发送以 delivery 回执为准，simulated/partial/unconfirmed/failed 不当作送达，不重复发。
