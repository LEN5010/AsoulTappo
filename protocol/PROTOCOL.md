# AsoulTappo 协议

## 身份与房间

HTTP 请求使用 `X-Player-Token`（16–128 字符）；客户端本地生成，服务端以 SHA-256 前 16 位标识玩家。登录主站账号后改用 `Authorization: Bearer <主站令牌>`，服务端向 `MAIN_API_URL/auth/me` 确认账号（结果缓存 5 分钟；主站连不上时沿用该令牌 1 小时内的上次结果，没有则返回 503 `account_unavailable`，失败后 15 秒内不再请求主站），再按 `account_links` 找到绑定的存档。游客存档绑定账号后，原来的 `X-Player-Token` 返回 401 `save_linked`。`GET /healthz` 返回服务状态，`POST /rooms` 返回随机房间号。房间在首次加入时创建、最后一个成员离开时回收，最多 20 人。

第一个进入房间的成员是房主；房主离开（包括连接因超时或积压被断开）后，房主传给剩下成员里最早进入的一位。房间默认私密，房主可以随时设为公开或改回私密，公开房间出现在 `GET /rooms` 里。设为公开要求房主带存档（见下），否则返回 `host_needs_save`。接入了主站账号的服务端（配置了 `MAIN_API_URL`）还要求房主这条连接加入时带了有效的 accountToken，否则返回 `host_needs_account`；两项都检查时先查账号，所以没登录的房主收到 `host_needs_account`，登录了但账号没绑定存档的收到 `host_needs_save`。改回私密不受这两条限制。房主传给没登录账号的成员时，房间保持公开，新房主可以改回私密，但不能再设为公开。公开以后，新加入的成员必须带存档；设为公开前已经在房间里的无存档成员留下。这里的带存档指加入时的 token 或 accountToken 能解析出存档，与 HTTP 接口的身份规则相同。

房主可以移出其他成员，不能移出自己。被移出成员的存档记在这个房间的封禁名单上，房间回收前这份存档无法再进入；同一存档在房间里的其他连接一起移出。无存档的成员也可以移出，但没有存档可封，他拿着房间号还能再进来（公开房间除外，因为公开房间不收无存档成员）。房主在另一条连接上的同一存档只移出、不封禁。房间回收后封禁名单随之清空。正在猜拳的成员（下注已扣）不能被移出，返回 `in_duel`。成员被移出房间（被移出、连接写入失败）后如果连接还没关，这条连接再发来的消息按未加入处理：`ping` 和 `join` 照常，其余返回 `not_joined`。房间没有文字聊天。

`GET /rooms` 在接入了主站账号的服务端上要求 `Authorization: Bearer <主站令牌>`：没带令牌返回 401 `account_required`，令牌无效返回 401 `account_expired`，主站连不上返回 503 `account_unavailable`；账号不必绑定存档。没接入账号的服务端不检查身份。凭房间号加入不受影响，游客存档照样能进公开房间。返回 `{rooms:[{room,host:{nick,character},members,max}, ...]}`：公开房间的房间号、房主昵称和显示的角色、当前人数和人数上限，最多 50 个。有空位的房间排在前面，同类按人数从多到少，人数相同按创建先后。满员房间照样列出。

WebSocket 地址为 `/ws`，每帧一个 JSON 对象。不是 JSON 文本或字段不合格式的帧返回 `error` `bad_message`，连接保持。

