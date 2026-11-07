# AsoulTappo 协议

## 身份与房间

HTTP 请求使用 `X-Player-Token`（16–128 字符）；客户端本地生成，服务端以 SHA-256 前 16 位标识玩家。登录主站账号后改用 `Authorization: Bearer <主站令牌>`，服务端向 `MAIN_API_URL/auth/me` 确认账号（结果缓存 5 分钟），再按 `account_links` 找到绑定的存档。游客存档绑定账号后，原来的 `X-Player-Token` 返回 401 `save_linked`。`GET /healthz` 返回服务状态，`POST /rooms` 返回随机房间号。房间在首次加入时创建、最后一个成员离开时回收，最多 20 人。

WebSocket 地址为 `/ws`，每帧一个 JSON 对象。

| 客户端 type | 字段 |
|---|---|
| join | room（1–64）、nick（1–24）、character（≤32，成员名或以成员名开头的皮肤名，如 `贝拉山海经`）、token（可选）、accountToken（可选，主站令牌，优先于 token）、plate（可选，铭牌卡 ID，存档未拥有时忽略） |
| leave | 无 |
| tap | count（1–500），客户端每 100–200ms 合并；服务端按连接限速（每秒 15、最多攒 75），超出部分不广播。这只限制房间显示，每条连接各算各的，重连会重新计，不是每人总上限；收益只看 `POST /api/activity`，按存档共用一份额度（存在数据库里，并发、多连接、重连都不叠加） |
| motion | dx、dy（桌宠图层偏移，−20 至 20）、keyDown、left、right（按下状态）；移动每 50ms 合并，按键状态即时发送 |
| emote | emote（≤32），表情 key；初始表情免费，其余验证所有权 |
| state | character、nick、plate，至少提供一个；plate 为空字符串时取下铭牌，存档未拥有时返回 `locked` 并忽略整条消息 |
| ping | 无 |

服务端消息：`joined {room,you,members}`、`member_joined {member}`、`member_left {id}`、`tap {id,count,total}`、`motion {id,dx,dy,keyDown,left,right}`、`motion_batch {motions:[{id,dx,dy,keyDown,left,right}, ...]}`、`emote {id,emote}`、`state {id,character,nick,plate}`、`pong`、`error {code,message}`。成员包含 `id,uid,nick,character,taps,motion,plate`，plate 为经服务端核对的铭牌卡 ID，没有时为 null；加入时的 motion 为该成员最近一次桌宠动作。`uid = sha256(player_id + ':' + room)[:10]` 用于记录同桌位置。

连续位移由服务端按房间每 50ms 汇总为一条 `motion_batch`，每个成员保留最新位置。按键、左右键边沿仍即时发送 `motion`，入房、离房、表情和敲击消息按连接顺序发送。动作仅发给同房间的其他成员。每个连接独立发送，连续位置批次合并，发送超时或有序消息积压达到 256 条时断开该连接。客户端将短按状态保持至少 70ms，供桌宠呈现点击和按键动作。

连接关闭时清除成员动作，重连后发送当前动作；敲击计数由 `tap` 累计。本次协议更新配套发布客户端和服务端。

## HTTP API

