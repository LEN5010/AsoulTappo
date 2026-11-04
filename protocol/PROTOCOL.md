# AsoulTappo 协议

## 身份与房间

HTTP 请求使用 `X-Player-Token`（16–128 字符）；客户端本地生成，服务端以 SHA-256 前 16 位标识玩家。`GET /healthz` 返回服务状态，`POST /rooms` 返回随机房间号。房间在首次加入时创建、最后一个成员离开时回收，最多 20 人。

WebSocket 地址为 `/ws`，每帧一个 JSON 对象。

| 客户端 type | 字段 |
|---|---|
| join | room（1–64）、nick（1–24）、character（≤32，成员名或以成员名开头的皮肤名，如 `贝拉山海经`）、token（可选） |
| leave | 无 |
| tap | count（1–500），客户端每 100–200ms 合并 |
| emote | emote（≤32），表情 key；初始表情免费，其余验证所有权 |
| state | character、nick，至少提供一个 |
| ping | 无 |

服务端消息：`joined {room,you,members}`、`member_joined {member}`、`member_left {id}`、`tap {id,count,total}`、`emote {id,emote}`、`state {id,character,nick}`、`pong`、`error {code,message}`。成员包含 `id,uid,nick,character,taps`。`uid = sha256(player_id + ':' + room)[:10]` 用于记录同桌位置。

## HTTP API

| 路由 | 请求与响应 |
|---|---|
| GET /api/manifest | v4 素材清单，与 `assets-packs/manifest.json` 一致，包含 skins 和 economy |
| GET /api/me | player、shards、income、resonance、totals |
| POST /api/activity | `{taps,session,sequence}`，返回状态和 credited |
| POST /api/presence | `{session}`，按实际在线秒数结算碎片并返回状态 |
| POST /api/resonance/draw | `{count}`，count 为 1–100，实际次数取 count、100、余额可支付次数的最小值，返回状态和 drops |
| POST /api/craft | `{item}`，兑换未拥有的普通卡、普通表情或稀有表情，返回状态和 item |
| GET /api/collection | owned（物品 ID → 数量）、recent（最近获得记录） |
| GET /api/loadout | character、favorites |
| POST /api/loadout | 更新 character 或 favorites（最多 8 个且已拥有）；五位原皮直接可用，皮肤要求已拥有 |
| GET /packs/index.json | 素材文件路径、大小及 SHA-256 |
| GET /packs/... | 卡面原图、视频及动画资源 |

物品 ID 为 `card:<id>`、`emote:<key>`、`char:<皮肤名称>`。五位成员原皮默认拥有，初始表情不参与共鸣。`drops[]` 包含 `item,rarity,new,count,shards`，卡片额外包含 `tier`（`big` / `small` / `normal`）。rarity 为 `legendary`、`skin`、`epic`、`rare` 或 `common`。新物品 shards 为 0，普通档重复返还 40。

状态示例：

```json
{
  "player": "hash",
  "shards": 7360,
  "income": { "multiplier": 3.2, "perMinute": 51.2 },
  "resonance": {
    "pity": { "legendary": 212, "skin": 87 },
    "hardPity": { "legendary": 400, "skin": 200 },
    "total": 1234
  },
  "totals": { "taps": 0, "activeMinutes": 0, "owned": 0, "items": 428 }
}
```

错误沿用 `{detail:{code,message}}`，碎片不足为 `no_shards`（409），兑换已拥有物品为 `owned`（409），装备未拥有皮肤为 `locked`（400）。

## 在线收益与活动

客户端每 20 秒发送心跳和累计敲击数。碎片收益为每分钟 `16 × (1 + 4 × min(上一分钟有效敲击数, 60) / 60)`，倍率最高 ×5。只挂机每分钟 16 碎片，上一分钟 30 下为 48 碎片，60 下及以上为 80 碎片。超过一分钟没有敲击上报后倍率回到 ×1，小数碎片留到下次结算。

服务端只接收敲击次数，按每秒 15 下限速；相同 session 的 sequence 去重。每个 UTC 分钟累计 10 下计一个活跃分钟。多个运行客户端共用玩家的在线时间基准；心跳间隔超过 60 秒时重新建立在线基准。

## 共鸣与兑换

五位成员共用一个池子，所有非初始卡片、表情和皮肤一起参与共鸣。三张心宜与思诺共有卡各自只入池一次，共用同一个拥有记录。可抽内容共 428 件：70 张卡、355 张表情、3 款皮肤。

| 档位 | 内容 | 概率 | 保底 |
|---|---|---|---|
| 传说 | 大隐藏卡 | 0.5% | 400 次 |
| 皮肤 | 成员皮肤 | 0.5% | 200 次 |
| 史诗 | 小隐藏与跳舞卡 | 4.5% | — |
| 稀有 | 稀有表情 | 5% | — |
| 普通 | 普通卡与普通表情 | 89.5% | — |

每次消耗 160 碎片。两个保底各自累计，抽中对应档位时清零；同时到期先出大隐藏，下次出皮肤。对应档位全部拥有时保留进度，新增内容后可继续触发。高档集齐后的概率并入普通档，各档先等概率选择未拥有物品，普通档集齐后重复返还 40 碎片。

新玩家获得 1600 碎片。普通卡与普通表情兑换价格为 480，稀有表情为 1600；史诗、传说、皮肤和初始表情不参与兑换。

## 数据迁移

首次启动新版本时，旧碎片乘 16，旧抽卡次数和箱余额每份换成 160 碎片，随后清零旧余额。迁移由 skin_pity 列的存在性标记，只执行一次。已拥有物品、draw_pity 大隐藏进度和 drawn_total 累计次数保留。发布前备份数据库并在备份副本验证换算；回滚时同时恢复匹配版本的数据库。