| 客户端 type | 字段 |
|---|---|
| join | room（1–64）、nick（1–24）、character（≤32，成员名或以成员名开头的皮肤名，如 `贝拉山海经`；存档未拥有的皮肤或未知名称改为显示名称开头的成员，都不匹配时显示第一位成员）、token（可选）、accountToken（可选，主站令牌，优先于 token）、plate（可选，铭牌 ID，存档未解锁或不认识时忽略）、dnd（可选，布尔，猜拳免打扰，见猜拳一节） |
| leave | 无 |
| tap | count（1–500），客户端每 100–200ms 合并；服务端按连接限速（每秒 15、最多攒 75），超出部分不广播。这只限制房间显示，每条连接各算各的，重连会重新计，不是每人总上限；收益只看 `POST /api/activity`，按存档共用一份额度（存在数据库里，并发、多连接、重连都不叠加） |
| motion | dx、dy（桌宠图层偏移，−20 至 20）、keyDown、left、right（按下状态）；移动每 50ms 合并，按键状态即时发送 |
| emote | emote（≤32），表情 key；初始表情免费，其余验证所有权 |
| state | character、nick、plate，至少提供一个；plate 为空字符串时取下铭牌。character 为存档未拥有的皮肤（或未知名称）、plate 未解锁时返回 `locked` 并忽略整条消息 |
| ping | 无 |
| set_public | public（布尔），仅房主；值有变化时向全房间广播 `room_info`，没有变化时只把当前的 `room_info` 回给房主 |
| kick | id（成员 id），仅房主；不是房主返回 `not_host`，id 不在房间里或是房主自己返回 `no_member`，要移出的连接正在猜拳返回 `in_duel` |
| dnd | dnd（布尔），猜拳免打扰开关；只发给有猜拳的服务端 |
| duel_invite | id（成员 id）、bet（下注，必须是 `economy.duel.stakes` 里的一档） |
| duel_answer | duel（对局 id）、accept（布尔），只有被邀请的一方能回应 |
| duel_throw | duel、hand（`rock` / `scissors` / `paper`），每局只认第一次 |

服务端消息：`joined {room,you,members,info}`、`room_info {host,public}`、`member_joined {member}`、`member_left {id}`、`tap {id,count,total}`、`motion {id,dx,dy,keyDown,left,right}`、`motion_batch {motions:[{id,dx,dy,keyDown,left,right}, ...]}`、`emote {id,emote}`、`scratch {id,shards}`、`state {id,character,nick,plate}`、`duel_invite`、`duel_start`、`duel_round`、`duel_result`、`duel_over`、`sticker {id,key,sec}`（猜拳一节）、`pong`、`error {code,message,reason?}`。`info` 和 `room_info` 是房间级状态：host 为房主的成员 id，public 表示房间是否公开；房主变化或公开状态变化时服务端广播 `room_info`。成员包含 `id,uid,nick,character,taps,motion,plate`，plate 为经服务端核对的铭牌 ID，没有时为 null；加入时的 motion 为该成员最近一次桌宠动作。`uid = sha256(player_id + ':' + room)[:10]` 用于记录同桌位置。

连续位移由服务端按房间每 50ms 汇总为一条 `motion_batch`，每个成员保留最新位置。按键、左右键边沿仍即时发送 `motion`，入房、离房、表情和敲击消息按连接顺序发送。动作仅发给同房间的其他成员。每个连接独立发送，连续位置批次合并，发送超时或有序消息积压达到 256 条时断开该连接。客户端将短按状态保持至少 70ms，供桌宠呈现点击和按键动作。

连接关闭时清除成员动作，重连后发送当前动作；敲击计数由 `tap` 累计。本次协议更新配套发布客户端和服务端。

### 错误码

| code | 含义 |
|---|---|
| bad_message | 帧不是 JSON 或字段不合格式；加入请求被判为无效时客户端停止重连 |
| not_joined / already_joined | 没加入就发送房间消息 / 重复加入 |
| room_full | 结束这次会话：客户端收到后停止重连。不带 reason 时表示房间已满（20 人）；带 reason 时见下 |
| locked | 表情、皮肤或铭牌未解锁，整条消息被忽略 |
| rate_limited | 表情发得太快 |
| not_host | 非房主发送 `set_public` 或 `kick` |
| no_member | `kick` 的 id 不在房间里或是房主自己 |
| host_needs_save | 无存档的房主设置公开 |
| host_needs_account | 接入了主站账号的服务端上，没带有效 accountToken 加入的房主设置公开 |
| in_duel | 要移出的成员正在猜拳 |
| no_duel | 服务器没有猜拳（manifest 没有 `economy.duel`） |
| duel_locked / duel_target_locked | 自己 / 对方没有存档，或累计敲击不足 |
| duel_busy / duel_target_busy | 自己 / 对方的存档已有一场对局或待回应的邀请 |
| duel_self | 邀请自己，或同一存档的另一条连接 |
| duel_cooldown | 对方 30 秒内拒绝过或没回应过你的邀请 |
| duel_cap | 这一档赢了会让某一方今天的净赢超过上限 |
| no_shards | 邀请方碎片不够这一档 |
| duel_gone | 回应或出拳时对局已经结束（客户端不提示） |