| 路由 | 请求与响应 |
|---|---|
| GET /api/manifest | v4 素材清单，与 `assets-packs/manifest.json` 一致，包含 skins 和 economy |
| GET /api/me | player、shards、income、resonance、totals、checkin |
| POST /api/activity | `{taps,session,sequence}`，返回状态和 credited |
| POST /api/presence | `{session}`，按实际在线秒数结算碎片并返回状态 |
| POST /api/resonance/draw | `{count}`，count 为 1–100，实际次数取 count、100、余额可支付次数的最小值，返回状态和 drops |
| POST /api/craft | `{item}`，兑换未拥有的普通卡，以及普通、罕见、稀有表情，返回状态和 item |
| GET /api/checkin | 签到日历：today（北京时间日期）、available（今天还能不能签）、days（本月已签的 `{day,prize,shards}`，按日期排列，prize 为奖励档下标） |
| POST /api/checkin | 每日签到，每个存档每天一次，北京时间（UTC+8）零点刷新。服务端按 manifest `economy.checkin.prizes` 的权重抽一档，实发碎片在该档数额上下浮动 `economy.checkin.spread`（均匀分布，0.1 即 ±10%，四舍五入取整），返回状态和 `prize:{index,shards,day}`，index 为奖励档的下标；当天已签返回 409 `checked_in` |
| GET /api/collection | owned（物品 ID → 数量）、recent（最近获得记录） |
| GET /api/loadout | character、favorites、plate |
| POST /api/loadout | 更新 character、favorites（最多 8 个且已拥有）或 plate；五位原皮直接可用，皮肤要求已拥有；plate 必须是已拥有的大隐藏卡 ID，null 或空字符串取下铭牌 |
| GET /api/info | accountLogin（是否接入主站账号）、mainApi（主站 API 地址，未接入时为 null） |
| GET /api/client/release | 最新客户端版本 version 和更新说明 notes，读自主站 `/tappo/release`（未配置 `MAIN_API_URL` 时读官方主站），缓存 10 分钟；查不到时返回 503 `release_unavailable`。客户端用它检查更新，安装包仍由 Tauri 更新器从 GitHub 下载，失败时打开主站下载页 |
| GET /api/account | Bearer；user、save（账号存档摘要，未绑定时为 null） |
| POST /api/account/link | Bearer，可带 `X-Player-Token`。账号未绑定时把这份游客存档（或新存档）绑定到账号，返回 user、save、linkedGuest；账号已有存档且游客存档玩过时返回 409 `account_has_save`，附 account 和 guest 两份摘要；游客存档已属于其他账号时返回 401 `save_linked` |
| GET /packs/index.json | 素材文件路径、大小及 SHA-256 |
| GET /packs/... | 卡面原图及主题动画资源 |

铭牌是玩家装备的一张大隐藏卡，显示在其他成员桌面上该玩家桌宠的下方。客户端取卡面眼睛所在的一条横条，播放卡面视频；裁切位置保存在客户端 `client/src/pet/plates.ts`。联机页的座位仍显示普通名牌。

动态卡的 `video` 字段使用 `bundle:cards/<系列>/<id>.mp4`，随客户端安装并在本地播放。`/packs/index.json` 只索引服务端的静态卡面和主题资源。

物品 ID 为 `card:<id>`、`emote:<key>`、`char:<皮肤名称>`。五位成员原皮默认拥有，初始表情不参与共鸣。`drops[]` 包含 `item,rarity,new,count,shards`，卡片额外包含 `tier`（`big` / `small` / `normal`）。rarity 为 `legendary`、`skin`、`epic`、`rare`、`uncommon` 或 `common`。新物品及重复卡片的 shards 为 0，重复表情的 shards 为 10。

状态示例：

```json
{
  "player": "hash",
  "shards": 7360,
  "income": { "multiplier": 3.2, "perMinute": 12.8 },
  "resonance": {
    "pity": { "legendary": 212, "skin": 87 },
    "hardPity": { "legendary": 400, "skin": 200 },
    "total": 1234
  },
  "totals": { "taps": 0, "activeMinutes": 0, "owned": 0, "items": 547 },
  "checkin": { "available": true }
}
```

错误沿用 `{detail:{code,message}}`，碎片不足为 `no_shards`（409），兑换已拥有物品为 `owned`（409），装备未拥有皮肤为 `locked`（400）。

## 管理接口

主站后台用来查看和管理桌宠账号。服务端配置 `ASOULTAPPO_ADMIN_KEY` 后启用，请求需带 `X-Admin-Key`；未配置或密钥不符时一律返回 404。`/admin` 不经过公网反向代理，只由同机的主站 API 访问。统计按北京时间（UTC+8）切分日期；当天有活动上报（敲击被计入）或在线心跳的存档记为活跃。

