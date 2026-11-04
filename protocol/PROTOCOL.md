# AsoulTappo 协议

## 身份与房间

HTTP 请求使用 `X-Player-Token`（16–128 字符）；客户端本地生成，服务端以 SHA-256 前 16 位标识玩家。`GET /healthz` 返回服务状态，`POST /rooms` 返回随机房间号。房间在首次加入时创建、最后一个成员离开时回收，最多 20 人。

WebSocket 地址为 `/ws`，每帧一个 JSON 对象。

| 客户端 type | 字段 |
|---|---|
| join | room（1–64）、nick（1–24）、character（≤32）、token（可选） |
| leave | 无 |
| tap | count（1–500），客户端每 100–200ms 合并 |
| emote | emote（≤32），表情 key；初始表情免费，其余验证所有权 |
| state | character、nick，至少提供一个 |
| ping | 无 |

服务端消息：`joined {room,you,members}`、`member_joined {member}`、`member_left {id}`、`tap {id,count,total}`、`emote {id,emote}`、`state {id,character,nick}`、`pong`、`error {code,message}`。成员包含 `id,uid,nick,character,taps`。`uid = sha256(player_id + ':' + room)[:10]` 用于记录同桌位置。

## HTTP API

| 路由 | 请求与响应 |
|---|---|
| GET /api/manifest | 素材清单，与 `assets-packs/manifest.json` 一致 |
| GET /api/me | boxes、shards、progress、boxesToday、dailyCap、totals、pity、draw |
| POST /api/activity | `{taps,session,sequence}`，返回状态和 credited、newBoxes |
| POST /api/presence | `{session}`，记录运行心跳并返回状态 |
| POST /api/cards/draw | `{pool,count}`，count 为 1–100，返回状态和 drops |
| POST /api/boxes/open | `{count}`，每请求最多打开 10 箱，返回状态和 drops |
| POST /api/craft | `{item}`，兑换未拥有的非初始表情，返回状态和 item |
| GET /api/collection | owned（物品 ID → 数量）、recent（最近获得记录） |
| GET /api/loadout | character、favorites |
| POST /api/loadout | 更新 character 或 favorites（最多 8 个且已拥有） |
| GET /packs/index.json | 素材文件路径、大小及 SHA-256 |
| GET /packs/... | 卡面原图、视频及动画资源 |

物品 ID 为 `card:<id>` 或 `emote:<key>`。`drops[]` 包含 `item,rarity,new,count,shards`，抽卡额外包含 `tier`（`big` / `small` / `normal`）。

## 在线时长与抽卡

`draw` 包含 `tickets,seconds,secondsPerDraw,pity,hardPity,total`。客户端每 20 秒发送一次 `POST /api/presence` 心跳，累计满 300 秒获得 1 次抽卡机会。

每次抽卡先按档位概率抽取：大隐藏 0.5%、小隐藏 4.5%、普通 95%，随后在所选卡池的同档位卡牌中等概率抽取。所有卡池共用 400 抽大隐藏保底，抽中大隐藏后重置。

## 活动与表情宝箱

每 600 次有效点击或 10 个活跃分钟获得 1 个表情宝箱（每日最多 10 箱、持有上限 20 箱）。宝箱掉落非初始表情；普通 / 稀有表情重复获得分别转化为 1 / 3 碎片，兑换价格分别为 10 / 30 碎片。
