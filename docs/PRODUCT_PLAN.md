# 收藏与联机功能建议

状态：讨论稿。账号与收藏同步方案见 [统一账号设计](UNIFIED_ACCOUNT_DESIGN.md)。以下功能为待实施建议。

## 产品目标

把桌宠响应输入、抽取收藏、房间同桌这三块连起来：收藏能装备到桌面，伙伴能看见和回应，联机有几秒到几分钟即可参与的小活动。

优先利用已有立绘、475 个收藏表情和 33 段动态卡视频。首轮工作集中在展示与互动；新增美术按具体功能补充。

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

## 大隐藏的用途：铭牌

本项目有 10 张大隐藏，全部具备本地动态视频。传说档只在未拥有的卡里抽，大隐藏不会重复，平均约 173 抽才出一张，适合做成给别人看的身份标识。

已实现的铭牌：

- 玩家在背包的铭牌分类里，从已解锁的铭牌中选一张使用，也可以不使用。点铭牌先打开预览，显示卡面、解锁进度和自己的桌宠戴上它的样子。
- 解锁条件（1.1.0 起）：大隐藏加上它所在收藏集里该成员的全部卡片。几位成员共用的收藏集只要求该成员的卡，双人卡要求整个双人收藏集。只有大隐藏的旧存档不再保留铭牌。
- 铭牌显示在其他成员桌面上该玩家桌宠的下方，替换普通名牌；联机页的座位仍显示普通名牌。
- 铭牌取卡面眼睛所在的一条横条，眼睛位于从左往右约 70% 处，镶金框，一直播放卡面视频。昵称用白字压在左侧的暗色渐变上，名字越长，暗色渐变越宽。
- 卡面视频与静态卡图构图不同，部分卡的视频单独标定裁切位置。巡梦漫游有心宜和思诺两张脸，横条在两张脸之间上下移动。
- 同一张卡只解码一个视频，所有戴着这张卡的铭牌共用画面。系统开启减少动态效果时显示静态卡面。
- 联机页的同桌显示里可以关闭伙伴铭牌，关闭后显示普通名牌。
- 服务端在保存装备、加入房间和更换铭牌时核对存档是否集齐。

不做全服编号、彩虹闪膜和敲击连段时的特殊动画。

## 联机小功能候选

| 功能 | 一次玩法 | 能复用什么 | 新增状态 | 建议顺序 |
| --- | --- | --- | --- | --- |
| 戳一戳 | 点击伙伴，双方角色弹一下，显示 `某某戳了戳你`，对方可回戳 | PetActor 已有未拖动点击 poke 事件，但远端节点尚未接入；现有气泡与房间广播 | 发起者、目标、事件 ID、短冷却 | 第一批 |
| 看收藏 / 表情回应 | 点伙伴铭牌看对应的卡，发一个喜欢的表情回应 | 铭牌、CardDetail、表情播放 | 收藏展示事件和回应目标 | 第一批 |
| 应援接力 | 一人发起，10 秒内 2–3 位不同成员点应援，共同触发短彩带 | 常用表情、应援色、房间名单 | 活动 ID、截止时间、参与成员集合 | 第二批 |
| 同桌合影 | 选择房间成员，生成一张带昵称、皮肤、铭牌的合影图 | RoomStage、立绘、卡面 | 本地合影选项 | 第二批 |
| 同桌专注钟 | 发起 25 分钟专注，成员自行加入，结束时角色一起庆祝 | 心跳、在线状态、表情 | 活动 ID、服务端起止时间、参加者 | 后续 |
| 默契选表情 | 自愿加入两人局，各选一个表情，双方提交后一起揭晓是否相同 | 已有表情图与选择器 | 局 ID、双方选择、截止时间 | 后续 |

铭牌已经完成，下一步最合适的是戳一戳和看收藏。玩家进入同一房间后，马上就能看见收藏、点击互动并获得回应。应援接力适合第二轮，作为房间内的共同动作。

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
| B：收藏有用途 | 大隐藏铭牌（已完成）、伙伴详情 | 抽到大隐藏后能挂在伙伴桌面的桌宠下面 |
| C：轻互动 | 戳一戳、表情回应、单成员隐藏、快捷键 | 联机从看动作增加到直接互动 |
| D：一起做一件事 | 应援接力、同桌合影 | 房间内有可共同完成的小活动 |
| E：使用体验 | 自动排列方向、贴边、OBS 窗口、更新入口 | 桌宠更适合长期挂着、直播与分享 |

B、C 和 A 并行开发。桌宠服务端统一按解析出的玩家 ID 处理请求，游客和账号登录共用同一套库存逻辑。

## 后续设计落点

本仓库保留本稿与统一账号方案。主站按自身文档结构记录实施项；Asasfans 的计划写入其 docs/next.md，遵循该仓库现有约定。

