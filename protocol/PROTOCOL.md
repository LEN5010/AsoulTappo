# AsoulTappo 协议

## 身份与房间

HTTP 请求使用 `X-Player-Token`（16–128 字符）；客户端本地生成，服务端以 SHA-256 前 16 位标识玩家。`GET /healthz` 返回服务状态，`POST /rooms` 返回随机房间号。房间在首次加入时创建、最后一个成员离开时回收，最多 20 人。

WebSocket 地址为 `/ws`，每帧一个 JSON 对象。

| 客户端 type | 字段 |
|---|---|
| join | room（1–64）、nick（1–24）、character（≤32）、token（可选） |
| leave | 无 |
| tap | count（1–500），客户端每 100–200ms 合并 |
| emote | emote（≤32），图片表情 key 或 thumbup；初始表情免费，其余验证所有权 |
| state | character、nick，至少提供一个 |
| ping | 无 |

服务端消息：`joined {room,you,members}`、`member_joined {member}`、`member_left {id}`、`tap {id,count,total}`、`emote {id,emote}`、`state {id,character,nick}`、`pong`、`error {code,message}`。成员包含 `id,uid,nick,character,taps`。`uid = sha256(player_id + ':' + room)[:10]` 用于记录同桌位置。

表情服务端间隔 250ms，客户端间隔 400ms。每个成员的发送串行执行，2 秒超时后关闭慢连接。数据库所有权检查在线程池执行。客户端每 20 秒 ping，断线指数退避重连并重新加入。

## HTTP API

| 路由 | 请求与响应 |
|---|---|
| GET /api/manifest | 素材清单，与 assets-packs/manifest.json 一致 |
| GET /api/me | boxes、shards、progress、boxesToday、dailyCap、totals、pity、draw |
| POST /api/activity | `{taps,session,sequence}`，返回状态和 credited、newBoxes |
| POST /api/presence | `{session}`，记录运行心跳并返回状态 |
| POST /api/cards/draw | `{pool,count}`，count 为 1–100，返回状态和 drops |
| POST /api/boxes/open | `{count}`，每请求最多打开 10 箱，返回状态和 drops |
| POST /api/craft | `{item}`，兑换未拥有的非初始表情，返回状态和 item |
| GET /api/collection | owned（物品 ID → 数量）、recent（最近获得记录） |
| GET /api/loadout | character、favorites |
| POST /api/loadout | 更新 character 或 favorites（最多 8 个且拥有） |
| GET /packs/index.json | 素材文件路径、大小及 SHA-256 |
| GET /packs/... | 卡面原图、视频及动画资源 |

物品 ID 为 `card:<id>` 或 `emote:<key>`。`drops[]` 包含 `item,rarity,new,count,shards`，抽卡额外包含 `tier`（big / small / normal）。

## 在线时长与抽卡

`draw` 包含 `tickets,seconds,secondsPerDraw,pity,hardPity,total`。每个运行会话使用随机 session，启动时建立基线，每 20 秒心跳一次。相邻心跳间隔不超过 60 秒时按服务端实际时间累计；超过 60 秒重新建立基线。多客户端的重叠时间只累计一次。累计 900 秒获得一抽，剩余秒数、抽卡次数和保底保存在 SQLite；次数无积累上限。

每次先抽档位：大隐藏 0.5%、小隐藏 4.5%、普通 95%；然后在所选卡池的同档卡牌中等概率抽取。第 400 抽必出大隐藏，所有卡池共用计数，提前抽中也重置。重复卡累加收藏数量。库存扣除、掉落和保底更新在同一事务中完成。客户端“全部抽取”按最多 100 抽一批展示，收下后继续剩余次数。

## 活动与表情宝箱

活动批次的 session 为 16–128 字符，sequence 从 1 开始，每个新批次递增；失败重试复用原批次。每秒产生 15 次点击额度，最多积累 120 秒，保留小数额度；每次最多结算 5000 次。每 UTC 分钟达到 10 次点击记一个活跃分钟。每 600 次点击或 10 个活跃分钟获得一箱，每日最多 10 箱、持有最多 20 箱。

宝箱只掉落非初始表情。普通 / 稀有表情重复后分别获得 1 / 3 碎片，兑换价格分别为 10 / 30。每个角色第一套的前四个表情为初始表情。宝箱保留既有稀有度抽取与偏向未收集表情的权重；独立抽卡使用上一节的固定概率。

客户端 HTTP 超时为 10 秒，同一服务器的状态请求顺序执行。切换服务器时退出旧房间、清空显示状态；未送达的活动批次继续发往原服务器，过期响应按服务器代次过滤。

错误格式为 `{"detail":{"code":"...","message":"..."}}`。401：bad_token；409：no_box、no_shards、owned、no_ticket；400：bad_item、bad_pool、locked；字段校验错误返回 422。

## Upgrade

同时更新客户端、服务端和素材包。

- 旧数据库启动时增加 draw_tickets、draw_seconds、draw_pity、drawn_total、presence_last 及 presence_sessions 表。已有卡牌、表情、宝箱和碎片继续使用；旧配件与装扮记录保留在数据库中，当前产品不展示。
- 收藏集扩展至 70 张，并使用明确的 tier 字段；大隐藏不再根据是否带视频推断。
- 配件、装扮、预设 API 及房间对应字段已移除；loadout 仅同步角色和常用表情。
- 保留 activity 的 session / sequence 去重协议及旧 cards 表到 items 表的迁移。