`room_full` 的 reason：`kicked`（被房主移出，发完这条后服务端关闭这条连接）、`banned`（存档在这个房间的封禁名单上，加入被拒，连接保持）、`need_save`（无存档加入公开房间，加入被拒，连接保持）。其他错误不带 reason 字段。

### 与 1.1 及更早版本的兼容

- 旧客户端只在收到 `room_full` 时停止重连，关闭码和其他错误码都会让它重连。所以被移出、被封禁、无存档进公开房间都用 `room_full` 加 reason 表示，旧客户端会当成最终失败并停止，但界面显示的是房间已满的文案（它按 code 选文案，不读 message 和 reason）。
- 旧客户端忽略 `room_info` 和 `joined` 里的 `info`，不显示房主，也不会发送 `set_public` 和 `kick`。旧客户端作为房主时，房间保持私密，直到房主传给新客户端。
- 新客户端连旧服务端：`joined` 没有 `info` 时不显示房主标记、公开开关和移出键，也不发送 `set_public` 和 `kick`；`GET /rooms` 在旧服务端返回 405（只有 `POST /rooms`），客户端收到 404 或 405 时不显示公开房间列表。
- 公开房间要求账号：客户端先读 `GET /api/info`，`accountLogin` 为 true 且没登录时不请求列表，公开房间一节只显示登录键；登录后带主站令牌请求，令牌只发给登录时所在的服务器。列表返回 401 时按未登录处理（`account_expired` 同时清除本地的登录状态）。房主没登录时不显示公开开关，房间已经公开时除外（用来改回私密）。`/api/info` 读不到时按没接入账号处理，服务端返回 401 时同样显示登录键。
- 猜拳：旧客户端忽略 `duel_*` 和 `sticker` 消息（`RoomClient` 不认识的类型直接丢弃），成员字段没有变化；它收不到也回应不了邀请，邀请它的人 15 秒后看到超时。新客户端只在 `GET /api/me` 带 `duel` 时显示猜拳键、发送 `dnd` 和猜拳消息；旧服务端的状态没有这一项。`join` 里的 dnd 只在打开时带上，旧服务端忽略多出来的字段。

## HTTP API

