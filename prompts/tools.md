live_schedule 查日历。
asoul_dynamics 的 request.action：members 列成员，search 查最近或关键词动态，read 读真实 dynamicId，history 查往年今日。member 可填源站 ID 或完整名称；名称按源列表精确匹配。翻页原样传 nextCursor。
asoul_fanart 搜索或随机二创；asoul_send_card 用返回的 dynamicId/sourceDynamicId 重新读取并发送，保留来源前缀。查询返回数据和来源；发送结果看 delivery 回执，sent 是送达，simulated/partial/unconfirmed/failed 按原状态说明，不用再发一遍。