| 路由 | 请求与响应 |
|---|---|
| GET /admin/stats?days= | days 为 1–180，默认 30。totals：saves（存档数）、linked（已绑定账号）、guests（游客存档）、activeToday、rooms、online；series：每天一行 `{day,active,newSaves,items}`，从旧到新 |
| GET /admin/accounts?ids=&offset=&limit= | 已绑定账号的存档，按最近活动倒序；ids 为逗号分隔的主站用户 ID（最多 100 个），用于按主站搜索结果筛选。返回 total、accounts（`userId,linkedAt,shards,owned,taps,lastActive`） |
| POST /admin/accounts/{userId}/shards | `{delta}`，正数补发、负数扣减，扣到负数时返回 409 `no_shards`；返回新的 shards |
| POST /admin/accounts/{userId}/unlink | 解除绑定。存档保留，原游客令牌恢复可用，账号可以重新绑定 |

账号没有绑定存档时返回 409 `account_not_linked`。

## 在线收益与活动

客户端每 20 秒发送心跳和累计敲击数。碎片收益为每分钟 `4 × (1 + 7 × min(上一分钟有效敲击数, 60) / 60)`，倍率最高 ×8。只挂机每分钟 4 碎片，上一分钟 30 下为 18 碎片，60 下及以上为 32 碎片。超过一分钟没有敲击上报后倍率回到 ×1，小数碎片留到下次结算。

服务端只接收敲击次数，按每秒 15 下限速；相同 session 的 sequence 去重。每个 UTC 分钟累计 10 下计一个活跃分钟。多个运行客户端共用玩家的在线时间基准；心跳间隔超过 60 秒时重新建立在线基准。

## 共鸣与兑换

五位成员共用一个池子，所有非初始卡片、表情和皮肤一起参与共鸣。三张心宜与思诺共有卡各自只入池一次，共用同一个拥有记录。可抽内容共 547 件：85 张卡、455 张表情、7 款皮肤。

| 档位 | 内容 | 概率 | 保底 |
|---|---|---|---|
| 传说 | 大隐藏卡 | 0.5% | 400 次 |
| 皮肤 | 成员皮肤 | 0.5% | 200 次 |
| 史诗 | 小隐藏与跳舞卡 | 4.5% | — |
| 稀有 | 动态表情 | 3% | — |
| 罕见 | 绽放收藏集与脑洞波表情 | 6% | — |
| 普通 | 普通卡与普通表情 | 85.5% | — |

每次消耗 160 碎片。两个保底各自累计，抽中对应档位时清零；同时到期先出大隐藏，下次出皮肤。对应档位全部拥有时保留进度，新增内容后可继续触发。高档集齐后的概率并入普通档。普通档先按 `commonKindWeights`（普卡 45 : 表情 40.5）选类型，再在该类型内等概率选择未拥有物品，该类型集齐后产生重复；只有表情重复返还 10 碎片，卡片重复累计数量。初始单抽概率为普卡 45%、普通表情 40.5%；某类集齐后仍保持类型比例。其他档位在未拥有物品内等概率选择。

稀有表情为此间为爱、绮梦漫游、匣中惊鸿三套动态表情，共 60 个；罕见为绽放收藏集与脑洞波各三套，共 75 个；普通表情共 320 个。已有物品按原 ID 保留。

新玩家获得 1600 碎片。普通卡与普通表情兑换价格为 480，罕见表情为 960，稀有表情为 1600；史诗、传说、皮肤和初始表情不参与兑换。

## 数据迁移

首次启动新版本时，旧碎片乘 16，旧抽卡次数和箱余额每份换成 160 碎片，随后清零旧余额。迁移由 skin_pity 列的存在性标记，只执行一次。已拥有物品、draw_pity 大隐藏进度和 drawn_total 累计次数保留。发布前备份数据库并在备份副本验证换算；回滚时同时恢复匹配版本的数据库。