| 路由 | 请求与响应 |
|---|---|
| GET /api/manifest | v4 素材清单，与 `assets-packs/manifest.json` 一致，包含 skins 和 economy |
| GET /api/me | player、shards、income、resonance、totals、checkin、tapCooldown、scratch、duel（`{net}`，今天猜拳的净赢；没有猜拳的服务端不带） |
| POST /api/activity | `{taps,session,sequence,cooldown?}`，返回状态和 credited；cooldown 是客户端自己触发冷却后剩余的秒数 |
| POST /api/presence | `{session}`，记录在线并返回状态；在线本身不给碎片 |
| POST /api/resonance/draw | `{count}`，count 为 1–100，实际次数取 count、100、余额可支付次数的最小值，返回状态和 drops |
| POST /api/craft | `{item}`，兑换未拥有的普通卡，以及普通、罕见、稀有表情，返回状态和 item |
| GET /api/checkin | 签到日历：today（北京时间日期）、available（今天还能不能签）、days（本月已签的 `{day,prize,shards}`，按日期排列，prize 为奖励档下标） |
| POST /api/checkin | 每日签到，每个存档每天一次，北京时间（UTC+8）零点刷新。服务端按 manifest `economy.checkin.prizes` 的权重抽一档，实发碎片在该档数额上下浮动 `economy.checkin.spread`（均匀分布，0.1 即 ±10%，四舍五入取整），返回状态和 `prize:{index,shards,day}`，index 为奖励档的下标；当天已签返回 409 `checked_in` |
| GET /api/scratch | 刮刮乐状态：day（北京时间日期）、left（今天还能买几张）、pity（距上次出阿草表情已买的张数）、card（已买未揭开的卡 `{id,cells}`，没有时为 null） |
| POST /api/scratch | 买一张刮刮乐，返回状态和 `card:{id,cells}`。已有未揭开的卡时原样返回这张卡，不再扣费。当天卖完返回 409 `sold_out`，碎片不足返回 409 `no_shards` |
| POST /api/scratch/reveal | `{card}`，揭开这张卡并发放奖品，返回状态和 `prize:{shards,item}`。重复揭开返回同一份奖品，不再发放；卡不存在或不属于该存档返回 404 `no_card` |
| GET /api/collection | owned（物品 ID → 数量）、recent（最近获得记录） |
| GET /api/loadout | character、favorites、plate |
| POST /api/loadout | 更新 character、favorites（最多 8 个且已拥有）或 plate；五位原皮直接可用，皮肤要求已拥有；plate 必须是已解锁的铭牌 ID，null 或空字符串取下铭牌；不是铭牌的 ID 返回 `bad_item`，未集齐返回 `locked` |
| GET /api/info | accountLogin（是否接入主站账号）、mainApi（主站 API 地址，未接入时为 null） |
| GET /api/client/release | 最新客户端版本 version 和更新说明 notes，读自主站 `/tappo/release`（未配置 `MAIN_API_URL` 时读官方主站），缓存 10 分钟；查不到时返回 503 `release_unavailable`。客户端用它检查更新，安装包仍由 Tauri 更新器从 GitHub 下载，失败时打开主站下载页 |
| GET /api/account | Bearer；user、save（账号存档摘要，未绑定时为 null） |
| POST /api/account/link | Bearer，可带 `X-Player-Token`。账号未绑定时把这份游客存档（或新存档）绑定到账号，返回 user、save、linkedGuest；账号已有存档且游客存档玩过时返回 409 `account_has_save`，附 account 和 guest 两份摘要；游客存档已属于其他账号时返回 401 `save_linked` |
| GET /packs/index.json | 素材文件路径、大小及 SHA-256 |
| GET /packs/... | 卡面原图及主题动画资源 |

铭牌显示在其他成员桌面上该玩家桌宠的下方。`plate` 字段是铭牌 ID，有两种：

- 大隐藏卡的卡片 ID（形如 `c1762331462002`）。解锁条件是集齐这张卡所在收藏集里该成员的全部卡片（包括大隐藏本身）：几位成员共用的收藏集只要求该成员的卡，双人卡要求整个双人收藏集。客户端取卡面眼睛所在的一条横条，播放卡面视频。
- manifest 顶层 `plates` 里的铭牌 ID，每项为 `{id,name,emoteSet}`，拥有表情套 `emoteSet` 的全部表情即解锁。目前只有阿草铭牌 `achao`，由刮刮乐的 20 个阿草表情解锁。客户端显示侧栏的阿草图，横条从手臂慢慢扫到脸上再回到手臂。

`plates` 的 ID 不与卡片 ID 重复。服务端和客户端读同一份 manifest 判断解锁；没有 `plates` 的旧 manifest 只认大隐藏卡。存档里已装备但未集齐的铭牌，读取装备和进房间时会被取下。裁切位置和动效节奏保存在客户端 `client/src/pet/plates.ts`。联机页的座位仍显示普通名牌。

动态卡的 `video` 字段使用 `bundle:cards/<系列>/<id>.mp4`，随客户端安装并在本地播放。`/packs/index.json` 只索引服务端的静态卡面和主题资源。

