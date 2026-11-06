# 收藏与联机功能建议

状态：讨论稿。账号与收藏同步方案见 [统一账号设计](UNIFIED_ACCOUNT_DESIGN.md)。以下功能为待实施建议。

## 产品目标

把桌宠响应输入、抽取收藏、房间同桌这三块连起来：收藏能装备到桌面，伙伴能看见和回应，联机有几秒到几分钟即可参与的小活动。

优先利用已有立绘、475 个收藏表情和 36 段动态卡视频。首轮工作集中在展示与互动；新增美术按具体功能补充。

## WuwaTappoNative 调研

源码快照：[DanielToyama/WuwaTappoNative @ c417eb1](https://github.com/DanielToyama/WuwaTappoNative/tree/c417eb1e26c2ab2ee863f9a2f6f76c15e4f9ddc1)。核对了 README、账号会话、成员状态、桌宠排布、采集窗口、快捷键、输入和更新模块；功能判断以该快照为准。

它是连接库洛官方服务的 Windows 客户端，未提供可直接复用的自建账号后端。对本项目更有价值的是桌宠的桌面使用体验和客户端会话组织。

| 可参考的工作 | 源码依据 | 本项目现状与建议 | 优先级 |
| --- | --- | --- | --- |
| 单独显示或隐藏某位伙伴 | [RoomManager.cs](https://github.com/DanielToyama/WuwaTappoNative/blob/c417eb1e26c2ab2ee863f9a2f6f76c15e4f9ddc1/src/Net/RoomManager.cs)、[StateStore.cs](https://github.com/DanielToyama/WuwaTappoNative/blob/c417eb1e26c2ab2ee863f9a2f6f76c15e4f9ddc1/src/Core/StateStore.cs) | 已有房间内稳定成员键与位置记忆；增加本地可见性开关 | 高 |
| 按可见区域排列、横排/竖排、容忍少量重叠 | [PetWindow.cs](https://github.com/DanielToyama/WuwaTappoNative/blob/c417eb1e26c2ab2ee863f9a2f6f76c15e4f9ddc1/src/Pet/PetWindow.cs#L1277) | 已有 nextSlot 与整理位置功能；补方向选择、可见内容边界和保存位置冲突处理 | 高 |
| 可配置快捷键与表情槽位动作 | [Hotkeys.cs](https://github.com/DanielToyama/WuwaTappoNative/blob/c417eb1e26c2ab2ee863f9a2f6f76c15e4f9ddc1/src/Core/Hotkeys.cs) | 将显示/隐藏、穿透、打开面板、发常用表情绑定现有动作 | 高 |
| 单实例与再次启动唤起面板 | [SingleInstance.cs](https://github.com/DanielToyama/WuwaTappoNative/blob/c417eb1e26c2ab2ee863f9a2f6f76c15e4f9ddc1/src/Core/SingleInstance.cs) | 桌宠持续后台运行，重复启动时唤起已有实例最符合使用场景 | 高 |
| 独立 OBS 采集窗口 | [CaptureWindow.cs](https://github.com/DanielToyama/WuwaTappoNative/blob/c417eb1e26c2ab2ee863f9a2f6f76c15e4f9ddc1/src/Pet/CaptureWindow.cs) | 新建可采集的正常窗口，复用 PetView，独立尺寸与背景色；适合直播与录屏 | 中 |
| 贴边、悬停淡出、游戏进程触发穿透 | [PetWindow.cs](https://github.com/DanielToyama/WuwaTappoNative/blob/c417eb1e26c2ab2ee863f9a2f6f76c15e4f9ddc1/src/Pet/PetWindow.cs#L602)、[GameModeRules.cs](https://github.com/DanielToyama/WuwaTappoNative/blob/c417eb1e26c2ab2ee863f9a2f6f76c15e4f9ddc1/src/Core/GameModeRules.cs) | 先补手动贴边和悬停效果，再按实际需求接进程规则 | 中 |
| 更新说明集中展示 | [UpdateChecker.cs](https://github.com/DanielToyama/WuwaTappoNative/blob/c417eb1e26c2ab2ee863f9a2f6f76c15e4f9ddc1/src/Core/UpdateChecker.cs) | 设置页检查 Release，展示版本变化与下载入口 | 中 |
| 登录切换时替换完整客户端会话 | [AuthService.cs](https://github.com/DanielToyama/WuwaTappoNative/blob/c417eb1e26c2ab2ee863f9a2f6f76c15e4f9ddc1/src/Net/AuthService.cs#L48) | 已有服务端切换代次；接统一账号时增加账号维度，固定活动批次归属 | 账号接入时 |
| 可重复运行的多人动作压测入口 | [App.cs](https://github.com/DanielToyama/WuwaTappoNative/blob/c417eb1e26c2ab2ee863f9a2f6f76c15e4f9ddc1/src/App.cs) | 对当前 20 人上限测试动作、表情与展示效果叠加时的渲染成本 | 相关功能完成时 |

源码采用[自定义授权](https://github.com/DanielToyama/WuwaTappoNative/blob/c417eb1e26c2ab2ee863f9a2f6f76c15e4f9ddc1/LICENSE)；本计划参考交互与实现思路，在 Tauri / Vue / FastAPI 内独立实现。

现有项目已经具备双窗口、动作合批、远端点击边沿、位置记忆和按需视频播放。新增工作基于这些能力展开。WuwaTappoNative 的官方登录继承、输入键位显示和自动敲击属于它的特定产品路线，当前计划聚焦自营统一账号、收藏展示和房间互动。

## 大隐藏的用途

### 当前缺口

本项目有 10 张大隐藏，全部具备本地动态视频，包括蝶影共醉、绘心物语、巡梦漫游、歌剧之星、月下童话等。CardDetail 支持查看与播放，但没有装备入口；房间成员模型主要同步角色、昵称和动作。卡池预览也能看动态卡面，因此拥有后的专属使用场景不足。

目标是让拥有者在日常桌面中使用收藏，并让同桌伙伴看到、点开和回应。

### 首轮：展示卡与收藏特效

1. **所有已拥有卡可装备为展示卡，每人一张。** 桌宠旁显示小卡座，联机成员列表显示相同收藏。卡座常态使用静态缩略图，点击后在面板播放动态详情。桌面显示可由用户开关。
2. **装备大隐藏时启用对应收藏特效。** 名牌与卡座采用该卡的应援色、细节纹样和稀有标识；敲击连段达成时播放短促的系列粒子效果。使用一套可配置动画模板，避免十套独立特效资产成为首版前置。
3. **大隐藏解锁一次可主动触发的展示演出。** 房间内发起展示收藏，卡座短暂展开并播放静音片段，伙伴可以给出表情回应。自动入场演出作为独立可选项，加入房间默认先显示卡座。
4. **已有持有记录直接获得使用权。** 展示和特效根据现有 owned 判定，更新后即可装备，无需额外领取物品。
5. **重复大隐藏先沿用累计持有数。** 展示详情显示收藏数量；重复兑换或返碎片另列经济调整，先把首次获得的实际用途做完整。

首轮奖励定位为长期可用的展示外观。联机活动由所有成员参与，收藏决定展现形式。

### 后续可扩展的用途

- **个人主页主视觉**：选择已拥有的大隐藏，打开背包时使用对应动态背景；关闭动画时显示静态卡面。
- **房间合影装饰**：将装备的卡面、卡座与昵称一起排入同桌合影。
- **系列收藏纪念**：集齐系列后解锁对应名牌样式，沿用已拥有条目判断。
- **自选场景**：将现有主题素材与收藏关联。先确定要展示的具体部件，再接入装备。

### 最小实现改动

- loadout 增加可空的 showcaseCard；服务端核对卡片存在与持有状态。
- Member 与 state 增加经过服务端确认的展示卡 ID；详情由客户端 manifest 解析。
- 客户端新增卡座组件，与 PetView、成员列表、卡片详情共用同一装备状态。
- 系列颜色与特效模板按卡片元数据配置；动画在触发时运行，静态展示使用现有缩略图。
- 发起收藏展示时广播卡 ID、发起者与事件 ID，各客户端按自己的桌面布局播放。客户端版本缺少该卡时显示已知成员信息。

## 联机小功能候选

| 功能 | 一次玩法 | 能复用什么 | 新增状态 | 建议顺序 |
| --- | --- | --- | --- | --- |
| 戳一戳 | 点击伙伴，双方角色弹一下，显示 `某某戳了戳你`，对方可回戳 | PetActor 已有未拖动点击 poke 事件，但远端节点尚未接入；现有气泡与房间广播 | 发起者、目标、事件 ID、短冷却 | 第一批 |
| 看收藏 / 表情回应 | 点伙伴卡座看其装备卡，发一个喜欢的表情回应 | 展示卡、CardDetail、表情播放 | 收藏展示事件和回应目标 | 第一批 |
| 应援接力 | 一人发起，10 秒内 2–3 位不同成员点应援，共同触发短彩带 | 常用表情、应援色、房间名单 | 活动 ID、截止时间、参与成员集合 | 第二批 |
| 同桌合影 | 选择房间成员，生成一张带昵称、皮肤、展示卡的合影图 | RoomStage、立绘、卡面 | 本地合影选项 | 第二批 |
| 同桌专注钟 | 发起 25 分钟专注，成员自行加入，结束时角色一起庆祝 | 心跳、在线状态、表情 | 活动 ID、服务端起止时间、参加者 | 后续 |
| 默契选表情 | 自愿加入两人局，各选一个表情，双方提交后一起揭晓是否相同 | 已有表情图与选择器 | 局 ID、双方选择、截止时间 | 后续 |

首轮最合适的是展示卡、戳一戳、看收藏这三项。玩家进入同一房间后，马上就能看见收藏、点击互动并获得回应。应援接力适合第二轮，作为房间内的共同动作。

### 房间设计上的实际约束

- 伙伴位置目前只在各客户端本地保存。互动消息按成员 ID 定位，接收端在自己的布局中画动画；合影使用本机 RoomStage 的独立排列。
- 戳一戳区分拖动和点击，命中现有 data-hit 区域；穿透模式沿用当前快捷键或托盘入口。
- 短冷却按发起者实施，房间活动按不同成员计参与；用户可以隐藏伙伴、关闭互动提示和视觉特效。
- 定时玩法由服务端给出起止时间，重连读取当前活动快照。成员离开、取消或到期后结束对应活动。
- 收藏展示由服务端确认拥有；卡面视频仍从本地播放，WebSocket 只发送事件和卡 ID。
- 首轮活动只产生即时反馈与合影。未来若增加碎片奖励，再定义活动结算与领取规则。

## 建议实施批次

| 批次 | 内容 | 完成后的可见结果 |
| --- | --- | --- |
| A：账号基础 | 桌宠存档码；主站授权码登录、桌宠存档绑定、收藏同步接口，按[统一账号方案](UNIFIED_ACCOUNT_DESIGN.md)第 5 节的顺序实施 | 换电脑能恢复存档，三端用同一个主站账号 |
| B：收藏有用途 | 展示卡装备、卡座、名牌/连段特效、伙伴详情 | 抽到大隐藏后可在桌面与房间中使用 |
| C：轻互动 | 戳一戳、表情回应、单成员隐藏、快捷键 | 联机从看动作增加到直接互动 |
| D：一起做一件事 | 应援接力、同桌合影 | 房间内有可共同完成的小活动 |
| E：使用体验 | 自动排列方向、贴边、OBS 窗口、更新入口 | 桌宠更适合长期挂着、直播与分享 |

B、C 和 A 并行开发。桌宠服务端统一按解析出的玩家 ID 处理请求，游客和账号登录共用同一套库存逻辑。

## 后续设计落点

本仓库保留本稿与统一账号方案。主站按自身文档结构记录实施项；Asasfans 的计划写入其 docs/next.md，遵循该仓库现有约定。