物品 ID 为 `card:<id>`、`emote:<key>`、`char:<皮肤名称>`。五位成员原皮默认拥有，初始表情不参与共鸣。`drops[]` 包含 `item,rarity,new,count,shards`，卡片额外包含 `tier`（`big` / `small` / `normal`）。rarity 为 `legendary`、`skin`、`epic`、`rare`、`uncommon` 或 `common`。重复物品自动兑换成碎片，不再累计数量：新物品的 shards 为 0，重复表情为 5，重复的普通卡和跳舞卡为 20，重复的小隐藏为 360（`economy.resonance.duplicateRefund`，卡片按 `tier` 取值）。1.1 之前累计的重复卡片在服务端启动时一次性按同样标准折算，数量改为 1。

状态示例：

```json
{
  "player": "hash",
  "shards": 7360,
  "income": { "day": "2026-11-10", "today": 3752, "cap": 10400, "taps": 2820, "perTap": 0.733, "multiplier": 1, "perMinute": 44.0 },
  "resonance": {
    "pity": { "legendary": 212, "skin": 87 },
    "hardPity": { "legendary": 400, "skin": 200 },
    "total": 1234
  },
  "totals": { "taps": 0, "activeMinutes": 0, "owned": 0, "items": 569 },
  "checkin": { "available": true },
  "tapCooldown": 0,
  "scratch": { "left": 20, "pity": 0 }
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
| GET /admin/blocked-words | 昵称屏蔽词表，返回 `{words,count}`，按上次保存时的顺序 |
| PUT /admin/blocked-words | `{words:[...]}`，整表替换。每个词去掉首尾空白后为 1–64 个字符，最多 20000 个（按去重前的个数算），不符合时返回 422 且词表不变；去重后保存原词（不保存折叠结果）。返回 `{count}`，为去重后的个数。新词表立即对在线成员生效，见下节 |

账号没有绑定存档时返回 409 `account_not_linked`。

### 昵称屏蔽

服务端按屏蔽词表给房间昵称（join 和 state 的 nick）打码后再发出：`joined.members`、`member_joined`、`state` 和 `GET /rooms` 的房主昵称都是打码后的结果，命中部分换成 `*`。房间协议和错误码不变，命中不会被拒绝进房。发给本人的 `joined.members` 和 `state` 里也是打码后的昵称：新客户端在成员列表里自己那一行显示本地设置的昵称；1.1.1 及更早的客户端显示服务端发来的值，所以本人会在成员列表里看到星号。词表为空时昵称原样转发。词表由主站后台维护，保存时调用 `PUT /admin/blocked-words`。更新后服务端用新词表重新计算在线成员的原始昵称（删掉的词会恢复显示），昵称有变化的成员由服务端向所在房间广播一条 `state`。

折叠规则（主站移植时须完全一致；下标和长度都按 Unicode 码点计，不按 UTF-16 编码单元）：

1. 逐个码点处理原文。每个码点先做 NFKD 分解，再把分解出的每个字符单独转小写（Python `str.lower()`，JavaScript `toLowerCase()`；逐个字符转换，避开希腊字母词尾 σ 这类依赖上下文的规则）。结果只保留 Unicode 大类为 L（字母）或 N（数字）的字符，其余全部跳过：空格、标点、符号、组合记号、零宽和格式字符、表情。每个保留的字符记下它来自原文的第几个码点。
2. 词表里的每个词按同一规则折叠，折叠后为空的词忽略。
3. 折叠后的词是折叠后昵称的连续子串，即为命中。

打码规则：从命中的第一个字符对应的原文码点，到最后一个字符对应的原文码点，这一段原文（包括中间被跳过的字符）每个码点换成一个 `*`；段外的字符原样保留，码点总数不变。多处命中、重叠命中取并集。紧跟在最后一个命中字符后面的组合记号不在这一段里，会留在 `*` 后面（见下表 `café` 一行）。

不处理的情况：谐音和拼音、繁简转换、形近字符互相替换（例如用 0 代替 o）。

字符分类和 NFKD 分解取自运行环境的 Unicode 字符数据（服务端为 Python `unicodedata`，版本跟随部署镜像的 Python），不同版本之间可能有个别字符不同。下表在 Unicode 16.0 下生成，表中字符在各版本里结果相同。

测试向量。词表为 `坏词`、`BadWord`、`café`、`wordy`、`!!`，其中 `!!` 折叠后为空，被忽略。`​` 这类写法代表对应的码点；😀 是 U+1F600，占 1 个码点、2 个 UTF-16 编码单元。

| 输入 | 折叠结果 | 打码结果 | 覆盖 |
|---|---|---|---|
| `[坏词]` | `坏词` | `[**]` | 段外字符保留 |
| `ＢＡＤＷＯＲＤ` | `badword` | `*******` | 全角、大写 |
| `Bad Word!` | `badword` | `********!` | 插入空格，中间的分隔符一起打码 |
| `坏​词abc` | `坏词abc` | `***abc` | 零宽字符 |
| `CAFÉ` | `cafe` | `****` | 预组合的带音标字母 |
| `café` | `cafe` | `****́` | 分解形式的带音标字母，尾随组合记号 |
| `坏词x坏词` | `坏词x坏词` | `**x**` | 多处命中 |
| `badwordy` | `badwordy` | `********` | 重叠命中取并集 |
| `坏😀词` | `坏词` | `***` | 表情作分隔符，码点下标与 UTF-16 下标不同 |
| `好词` | `好词` | `好词` | 不命中 |

## 敲击收益与活动

客户端每 20 秒发送心跳和累计敲击数。碎片只来自敲击，在线本身不给碎片。每个北京时间自然日按当天计入的敲击数 n 累计发放 `min(2800 × ln(1 + n / 1000), 10400)` 碎片：开头每下约 2.8 碎片，1 万下累计约 6710，约 4 万下达到每天上限 10400，之后当天不再增加，次日零点重新计算。每个 UTC 分钟只有前 120 下计入 n，超出的仍计入总敲击数和活跃分钟。小数碎片留到下次结算。参数在 manifest `economy.income`：`shardScale`（2800）、`tapScale`（1000）、`dailyCap`（10400）、`tapsPerMinute`（120）。

状态里的 `income`：`day` 是这些数字所属的北京时间日期（YYYY-MM-DD），`today` 是今天已从敲击拿到的碎片，`cap` 是每天上限，`taps` 是今天计入的敲击数，`perTap` 是下一下值多少碎片（达到上限后为 0）。`multiplier` 固定为 1、`perMinute` 为 `perTap × 60`，只给 1.0 版客户端显示，新客户端不读。

服务端只接收敲击次数，按每秒 15 下限速；相同 session 的 sequence 去重。同一 session 相邻两次上报之间平均每秒 10 下及以上算过快，过快连续 30 秒及以上时，这份存档进入 60 秒冷却：触发的那一批和冷却期间所有 session 的上报都不计入，也不给碎片。状态里的 `tapCooldown` 是冷却剩余秒数，没有冷却时为 0。客户端按同样的门槛逐秒判断（连续 30 秒每秒都有 10 下及以上），触发后 60 秒内不计数、不广播敲击，并在桌宠上方提示剩余秒数；触发时立刻上报一批（没有敲击也报），带上 `cooldown` 剩余秒数，服务端据此让这份存档进入冷却（最多 60 秒，只会延长不会缩短），这一批不计入。服务端判定的冷却客户端也照样显示。每个 UTC 分钟累计 10 下计一个活跃分钟。

## 共鸣与兑换

五位成员共用一个池子，所有非初始卡片、表情和皮肤一起参与共鸣。三张心宜与思诺共有卡各自只入池一次，共用同一个拥有记录。可抽内容共 549 件：85 张卡、455 张表情、9 款皮肤。

| 档位 | 内容 | 概率 | 保底 |
|---|---|---|---|
| 传说 | 大隐藏卡 | 0.1% | 400 次 |
| 皮肤 | 成员皮肤 | 0.2% | 200 次 |
| 史诗 | 小隐藏与跳舞卡 | 4.5% | — |
| 稀有 | 动态表情 | 3% | — |
| 罕见 | 绽放收藏集与脑洞波表情 | 6% | — |
| 普通 | 普通卡与普通表情 | 86.2% | — |

每次消耗 160 碎片。两个保底各自累计，抽中对应档位时清零；同时到期先出大隐藏，下次出皮肤。对应档位全部拥有时保留进度，新增内容后可继续触发。高档集齐后的概率并入普通档，`repeatTiers` 里的档位（目前只有史诗档）除外：史诗档集齐后保留 4.5%，在整档里等概率抽，出的都是重复。普通档先按 `commonKindWeights`（普卡 45 : 表情 41.2）选类型，再在该类型内等概率选择未拥有物品，该类型集齐后产生重复。重复按上面的标准兑换成碎片。初始单抽概率为普卡 45%、普通表情 41.2%；某类集齐后仍保持类型比例。其他档位在未拥有物品内等概率选择。

稀有表情为此间为爱、绮梦漫游、匣中惊鸿三套动态表情，共 60 个；罕见为绽放收藏集与脑洞波各三套，共 75 个；普通表情共 320 个。已有物品按原 ID 保留。

新玩家获得 1600 碎片。普通卡与普通表情兑换价格为 480，罕见表情为 960，稀有表情为 1600；史诗、传说、皮肤和初始表情不参与兑换。

## 刮刮乐

每张 500 碎片，每个存档每天 20 张，北京时间零点刷新。配置在 manifest `economy.scratch`，没有这一项的服务端不提供刮刮乐，状态里也没有 `scratch`，三个接口返回 404 `no_scratch`。

| 奖品 | 概率 | 保底 |
|---|---|---|
| 阿草表情 | 5% | 10 张 |
| 30000 碎片 | 0.1% | — |
| 2500 碎片 | 2% | — |
| 1000 碎片 | 5% | — |
| 500 碎片 | 12% | — |
| 200 碎片 | 30% | — |
| 没中 | 45.9% | — |

奖品在买卡时由一次随机数决定，揭开时才发放，所以买卡后的余额只少了卡价。一个存档同时只有一张未揭开的卡；未揭开的卡跨天仍可揭开。碎片奖品平均返还卡价的一半。

阿草表情是表情套 `achao` 的 20 个表情（`source: "scratch"`），只从刮刮乐获得，不进共鸣池，也不能兑换。每次给一个存档还没有的；保底按买卡张数累计，出表情时清零，计数方式与共鸣保底相同。

20 个集齐后没有表情这一档，也不再触发保底：只按碎片奖品的权重抽，表情的 5% 并入没中，没中为 50.9%，不给重复表情。是否集齐在买卡时判断，拿到最后一个表情的那张卡揭开之后，下一张才按集齐后的规则抽。集齐后 `pity` 不再变化；最后一个表情出现时已清零，所以通常是 0。

`cells` 是九个格子的图案，碎片数额写成数字串，表情写成表情 key。中奖图案恰好出现三次，其余图案最多出现两次；没中的卡没有出现三次的图案。

揭开的碎片奖品达到 `economy.scratch.announce`（2500）时，服务端向该存档所在的每个房间广播 `scratch {id,shards}`，客户端在这位成员的桌宠上方显示。出表情由客户端在揭开后发送这个表情。

## 猜拳

房间里两位成员之间的石头剪刀布。数值在 manifest `economy.duel`，服务端和客户端读同一份；没有这一项的服务端没有猜拳，状态里也没有 `duel`，猜拳消息返回 `no_duel`。

| 下注 | 赢家到手 | 净赢 |
|---|---|---|
| 150 | 250 | 100 |
| 1500 | 2500 | 1000 |
| 15000 | 25000 | 10000 |

两人下注合计的六分之一被销毁。邀请等 `inviteSec`（15）秒，每局出拳 `throwSec`（10）秒。

- 资格：双方都要有存档，且累计敲击（`totals.taps`）满 `minTaps`（10000）。新存档自带 1600 碎片，游客存档能无限新建，这条门槛防止拿新存档给别的存档送碎片。不能邀请自己，也不能邀请同一存档的另一条连接；对方必须在同一个房间。一个存档同一时间只能有一场对局或一个待回应的邀请（发出的和收到的都算，跨房间也算）。
- 每日净赢上限：每个存档每个北京时间日期，已结算对局的（到手 − 下注）累加，输的局是负数，退款的局不算，这个数不能超过 `dailyWinCap`（10000）。输不设上限。某一档赢了会让任意一方当天的净赢超过上限时，这一档的邀请返回 `duel_cap`；接受时再按同样的规则查一次。对局的日期取扣款时的日期。
- 邀请：服务端把 `duel_invite {duel,from,to,bet,prize,sec}` 发给双方。被邀请方开了免打扰时，服务端直接替他拒绝，他收不到邀请，邀请方收到的 `duel_over` 和普通拒绝一样是 `declined`。免打扰在 `join` 的 dnd 或 `dnd` 消息里设置，不广播；客户端在设置打开或点击穿透打开时都算免打扰。被拒绝或超时后，同一邀请方 30 秒内不能再邀请同一存档（`duel_cooldown`）。
- 扣款：接受时在一个数据库事务里扣双方的下注，任何一方碎片不够就都不扣，双方收到 `duel_over` `no_shards`。扣款成功后双方收到 `duel_start {duel,round,sec}`。
- 出拳：双方各自发 `duel_throw`。一方出拳后，对方出拳前收不到任何消息。平局时双方收到 `duel_round {duel,round,sec,hands}`，hands 是这次平局的双方出拳（按成员 id），然后重来；连续平局 10 次后双方退款（`duel_over` `draws`）。一局到时只有一方出了拳，没出的一方输；双方都没出，双方退款（`duel_over` `idle`）。
- 掉线和离开：对局绑定在发起和接受时的那条连接上。这条连接离开房间（`leave`、断线、写入失败）算输，即使同一存档的另一条连接还在房间里；邀请阶段任何一方离开，邀请作废（`duel_over` `gone`）；被邀请方离开不算拒绝，邀请方离开和被拒绝一样要等 30 秒才能再邀请同一存档，免得离开再进来反复弹邀请。
- 结算：向全房间广播 `duel_result {duel,winner,loser,prize,hands}`（hands 里没出拳的一方为 null），随后为输家存档在这个房间里的每条连接广播 `sticker {id,key,sec}`：服务端从表情套 `economy.duel.sticker.set`（阿草）里随机挑一个表情 key，所有人看到同一张，贴 `sticker.sec`（300）秒。贴纸记在房间上、按存档记，之后进房间的成员在 `joined` 之后收到还没到期的 `sticker`，输家重连后也一样；房间回收时清空。客户端在赢家桌宠旁显示到手碎片，在输家桌宠头上贴这张表情。
- 只结算一次：出拳、超时、掉线、离开可能同时发生。服务端在内存里先把对局标为结束再访问数据库，数据库里用 `UPDATE duels SET state=... WHERE id=? AND state='open'` 的条件更新确认，只有第一次成功的结算发碎片。
- `duel_over` 的 reason：`declined`、`timeout`（邀请没回应）、`gone`、`no_shards`、`duel_cap`、`idle`、`draws`；后两种已退款。
- 余额：客户端收到 `duel_start`、`duel_result`、`duel_over` 后重新读一次 `GET /api/me`。

## 数据迁移

刮刮乐新增 `scratch_cards` 表和 `players.scratch_pity` 列，启动时自动补上。已揭开的卡保留 30 天，启动时清理更早的。

猜拳新增 `duels` 表（启动时自动创建）：扣款时写入一行，state 从 `open` 变为 `won`（winner 为赢家存档）或 `refunded`，只变一次。房间只在内存里，服务端重启后上次没结算的对局没法继续，启动时把 `open` 的对局全部退款。


首次启动新版本时，旧碎片乘 16，旧抽卡次数和箱余额每份换成 160 碎片，随后清零旧余额。迁移由 skin_pity 列的存在性标记，只执行一次。已拥有物品、draw_pity 大隐藏进度和 drawn_total 累计次数保留。发布前备份数据库并在备份副本验证换算；回滚时同时恢复匹配版本的数据库。
