# AsoulTappo 协议

## 身份与房间

HTTP 请求使用 `X-Player-Token`（16–128 字符）；客户端本地生成，服务端以 SHA-256 前 16 位标识玩家。登录主站账号后改用 `Authorization: Bearer <主站令牌>`，服务端向 `MAIN_API_URL/auth/me` 确认账号（结果缓存 5 分钟；主站连不上时沿用该令牌 1 小时内的上次结果，没有则返回 503 `account_unavailable`，失败后 15 秒内不再请求主站），再按 `account_links` 找到绑定的存档。游客存档绑定账号后，原来的 `X-Player-Token` 返回 401 `save_linked`。`GET /healthz` 返回服务状态，`POST /rooms` 返回随机房间号。房间在首次加入时创建、最后一个成员离开时回收，最多 20 人。

第一个进入房间的成员是房主；房主离开（包括连接因超时或积压被断开）后，房主传给剩下成员里最早进入的一位。房间默认私密，房主可以随时设为公开或改回私密，公开房间出现在 `GET /rooms` 里。设为公开要求房主带存档（见下），否则返回 `host_needs_save`。接入了主站账号的服务端（配置了 `MAIN_API_URL`）还要求房主这条连接加入时带了有效的 accountToken，否则返回 `host_needs_account`；两项都检查时先查账号，所以没登录的房主收到 `host_needs_account`，登录了但账号没绑定存档的收到 `host_needs_save`。改回私密不受这两条限制。房主传给没登录账号的成员时，房间保持公开，新房主可以改回私密，但不能再设为公开。公开以后，新加入的成员必须带存档；设为公开前已经在房间里的无存档成员留下。这里的带存档指加入时的 token 或 accountToken 能解析出存档，与 HTTP 接口的身份规则相同。

房主可以移出其他成员，不能移出自己。被移出成员的存档记在这个房间的封禁名单上，房间回收前这份存档无法再进入；同一存档在房间里的其他连接一起移出。无存档的成员也可以移出，但没有存档可封，他拿着房间号还能再进来（公开房间除外，因为公开房间不收无存档成员）。房主在另一条连接上的同一存档只移出、不封禁。房间回收后封禁名单随之清空。正在猜拳的成员（下注已扣）不能被移出，返回 `in_duel`。成员被移出房间（被移出、连接写入失败）后如果连接还没关，这条连接再发来的消息按未加入处理：`ping` 和 `join` 照常，其余返回 `not_joined`。房间没有文字聊天。

服务端重启会清空所有房间，客户端重连后按原房间号重新加入。服务端收到停止信号时记下每个房间的公开状态、房主的存档和封禁名单，重启后 10 分钟内有效：房间重新建起时带回封禁名单；原房主的存档回来时房主交还给它（向其他成员广播 `room_info`），房间原来公开的，这时一起恢复公开（接入了主站账号的服务端仍要求房主带了有效的 accountToken）。原房主回来之前，第一个回来的成员暂时当房主，房间保持私密。合力应援当前这一轮的进度不保留。

`GET /rooms` 在接入了主站账号的服务端上要求 `Authorization: Bearer <主站令牌>`：没带令牌返回 401 `account_required`，令牌无效返回 401 `account_expired`，主站连不上返回 503 `account_unavailable`；账号不必绑定存档。没接入账号的服务端不检查身份。凭房间号加入不受影响，游客存档照样能进公开房间。返回 `{rooms:[{room,host:{nick,character},members,max}, ...]}`：公开房间的房间号、房主昵称和显示的角色、当前人数和人数上限，最多 50 个。有空位的房间排在前面，同类按人数从多到少，人数相同按创建先后。满员房间照样列出。

WebSocket 地址为 `/ws`，每帧一个 JSON 对象。不是 JSON 文本或字段不合格式的帧返回 `error` `bad_message`，连接保持。

| 客户端 type | 字段 |
|---|---|
| join | room（1–64）、nick（1–24）、character（≤32，成员名或以成员名开头的皮肤名，如 `贝拉山海经`；存档未拥有的皮肤或未知名称改为显示名称开头的成员，都不匹配时显示第一位成员）、token（可选）、accountToken（可选，主站令牌，优先于 token）、plate（可选，铭牌 ID，存档未解锁或不认识时忽略）、dnd（可选，布尔，猜拳免打扰，见猜拳一节）、status（可选，联机状态 ID，见下）、motionVersion（可选，整数 ≥1，客户端能读的最新动作格式，见动作格式一节；不带为 1） |
| leave | 无 |
| tap | count（1–500），客户端每 100–200ms 合并；服务端按连接限速（每秒 15、最多攒 75），超出部分不广播。这只限制房间显示，每条连接各算各的，重连会重新计，不是每人总上限；收益只看 `POST /api/activity`，按存档共用一份额度（存在数据库里，并发、多连接、重连都不叠加） |
| motion | dx、dy（桌宠图层偏移，−20 至 20）、keyDown、left、right（按下状态）；移动每 100ms 合并，按键状态即时发送。格式 1 的客户端用它 |
| pose | x、y（四分之一像素，−80 至 80 的整数）、b（按键位：1 键盘、2 左键、4 右键，0 至 7），只带有变化的字段；格式 2 起的客户端用它代替 motion |
| motion_subscribe | ids（成员 id，最多 20 个）：要接收谁的动作。格式 2 起有效，格式 1 的连接发来会被忽略；每次发送替换上一次的名单 |
| poke | id（成员 id）：戳一戳同房间的另一位成员。每条连接每 3 秒最多一次，同一位成员 10 秒内只能戳一次，没到时间返回 `poke_cooldown`；id 不在房间里或是自己返回 `no_member`。只发给 `joined.features` 里有 `poke` 的服务端 |
| profile | id（成员 id，可以是自己）：要这位成员的主页。服务端回 `profile`，只发给请求的人。每条连接 0.3 秒最多一次，太快返回 `rate_limited`；id 不在房间里返回 `no_member`。只发给 `joined.features` 里有 `profile` 的服务端 |
| emote | emote（≤32），表情 key；初始表情免费，其余验证所有权 |
| state | character、nick、plate、status，至少提供一个；plate 为空字符串时取下铭牌，status 为空字符串或不在列表里时不显示状态。character 为存档未拥有的皮肤（或未知名称）、plate 未解锁时返回 `locked` 并忽略整条消息 |
| ping | 无 |
| set_public | public（布尔），仅房主；值有变化时向全房间广播 `room_info`，没有变化时只把当前的 `room_info` 回给房主 |
| kick | id（成员 id），仅房主；不是房主返回 `not_host`，id 不在房间里或是房主自己返回 `no_member`，要移出的连接正在猜拳返回 `in_duel` |
| dnd | dnd（布尔），猜拳免打扰开关；只发给有猜拳的服务端 |
| duel_invite | id（成员 id）、bet（下注，必须是 `economy.duel.stakes` 里的一档） |
| duel_answer | duel（对局 id）、accept（布尔），只有被邀请的一方能回应 |
| duel_throw | duel、hand（`rock` / `scissors` / `paper`），每局只认第一次 |

服务端消息：`joined {room,you,members,info,features,cheer}`、`cheer {target,minShare,total,shares,rounds}`、`cheer_done {round,rewards}`（合力应援，见下文）、`profile {id,showcase,progress}`（回给请求的人：showcase 为这位成员存档里选的展示卡 ID，最多 3 张，没选时为空；progress 为 `{cards,emotes,skins}`，每项 `[已拥有, 总数]`，计法和图鉴一致，初始表情算已拥有；没有存档的成员为 null）、`poke {from,to,quiet?}`（全房间都收到，包括发起人；被戳的人开了猜拳免打扰时，发给被戳者的那份带 `quiet: true`，客户端只让桌宠弹一下，不出气泡）、`room_info {host,public}`、`member_joined {member}`、`member_left {id}`、`tap {id,count,total}`、`motion {id,dx,dy,keyDown,left,right}`、`motion_batch {motions:[{id,dx,dy,keyDown,left,right}, ...]}`、`motion_snapshot`、`motion_delta`、`motion_edge`、`motion_edges`（见动作格式一节）、`emote {id,emote}`、`scratch {id,shards}`、`state {id,character,nick,plate,status}`、`duel_invite`、`duel_start`、`duel_round`、`duel_result`、`duel_over`（猜拳一节）、`pong`、`error {code,message,reason?}`。`features` 列出这个服务端在 1.1 之外支持的房间消息，现在是 `["poke", "profile", "cheer", "status"]`，`features` 和 `cheer` 只发给加入时带了 motionVersion（2 及以上）的客户端，更早的客户端收到的 `joined` 保持原样；旧服务端没有这个字段。`info` 和 `room_info` 是房间级状态：host 为房主的成员 id，public 表示房间是否公开；房主变化或公开状态变化时服务端广播 `room_info`。成员包含 `id,uid,nick,character,taps,motion,plate,status`，plate 为经服务端核对的铭牌 ID，没有时为 null；status 为联机状态 ID，只能是 `fish`（摸鱼）、`work`（工作）、`study`（学习）、`game`（打游戏）、`music`（听歌）、`live`（看直播）之一（`rooms.ROOM_STATUSES`），其他值一律当作没有，没有时为 null。状态由玩家自己选，只在内存里随连接保存。之前的服务端不认识 status，而且 state 至少要有 character、nick、plate 之一，所以客户端改状态时连同昵称一起发；加入时的 motion 为该成员最近一次桌宠动作。`uid = sha256(player_id + ':' + room)[:10]` 用于记录同桌位置。

合力应援：存档上报 `/api/activity` 后，服务端把这次计入收益的敲击（每分钟前 120 下，已过防连点冷却）加到这份存档最近加入的房间的应援条上；累计敲击不满 1 万下的存档不计入。房间里至少有 2 份不同存档时条才会涨。一份存档本轮出力满 50 下就算出力，从这时起它的出力才上条（不满 50 下的先记着，不上条）；条的目标是 300 × 出力人数（至少按 2 人算），所以满条等于出力的人平均每人 300 下，很多人各敲几十下凑不满条；条满并且至少 2 人出力时这一轮结束，每位出力的存档得 10 × 出力人数 碎片（账本来源 `cheer`，每份存档每天最多 1000），条清零。中途加入：出力立刻上条，满 50 下后计入人数，目标和每人奖励随之变大。中途离开：已出的力留在条上；离开后 60 秒内仍计入人数、仍能领本轮奖励（掉线重连的同一份存档接着算），过了 60 秒不再计入人数，但已上条的出力留在条上，目标随之变小，下一次有人上报时再判断是否满条。`cheer` 为条的现状：`target` 为当前目标，`total` 为已上条的出力（不超过 `target`），`shares` 为在场成员（按成员 id）本轮的出力，包括还没满 50 下的，`count` 为出力人数，`reward` 为现在满条时每人能得的碎片，`rounds` 为这个房间完成的轮数；条在涨时最多每 2 秒发一次，有人离开时、一轮结束后（跟在 `cheer_done` 后面）也发，加入时放在 `joined.cheer` 里。`cheer_done.rewards` 为这一轮每位在场得奖成员拿到的碎片，当天已到上限的为 0。状态里的 `cheer {day,got,cap,minTaps}` 为当天从应援拿到的碎片、每日上限和参与门槛。

### 动作格式

加入时客户端用 motionVersion 说明自己能读的最新格式，服务端取它和自己支持的最新格式（现在是 3）中较小的一个，格式 2 起在 `joined` 里回 `motionVersion`。旧服务端不认识这个字段，不回 motionVersion，客户端就按格式 1 收发。1.1.4 的服务端只接受 1 和 2，带 3 的 join 会被整条拒绝（`bad_message`），客户端收到后用 2 重发一次 join，之后对这个服务端一直用 2。

- 格式 1：收发完整动作。连续位移由服务端按房间每 100ms 汇总为一条 `motion_batch`，每个成员保留最新位置；按键、左右键边沿即时发送 `motion`。
- 格式 2：客户端发 `pose`。服务端只发 `motion_subscribe` 名单里的成员，字段同 `pose`，只带相对这条连接上次收到的值有变化的字段：订阅时对新加进名单的成员发 `motion_snapshot {motions:[{id,x,y,b}, ...]}`（完整值），连续位移每 100ms 一条 `motion_delta {motions:[{id,...}, ...]}`，按键边沿即时发 `motion_edge {id,...}`。
- 格式 3：同格式 2，按键边沿改为每 50ms 汇总：`motion_edges {edges:[{id,...}, ...]}` 按发生顺序排列，同一成员可以出现多次，短按的按下和松开都在里面。一个成员在一批里最多保留 6 个边沿，多出的丢掉最早的，最后的状态总会发出。边沿批次先于同一时刻的 `motion_delta` 发出，位置不会抢在边沿前面。20 人房间全员打字时，单个客户端收到的动作消息从每秒约 250 条降到约 20 条，压缩后流量少约 37%（`scripts/benchmark_server.py`）。

同一房间里各连接的格式可以不同，服务端按每条连接的格式分别发送。入房、离房、表情和敲击消息按连接顺序发送。动作仅发给同房间的其他成员。每个连接独立发送，连续位置批次合并，发送超时或有序消息积压达到 256 条时断开该连接。客户端将短按状态保持至少 70ms，供桌宠呈现点击和按键动作。

连接关闭时清除成员动作，重连后发送当前动作；敲击计数由 `tap` 累计。本次协议更新配套发布客户端和服务端。

### 错误码

| code | 含义 |
|---|---|
| bad_message | 帧不是 JSON 或字段不合格式；加入请求被判为无效时客户端停止重连 |
| not_joined / already_joined | 没加入就发送房间消息 / 重复加入 |
| room_full | 结束这次会话：客户端收到后停止重连。不带 reason 时表示房间已满（20 人）；带 reason 时见下 |
| locked | 表情、皮肤或铭牌未解锁，整条消息被忽略 |
| rate_limited | 表情发得太快 |
| poke_cooldown | 戳一戳太快：每条连接 3 秒一次，同一位成员 10 秒一次 |
| not_host | 非房主发送 `set_public` 或 `kick` |
| no_member | `kick` 的 id 不在房间里或是房主自己；`poke` 的 id 不在房间里或是自己 |
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
- 猜拳：旧客户端忽略 `duel_*` 消息（`RoomClient` 不认识的类型直接丢弃），成员字段没有变化；它收不到也回应不了邀请，邀请它的人 15 秒后看到超时。新客户端只在 `GET /api/me` 带 `duel` 时显示猜拳键、发送 `dnd` 和猜拳消息；旧服务端的状态没有这一项。`join` 里的 dnd 只在打开时带上，旧服务端忽略多出来的字段。

## HTTP API

| 路由 | 请求与响应 |
|---|---|
| GET /api/manifest | v4 素材清单，与 `assets-packs/manifest.json` 一致，包含 skins 和 economy |
| GET /api/me | player、shards、income、dailyTaps、resonance、totals、checkin、tapCooldown、scratch、duel（`{net}`，今天猜拳的净赢；没有猜拳的服务端不带）、cheer（`{day,got,cap,minTaps}`，见合力应援）、updateRewards（进行中且这个存档还没领的更新奖励 `[{id,version,shards}]`，按创建先后）、park（`{coins,news}`，见游乐园一节；没有游乐园的服务端不带） |
| POST /api/activity | `{taps,session,sequence,cooldown?}`，返回状态和 credited；cooldown 是客户端自己触发冷却后剩余的秒数 |
| POST /api/presence | `{session}`，记录在线并返回状态；在线本身不给碎片 |
| POST /api/resonance/draw | `{count}`，count 为 1–100，实际次数取 count、100、余额可支付次数的最小值，返回状态和 drops。皮肤池按 `X-Client-Version` 过滤，见共鸣一节 |
| POST /api/craft | `{item}`，兑换未拥有的普通卡，以及普通、罕见、稀有表情，返回状态和 item |
| GET /api/checkin | 签到日历：today（北京时间日期）、available（今天还能不能签）、days（本月已签的 `{day,prize,shards}`，按日期排列，prize 为奖励档下标） |
| POST /api/checkin | 每日签到，每个存档每天一次，北京时间（UTC+8）零点刷新。服务端按 manifest `economy.checkin.prizes` 的权重抽一档，实发碎片在该档数额上下浮动 `economy.checkin.spread`（均匀分布，0.1 即 ±10%，四舍五入取整），返回状态和 `prize:{index,shards,day}`，index 为奖励档的下标；当天已签返回 409 `checked_in` |
| POST /api/update-reward | 领取更新奖励：`X-Client-Version` 不低于奖励版本的、进行中且还没领的奖励一次全部发放，返回状态和 `reward:{shards,ids}`。预发布版本低于同号正式版。没有可领的返回 409 `no_reward` |
| GET /api/park | 游乐园状态（见游乐园一节）：coins、unlocked、bought、buyLeft、gift、stamps、stampsTotal、badge、today、jackpot |
| POST /api/park/coins | `{count}`，用碎片买驼币，返回状态和 `park`。见游乐园一节的错误码 |
| POST /api/park/gift | 领今天送的驼币，返回状态、`park` 和 `gift`（这次到账的枚数，今天领过时为 0） |
| POST /api/redeem | `{code}`，兑换码：返回状态、`park`（有游乐园的服务端才带）和 `redeemed:{shards,coins}`。错误码和防猜码见游乐园一节的兑换码 |
| GET /api/scratch | 刮刮乐状态：day（北京时间日期）、left（今天还能买几张）、pity（距上次出阿草表情已买的张数）、card（已买未揭开的卡 `{id,cells}`，没有时为 null） |
| POST /api/scratch | 买一张刮刮乐，返回状态和 `card:{id,cells}`。已有未揭开的卡时原样返回这张卡，不再扣费。当天卖完返回 409 `sold_out`，碎片不足返回 409 `no_shards` |
| POST /api/scratch/reveal | `{card}`，揭开这张卡并发放奖品，返回状态和 `prize:{shards,item}`。重复揭开返回同一份奖品，不再发放；卡不存在或不属于该存档返回 404 `no_card` |
| GET /api/collection | owned（物品 ID → 数量）、recent（最近获得记录） |
| GET /api/loadout | character、favorites、plate、showcase、nick、board |
| POST /api/loadout | 更新 character、favorites（最多 8 个且已拥有）或 plate；五位原皮直接可用，皮肤要求已拥有；plate 必须是已解锁的铭牌 ID，null 或空字符串取下铭牌；不是铭牌的 ID 返回 `bad_item`，未集齐返回 `locked`；showcase 为主页展示卡的卡片 ID 列表，最多 3 张、必须已拥有，超过或不认识返回 `bad_item`，未拥有返回 `locked`，空列表清空；nick 为收藏榜上显示的昵称（最多 24 字，空字符串用默认昵称），board 为 false 时不上收藏榜。这两项客户端只上传，读取装备时不会覆盖本地设置 |
| GET /api/board | 全服收藏榜。`order` 为 `score`（按收藏分，显示收藏分的客户端）或 `cards`（默认，按卡片数，之前的客户端）。`cards`（前 50：`[{id,rank,nick,character,plate,cards,big,skins,score}]`，cards、big、skins 为卡片、大隐藏、皮肤数量，score 为收藏分；order=score 时按收藏分、大隐藏数、最后一件计分物品的获得时间排序，order=cards 时按卡片数、大隐藏数、最后一张卡的获得时间排序，只列有卡片的存档；昵称取 loadout 的 nick，为空时取这个存档最近一次在房间里用的昵称（加入或改名时记录，默认昵称不记），都没有时为默认昵称，经屏蔽词处理；铭牌未集齐时为 null）、`total`（卡片总数）、`points`（收藏分表，见下）、`me`（`{rank,cards,big,skins,score,off}`，rank 为所选排序下的名次，off 为 `hidden`（自己关了上榜）、`account`（服务端启用了主站账号而存档未关联）或 null）。榜单每 5 分钟重算一次 |
| GET /api/board/profile/{id} | 收藏榜前 50 里某一行（`id`）的主页：`{showcase,progress}`，格式同房间消息 `profile`；不在榜上返回 404 `no_member` |
| GET /api/info | accountLogin（是否接入主站账号）、mainApi（主站 API 地址，未接入时为 null） |
| GET /api/client/release | 最新客户端版本 version 和更新说明 notes，读自主站 `/tappo/release`（未配置 `MAIN_API_URL` 时读官方主站），缓存 10 分钟；查不到时返回 503 `release_unavailable`。同时返回 minVersion（服务端要求的最低客户端版本，未设置时为 null）和 announcements（未过期的公告，每项 `{id,title,body,until,daily}`；daily 为 true 时客户端每个北京时间日第一次打开面板都显示，直到玩家选不再出现，1.2.2 以前的客户端只显示一次）。客户端用它检查更新，安装包仍由 Tauri 更新器从 GitHub 下载，失败时打开主站下载页 |
| GET /api/account | Bearer；user、save（账号存档摘要，未绑定时为 null） |
| POST /api/account/link | Bearer，可带 `X-Player-Token`。账号未绑定时把这份游客存档（或新存档）绑定到账号，返回 user、save、linkedGuest；账号已有存档且游客存档玩过时返回 409 `account_has_save`，附 account 和 guest 两份摘要；游客存档已属于其他账号时返回 401 `save_linked` |
| GET /packs/index.json | 素材文件路径、大小及 SHA-256 |
| GET /packs/... | 卡面原图及主题动画资源 |

收藏分按每件物品平均要抽几次折算，1 分约等于 1 抽：大隐藏 300 分（0.1%，400 抽保底，平均约 330 抽），皮肤 150 分（0.2%，200 抽保底，平均约 165 抽），史诗卡 20 分（10 张小隐藏和 13 张史诗普通款同在 4.5% 的史诗档，约 22 抽一张），普通卡 2 分。表情约按合成价（480、960、1600 碎片）的一半计分：普通 1、罕见 2、稀有 3，阿草表情按稀有算，初始表情不计分。`points` 为 `{big,skin,epic,card,emoteRare,emoteScratch,emoteUncommon,emote}` 各一件的分数，客户端据此显示分数表。之前的客户端不带 order，看到的仍是按卡片数的排名；它们都不在线后，order 的默认值可以改为 score。

从 1.1.4 起，状态中的 `dailyTaps` 为 `{day,count}`，day 是北京时间日期，count 是当天全部有效敲击数，包含每分钟收益上限以外的有效敲击。`income.taps` 继续记录参与碎片收益计算的次数。客户端的今日计数也按北京时间换日，并使用 `dailyTaps` 跨设备同步。旧库升级时以已有的当日收益计数初始化新统计，后续按全部有效敲击累加。

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
  "income": { "day": "2026-11-10", "today": 3716, "cap": 18000, "taps": 2820, "perTap": 1.079, "multiplier": 1, "perMinute": 64.8 },
  "dailyTaps": { "day": "2026-11-10", "count": 3200 },
  "resonance": {
    "pity": { "legendary": 212, "skin": 87 },
    "hardPity": { "legendary": 400, "skin": 200 },
    "total": 1234
  },
  "totals": { "taps": 3200, "activeMinutes": 0, "owned": 0, "items": 569 },
  "checkin": { "available": true },
  "tapCooldown": 0,
  "scratch": { "left": 20, "pity": 0 }
}
```

错误沿用 `{detail:{code,message}}`，碎片不足为 `no_shards`（409），兑换已拥有物品为 `owned`（409），装备未拥有皮肤为 `locked`（400）。

## 管理接口

主站后台用来查看和管理桌宠账号。服务端配置 `ASOULTAPPO_ADMIN_KEY` 后启用，请求需带 `X-Admin-Key`；未配置或密钥不符时一律返回 404。改动类请求可带 `X-Admin-Actor`（主站管理员的用户名，按 URL 编码），记进管理操作日志。`/admin` 不经过公网反向代理，只由同机的主站 API 访问。统计按北京时间（UTC+8）切分日期；当天有活动上报（敲击被计入）或在线心跳的存档记为活跃。

| 路由 | 请求与响应 |
|---|---|
| GET /admin/stats?days= | days 为 1–180，默认 30。totals：saves（存档数）、linked（已绑定账号）、guests（游客存档）、activeToday、rooms、online；series：每天一行 `{day,active,newSaves,items}`，从旧到新 |
| GET /admin/accounts?ids=&offset=&limit= | 已绑定账号的存档，按最近活动倒序；ids 为逗号分隔的主站用户 ID（最多 100 个），用于按主站搜索结果筛选。返回 total、accounts（`userId,linkedAt,shards,owned,taps,lastActive`） |
| POST /admin/accounts/{userId}/shards | `{delta,reason?}`，正数补发、负数扣减，扣到负数时返回 409 `no_shards`；返回新的 shards。reason 最多 200 字，记进管理操作日志 |
| POST /admin/accounts/{userId}/unlink | 可带 `{reason}`。解除绑定。存档保留，原游客令牌恢复可用，账号可以重新绑定 |
| GET /admin/economy?days=&scope=&newDays= | 碎片流水按天汇总。days 为 1–90，默认 14；scope 为 `all`（默认）或 `new`；newDays 为 1–30，默认 7。返回 `{scope,newDays,cap,series}`，cap 为每日敲击收入上限；series 每天一行，从旧到新，没有数据的日期也有一行。每行 `{day,players,issued,spent,sources,draws,taps,capped}`：players 为当天有流水的存档数；issued、spent 分别为正数流水之和、负数流水之和（取正值）；sources 为 `{来源:{amount,count}}`；draws 为当天共鸣次数；taps 为 `{players,p50,p90,max}`，按每个存档当天计入的敲击数统计，百分位取最近秩（nearest-rank），没人敲击时全为 0；capped 为当天敲击碎片达到 cap - 1 的存档数（整数取整可能差最后 1 个碎片）。scope=new 只统计创建日期距当天少于 newDays 天的存档，newDays=1 即只看创建当天 |
| GET /admin/saves?q=&limit= | 查找存档，含游客存档。q 按主站用户 ID 精确匹配绑定的存档；q 为 4–16 位十六进制时，同时按存档 ID 前缀匹配（不分大小写），两者合并。q 缺省或为空返回 422，只有空白或匹配不到时返回空列表。limit 为 1–50，默认 20。返回 `{saves:[...]}`，按最近活动倒序，每项 `{player,userId,created,lastActive,shards,owned,taps,drawn,tapCooldown,clientVersion}`；userId 为绑定的主站用户 ID，游客存档为 null；tapCooldown 为敲击冷却剩余秒数；clientVersion 为这份存档最近一次请求的客户端版本，没有记录时为 null |
| GET /admin/saves/{player} | 单个存档详情：上一行的字段，加 pity `{legendary,skin,scratch}`、today `{day,taps,tapShards}`（当天计入的敲击数和敲击得到的碎片）、recent（最近获得的物品，同 `/api/collection`）、ledger（最近 7 天流水，`[{day,sources}]`，从旧到新）、log（这份存档最近 20 条管理操作，格式同 `/admin/log`）。存档不存在时返回 409 `no_save` |
| POST /admin/saves/{player}/shards | `{delta,reason?}`，调整任意存档（含游客存档）的碎片，规则同 `/admin/accounts/{userId}/shards`；存档不存在时返回 409 `no_save` |
| GET /admin/log?player=&limit=&before= | 管理操作日志，新的在前。player 只看一份存档；limit 为 1–200，默认 50；before 为条目 id，接着往下翻。返回 `{entries:[{id,ts,actor,action,player,detail,reason}]}`：action 为 `shards`（detail `{delta,shards}`）、`unlink`（`{userId}`）、`reward_open`（`{version,shards}`）、`reward_end`（`{id,version}`）、`notice`（`{minVersion,announcements}`，公告只记标题）、`blocked_words`（`{count}`）、`code_create`（`{ids,count,shards,coins,uses,expires,custom}`，ids 为这批第一个和最后一个码的 id，reason 为备注）、`code_disable`（`{id,code}`）；player 不涉及存档时为 null。拒绝的改动不记 |
| GET /admin/insights?days= | 概况。days 为 1–90，默认 30。返回 `{today,retention,activeDays,active,versions,collection,drops,rarities}`。retention 每个创建日一行 `{day,size,d1,d3,d7}`：size 为当天新建的存档数，dN 为其中第 N 天又活跃的个数，那一天还没过完时为 null。activeDays 为 7，active 为近 7 天活跃的存档数；versions 为这些存档的客户端版本分布（`[{name,count}]`，没有记录的为 `unknown`，不是版本号的为 `other`；从新到旧）。collection `{total,saves}`：saves[k] 为近 7 天活跃、持有 k 张卡的存档数。drops 每天一行 `{day,rarities:{稀有度:{count,new}}}`，为共鸣、兑换和刮刮乐得到的物品数及其中新物品数；rarities 为稀有度的显示名，含 `skin` |
| GET /admin/online?days= | 联机。days 为 1–90，默认 14。返回 `{today,now,series,recent,recentStep}`。now 为此刻的 `{rooms,members,saves,largest,public}`：有成员的房间数、成员数、其中不同存档数、最大房间人数、公开列出的房间数。series 每天一行 `{day,samples,peakMembers,peakRooms,peakSaves,avgMembers,sharedMinutes,counts,duels,cheer}`：服务端每分钟记一次房间采样，samples 为当天采样数（服务端停机时没有采样），sharedMinutes 为有房间至少两人的分钟数；counts 为当天次数 `{room_join,poke,profile,board_profile,emote,duel_invite,cheer_round}`（进房间、戳一戳、房间里看主页、收藏榜看主页、表情、猜拳邀请、应援满条）；duels `{played,bets:{下注:局数}}` 为当天结束的猜拳局数；cheer `{shards,saves}` 为当天应援发出的碎片和领到的存档数。recent 为最近 24 小时，每 recentStep（10）分钟一个点 `{ts,rooms,members,saves}`，取那段时间的最大值 |
| GET /admin/anomalies?day= | 异常。day 为 `YYYY-MM-DD`，默认今天。返回 `{day,tapCap,taps,heavy,shards}`。taps 为当天有标记的存档，按匀速冷却次数、服务端冷却次数、被丢弃的敲击数倒序，最多 50 个 `{player,userId,credited,dropped,serverCooldowns,clientCooldowns,steadyCooldowns,tapShards}`：dropped 为上报了但没有计入的敲击（超过速率或冷却中），serverCooldowns 为服务端判定连续过快而开始的冷却次数，clientCooldowns 为客户端自己的防连点开始的冷却次数，steadyCooldowns 为服务端判定匀速而开始的冷却次数，credited、tapShards 为当天计入的敲击和敲击碎片。heavy 为当天计入敲击最多的 20 个存档，格式同 taps（速度有起伏又没到冷却线的连点器只会出现在这里）。shards 为当天靠玩法得到碎片最多的 50 个存档 `{player,userId,gained,sources}`，不算初始碎片、更新奖励、兑换码和后台调整 |
| GET /admin/blocked-words | 昵称屏蔽词表，返回 `{words,count}`，按上次保存时的顺序 |
| PUT /admin/blocked-words | `{words:[...]}`，整表替换。每个词去掉首尾空白后为 1–64 个字符，最多 20000 个（按去重前的个数算），不符合时返回 422 且词表不变；去重后保存原词（不保存折叠结果）。返回 `{count}`，为去重后的个数。新词表立即对在线成员生效，见下节 |

账号没有绑定存档时返回 409 `account_not_linked`。

碎片流水：服务端在每次碎片变动的同一事务里记一笔，按北京时间日期、存档和来源累加金额（amount，获得为正、花费为负）和次数（count）。流水从带这张表的服务端版本开始记录，之前的变动没有历史数据。来源如下：

| 来源 | 金额 | 次数 |
|---|---|---|
| `starter` | 新存档的初始碎片 | 1 |
| `tap` | 敲击得到的整数碎片 | 计入的敲击数，含超过收入上限的部分 |
| `draw` | 共鸣花费 | 共鸣次数 |
| `duplicate` | 重复物品兑换的碎片 | 兑换成碎片的物品数 |
| `craft` | 兑换物品花费 | 1 |
| `checkin` | 签到奖励 | 1 |
| `cheer` | 合力应援满条的奖励（受每日上限） | 1 |
| `update` | 更新奖励 | 一次领取的奖励个数 |
| `scratch_buy`、`scratch_prize` | 刮刮乐购买花费、刮开时的碎片奖励（只在有碎片时记） | 1 |
| `duel_bet`、`duel_prize`、`duel_refund` | 猜拳双方的下注、胜者奖金、无胜者时退回的下注（后两项按结算当天记） | 1 |
| `coin_buy` | 买驼币花费 | 买的枚数 |
| `park_scratch`、`jackpot`、`race_prize`、`lottery_prize` | 游乐园的碎片奖：驼币刮刮乐、全服奖池、团子赛跑、每日夺宝 | 1 |
| `redeem` | 兑换码发的碎片 | 1 |
| `admin` | 管理接口的调整 | 1 |

同一存档同一天的多次 `admin` 调整合并为一行，正负相抵，所以 `admin` 在 issued、spent 里是净值。

### 最低版本与公告

| 接口 | 说明 |
| --- | --- |
| GET /admin/notice | minVersion 和 announcements（含已过期的） |
| PUT /admin/notice | 整体替换。minVersion 为空字符串时取消限制；announcements 最多 20 条，每条 id、title（最多 40 字）、body（最多 2000 字）、until（Unix 秒，0 为不过期）、daily（布尔，缺省 false） |

客户端从 1.1.3 起在每个 HTTP 请求里带 `X-Client-Version`，房间连接地址带 `?v=`。设置 minVersion 后，版本更低或没有带版本的请求返回 426 `client_outdated`，加入房间收到 reason 为 `client_outdated` 的最终拒绝；`GET /api/client/release` 不受限制。1.1.3 及以后的客户端读到 minVersion 高于自己时，更新弹窗不能关闭；更早的客户端不带版本，只会看到请求失败。公告在面板打开时每条显示一次，已读记录在本机。`scripts/notice.py` 是这两个接口的命令行包装。

### 更新奖励

| 接口 | 说明 |
| --- | --- |
| GET /admin/update-rewards | `{rewards:[...]}`，从新到旧，每项 `{id,version,shards,created,ended,claims,paid}`；ended 为结束时间（Unix 秒），进行中为 null；claims 为领取的存档数，paid 为已发出的碎片 |
| POST /admin/update-rewards | `{version,shards}`，新建奖励：客户端版本不低于 version 的存档各能领一次 shards（1–1000000）。version 格式不对返回 400 `bad_version`；同一版本已有进行中的奖励返回 409 `reward_open`。返回同 GET |
| POST /admin/update-rewards/{id}/end | 结束奖励，没领的存档不能再领。奖励不存在或已结束返回 409 `no_reward`（不用 404，主站把 404 当作服务不可用）。返回同 GET |

新建档也能领，奖励按存档发，不看存档创建时间。客户端在面板里弹出可领的奖励，只列出自己版本够得着的。

### 兑换码管理

码的格式和兑换规则见游乐园一节的兑换码。每个码在下列接口里表示为 `{id,code,custom,shards,coins,uses,used,expires,disabled,note,createdBy,created}`：code 为显示形式（生成的码分三段）；custom 为管理员自己写的码；uses 为可用次数，used 为已兑换次数；expires 为过期时间（Unix 秒），不过期为 null；disabled 为停用时间，没停用为 null；createdBy 为生成它的主站管理员。

| 接口 | 说明 |
| --- | --- |
| POST /admin/codes | `{shards,coins,count,uses,expires,note,code}`，生成兑换码。shards 0–1000000、coins 0–1000，两者至少一个大于 0，否则返回 400 `bad_reward`；没有游乐园的服务端 coins 必须为 0。count 为 1–500（默认 1），uses 为每个码的可用次数 1–1000000（默认 1），expires 为 Unix 秒（0 或缺省为不过期，已过去的时间返回 400 `bad_expiry`），note 最多 200 字。code 为自定义码，可选：带 code 时 count 只能为 1（否则 400 `bad_count`），格式不对返回 400 `bad_code_text`，已有同样的码返回 409 `code_taken`。返回 `{codes:[...]}`，按生成顺序 |
| GET /admin/codes?q=&limit=&before= | 列表，新的在前。q 匹配码的一部分（不分大小写，忽略 `-` 和空白）或备注的一部分；limit 为 1–500，默认 50；before 为码的 id，接着往下翻。返回 `{codes:[...]}` |
| POST /admin/codes/{id}/disable | 可带 `{reason}`（最多 200 字，缺省时日志里记这个码的备注）。停用后立刻不能再兑换，已停用的再停用不变。返回这个码。码不存在返回 409 `no_code` |
| GET /admin/codes/{id}/claims?limit= | 兑换记录，新的在前，limit 为 1–1000，默认 200。返回 `{code,claims:[{player,userId,ts}]}`，userId 为存档绑定的主站用户 ID，游客存档为 null。码不存在返回 409 `no_code` |

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

客户端每 20 秒发送心跳和累计敲击数。碎片只来自敲击，在线本身不给碎片。每个北京时间自然日按当天计入的敲击数 n 累计发放 `dailyCap × (1 − e^−x)` 碎片，x = a·m + b·m² + c·m³，m 是 n 除以 1000：开头每下约 1.6 碎片，1 万下累计 9000，2 万下 13000，3 万下 16000，之后逐渐接近每天上限 18000、不会超过；每下不到 0.01 时（约 4.9 万下、17971 碎片）状态里的 `perTap` 记为 0，客户端显示今日已满。次日零点重新计算。每个 UTC 分钟只有前 120 下计入 n，超出的仍计入总敲击数和活跃分钟。小数碎片留到下次结算。参数在 manifest `economy.income`：`dailyCap`（18000）、`curve`（[a, b, c] = [0.0890449, -0.00269613, 7.23108e-05]）、`tapsPerMinute`（120）。管理接口里的到顶人数按 17971 算。

状态里的 `income`：`day` 是这些数字所属的北京时间日期（YYYY-MM-DD），`today` 是今天已从敲击拿到的碎片，`cap` 是每天上限，`taps` 是今天计入的敲击数，`perTap` 是下一下值多少碎片（达到上限后为 0）。`multiplier` 固定为 1、`perMinute` 为 `perTap × 60`，只给 1.0 版客户端显示，新客户端不读。

服务端只接收敲击次数，按每秒 15 下限速；相同 session 的 sequence 去重。同一 session 相邻两次上报之间平均每秒 10 下及以上算过快，过快连续 30 秒及以上时，这份存档进入 60 秒冷却：触发的那一批和冷却期间所有 session 的上报都不计入，也不给碎片。状态里的 `tapCooldown` 是冷却剩余秒数，没有冷却时为 0。客户端按同样的门槛逐秒判断（连续 30 秒每秒都有 10 下及以上），触发后 60 秒内不计数、不广播敲击，并在桌宠上方提示剩余秒数；触发时立刻上报一批（没有敲击也报），带上 `cooldown` 剩余秒数，服务端据此让这份存档进入冷却（最多 60 秒，只会延长不会缩短），这一批不计入。服务端判定的冷却客户端也照样显示。

匀速判定：同一 session 的每一批（与上一批间隔至少 5 秒）按 `敲击数 ÷ 间隔秒数` 算速度，每秒不到 0.2 下的不判断并重新开始。一批的敲击数与这一段的平均速度乘间隔相差不超过 8% 再加 1 下，算同一段匀速；中间夹一批对不上的会被跳过，连续两批对不上才从这一批重新开始。同一段匀速连续 30 批（客户端 20 秒一批，约 10 分钟），这份存档进入匀速冷却：触发的那一批和冷却期间的上报都不计入，也不给碎片，`tapCooldown` 同样是剩余秒数。匀速冷却当天第一次 600 秒，同一个北京时间日每多一次翻倍，最长 14400 秒。冷却期间客户端不再上报，所以当天被抓过的存档，之后连续 6 批都落在被抓时的速度上就直接再次触发，不必再等 30 批。判断按上报的敲击数算，速度没到 10 下也会触发。

每个 UTC 分钟累计 10 下计一个活跃分钟。

## 共鸣与兑换

五位成员共用一个池子，所有非初始卡片、表情和皮肤一起参与共鸣。三张心宜与思诺共有卡各自只入池一次，共用同一个拥有记录。可抽内容共 552 件：85 张卡、455 张表情、12 款皮肤。

清单 `skins` 每项为 `{name, member, title?, since?}`。name 是皮肤 ID（素材目录、`char:<name>` 物品、房间的 character 字段），以成员名开头，之后不再改动；title 是界面上显示的名称（成员名加皮肤自己的名字，如 `嘉然帝江`），没有时显示 name；since 是带上这款皮肤图片的客户端版本（x.y.z）。共鸣时客户端版本低于 since 的，这款皮肤不进它的皮肤池；预发布版本按对应正式版算（1.2.0-rc.3 算 1.2.0），不带版本或版本读不出时，带 since 的皮肤都不进池。这样老客户端不会抽到自己显示不了的皮肤。客户端把 since 最新的那一批皮肤作为开屏公告展示一次。

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
| 2500 碎片 | 3% | — |
| 1000 碎片 | 8% | — |
| 500 碎片 | 20% | — |
| 200 碎片 | 25% | — |
| 没中 | 38.9% | — |

奖品在买卡时由一次随机数决定，揭开时才发放，所以买卡后的余额只少了卡价。一个存档同时只有一张未揭开的卡；未揭开的卡跨天仍可揭开。碎片奖品平均返还卡价的 67%（每张 335）。

阿草表情是表情套 `achao` 的 20 个表情（`source: "scratch"`），只从刮刮乐获得，不进共鸣池，也不能兑换。每次给一个存档还没有的；保底按买卡张数累计，出表情时清零，计数方式与共鸣保底相同。

20 个集齐后没有表情这一档，也不再触发保底：只按碎片奖品的权重抽，表情的 5% 并入没中，没中为 43.9%，不给重复表情。是否集齐在买卡时判断，拿到最后一个表情的那张卡揭开之后，下一张才按集齐后的规则抽。集齐后 `pity` 不再变化；最后一个表情出现时已清零，所以通常是 0。

`cells` 是九个格子的图案，碎片数额写成数字串，表情写成表情 key。中奖图案恰好出现三次，其余图案最多出现两次，其中最大的数额（30000）最多出现一次；没中的卡没有出现三次的图案。

揭开的碎片奖品达到 `economy.scratch.announce`（2500）时，服务端向该存档所在的每个房间广播 `scratch {id,shards}`，客户端在这位成员的桌宠上方显示。出表情由客户端在揭开后发送这个表情。

## 游乐园

1.2.1 之后的客户端。配置在 manifest `economy.park`（`coin`、`scratch`、`race`、`lottery`），没有这一项的服务端不提供游乐园，状态里也没有 `park`，接口返回 404 `no_park`。

### 驼币

- 用碎片买，每枚 `coin.price`（500）。每个存档每天最多买 `coin.dailyBuy`（40）枚，北京时间零点重置；持有 `coin.hold`（100）枚时不能再买。驼币不能换回碎片，也不能转让。
- 每天送 `coin.gift`（1）枚：客户端第一次打开游乐园时调 `POST /api/park/gift`，当天再调返回 `gift: 0`。
- 买和领都要累计敲击满 `coin.minTaps`（10000）下，不够时返回 409 `park_locked`。
- 每花 1 枚驼币得 1 个印章，累计数到 `coin.stampsPerCoin`（30）的整数倍时自动换 1 枚驼币。`stamps` 是当前这一轮的印章数（`stampsTotal` 除以 30 的余数），`badge` 是 `stampsTotal` 达到的 `coin.badges`（100、1000、5000）档数，0 到 3。
- 奖品、印章、兑换码发的驼币不受持有上限限制。
- 赛跑停机退币时，印章和它换出的驼币一起退回。

`GET /api/park` 的 `today` 为 `{spent, won}`：今天买驼币花的碎片，和今天从游乐园奖品拿到的碎片（`park_scratch`、`jackpot`、`race_prize`、`lottery_prize`，不含兑换码）。`jackpot` 为刮刮乐全服奖池现在的金额。

错误码：`park_locked`、`coin_limit`（今天买够了）、`coin_hold`（持有到上限）、`no_shards`、`no_coins`（玩法要花的驼币不够），都是 409；`bad_count` 为 400。

驼币流水记在 `coin_ledger`，结构同碎片流水：花费按玩法记（`scratch`、`race`、`lottery`），获得记 `buy`、`gift`、`stamp`、`scratch_again`、`race_refund`、`redeem`、`admin`。

### 全服消息

大奖要让所有在线的桌宠知道，但服务端没有房间以外的推送。状态里的 `park.news` 带最近 15 分钟的最多 5 条：`{id, ts, kind, nick, ...}`，按 id 从旧到新，其余字段因 kind 而异。客户端每 20 秒的心跳会拿到状态，记住看过的 id，没看过的在桌宠上显示一次。昵称按房间昵称同样的规则做屏蔽词处理。消息保留 7 天。

<!-- park: scratch -->
### 刮刮乐

两种卡，奖表在 `scratch.cards`：普通卡 `basic` 花 1 枚驼币，豪华卡 `premium` 花 5 枚。和旧刮刮乐一样，奖品在买卡时定好，揭开时才发放，买卡后的余额只少了驼币；一个存档同时只有一张未揭开的驼币刮刮乐，和旧刮刮乐的卡互不影响。不限每天张数。

| 路由 | 请求与响应 |
|---|---|
| GET /api/park/scratch | card（未揭开的卡 `{id,kind,cells}`，没有时为 null）、pity（阿草表情保底计数，和旧刮刮乐共用）、emotesWhole（阿草表情是否已集齐）、jackpot（奖池金额） |
| POST /api/park/scratch | `{kind}`，kind 为 `basic` 或 `premium`。返回状态、`park` 和上一行的字段。已有未揭开的卡时原样返回这张卡，不再扣币。驼币不够返回 409 `no_coins` |
| POST /api/park/scratch/reveal | `{card}`，揭开并发放，返回状态、`park`、上上行的字段和 `prize:{tier,shards,coins,item}`。重复揭开返回同一份奖品，不再发放；卡不存在或不属于该存档返回 404 `no_card` |

`tier` 是奖项：

| tier | 普通卡 | 豪华卡 | 发放 |
|---|---|---|---|
| `again` | 15% | 12% | 退回买卡的驼币（`coins`），驼币流水记 `scratch_again` |
| `shards` | 1000（9.5%）、2500（3.5%）、8000（0.6%）、50000（0.05%） | 5000（13%）、12500（3%）、40000（0.5%）、250000（0.02%） | 碎片，流水记 `park_scratch` |
| `emote` | 5%，保底 10 张 | 没有 | 一个还没有的阿草表情（`item`） |
| `skin` | 没有 | 0.2% | 一款还没有的皮肤；全都有时给 `skin.shards`（30000）碎片 |
| `big` | 没有 | 0.1% | 一张还没有的大隐藏卡；全都有时给 `big.shards`（60000）碎片 |
| `jackpot` | 1/12000 | 5/12000 | 整个奖池，碎片流水记 `jackpot` |
| `miss` | 其余 | 其余 | 没有 |

- 阿草表情的保底计数就是旧刮刮乐的 `pity`，两种卡一起累计，规则相同。豪华卡不计数。集齐后表情那 5% 改成 `again`，计数不再变化。旧刮刮乐还没揭开的卡上的表情算已拥有。
- 皮肤池和共鸣一样按 `X-Client-Version` 过滤。刮出皮肤和大隐藏卡不影响共鸣保底。
- 买卡到揭开之间从别处得到了同一件东西：皮肤和大隐藏卡改发对应的碎片，表情改成退回驼币（`tier` 变成 `again`）。

**奖池**：两种卡每花 1 枚驼币，`jackpot.perCoin`（20）碎片进奖池，奖池从 `jackpot.seed`（30000）起步。每张卡先把自己的驼币计入奖池，再单独抽奖池，概率为驼币数除以 `jackpot.odds`（12000）；抽中时这张卡就是奖池卡，不再按奖表抽。奖池在买卡时整个归这张卡，并从 30000 重新起步，揭开时发放。揭开之前，刮刮乐三个接口给这个存档的奖池金额（`jackpot` 和 `park.jackpot`）仍是这张卡拿走的数目，免得提前看出中奖；`GET /api/park` 显示的是重新起步后的金额。

每枚驼币平均换回的碎片（再来一张退回的驼币接着玩，算到变成碎片为止；奖池按长期平均，每枚 20 加上 30000/12000）：普通卡集齐表情前 299，集齐后 347；豪华卡 342（皮肤、大隐藏卡按 30000、60000 算）。

**卡面**：`cells` 的写法同旧刮刮乐，另有 `again`、`skin`、`big`、`jackpot` 四个图案；豪华卡另有填空用的 `blank`，不对应任何奖。中奖图案恰好三次，其余最多两次；最高档图案（达到 `serverAt` 的数额、`skin`、`big`、`jackpot`）除中奖图案外最多出现一个，只出现一次。

**广播**：揭开的碎片（含奖池）达到 `roomAt[kind]`（8000、40000）时，向该存档所在的房间广播 `scratch {id,shards}`，同旧刮刮乐。全服消息（`park.news` 的 kind）：

| kind | 时机 | 其他字段 |
|---|---|---|
| `jackpot` | 刮中奖池 | shards |
| `scratch_big` | 奖表的碎片达到 `serverAt[kind]`（50000、250000） | card（`basic` 或 `premium`）、shards |
| `scratch_item` | 刮出皮肤或大隐藏卡 | card、item |

驼币刮刮乐的卡记在 `park_scratch_cards` 表，启动时自动建表；已揭开的卡保留 30 天。
<!-- park: race -->
<!-- park: lottery -->
### 每日夺宝

每天一期，按北京时间。配置在 `economy.park.lottery`。

- 1 枚驼币一注，号码 `000` 到 `999`，自选或机选，同一个号码可以买多注。每个存档每天最多 `daily`（10）注。
- 当天第 `closeAt` 分钟（1315，即 21:55）停售，第 `drawAt` 分钟（1320，即 22:00）开奖。
- 开奖号码和一个 256 位随机串在当天第一注卖出之前生成（零点由服务端生成，或当天第一次请求时生成），当天只公布 `hash = SHA-256(号码 + 随机串)`：号码的三位数字后面直接接随机串的十六进制文本，按 UTF-8 计算，结果为小写十六进制。开奖后公布号码和随机串，任何人都可以自己算一遍核对。
- 奖级，同一注只算最高一档：
  - 头奖，三位全对：当天销量（注数 × 驼币价格，单位碎片）的 `top`（40%）加上头奖滚存，最多 `topCap`（500000），超出的部分并进当天的二等。
  - 二等，后两位对：销量的 `second`（20%）加上二等滚存。
  - 三等，末位对：每注固定 `third`（600）碎片。
- 头奖和二等由中奖的注平分，向下取整到整数碎片。除不尽的余数滚存到下一期的同一档；没人中时整档滚存。
- 奖金按开奖当天记入碎片流水 `lottery_prize`；买注花的驼币记入驼币流水 `lottery`，同样得印章。
- 服务端停机错过的开奖在启动时按日期顺序补开，每期只开一次。

`GET /api/park/lottery` 返回：

| 字段 | 说明 |
| --- | --- |
| day | 今天的日期 |
| hash | 今天的哈希 |
| closeAt、drawAt | 今天停售、开奖的 Unix 秒 |
| open | 现在能不能买 |
| drawn | 今天是否已开奖。已开奖时下一期在明天，时间加一天 |
| sales | 今天卖出的注数 |
| prize | `{top, second, third}`，下一次开奖的奖金。今天没开奖时是今天的；开奖后是已经滚存到明天的部分 |
| daily、left | 每天最多几注、我今天还能买几注 |
| tickets | 我今天的号码，按购买顺序 |
| last | 最近开过奖的一期，没有时为 null：`{day, number, salt, hash, drawnAt, sales, winners, each, mine, won}`。winners 是各档中奖注数 `{top, second, third}`，each 是各档每注奖金，mine 是我这期的号码 `[{number, tier, prize}]`（tier 为 `top`、`second`、`third` 或 null），won 是我这期一共中的碎片 |
| history | 我最近 7 期的结果 `[{day, number, won}]`，只算我买过注、已开奖的期，从新到旧 |

`POST /api/park/lottery`：`{numbers?: ["007", ...], random?: n}`，自选号码和机选注数可以同时给，合计至少 1 注。机选的号码互不相同，也不和我今天已有的、这次自选的重复。要么全部买成，要么一注都不买。返回状态、`park`、`lottery`（同上）和 `bought`（这次买到的号码，自选在前）。

错误码：`lottery_closed`（已停售）、`lottery_cap`（超过每天的注数）、`no_coins`，都是 409；`bad_number`（号码不是三位数字）、`bad_count`（一注都没有）为 400。

开奖后发一条全服消息，`kind` 为 `lottery_draw`，带 `day`、`number`、`winners`、`each`，以及 `nicks`：头奖得主的昵称，每个存档一个，按最早买的那注排序，最多 5 个。消息只能带一个存档，`nick` 是第一位头奖得主，没人中头奖时为空字符串。当天一注都没卖出时不发消息。
<!-- park: redeem -->
### 兑换码

`POST /api/redeem`，`{code}`（最多 64 字符）。码不分大小写，忽略 `-` 和空白。成功时返回状态、`park`（有游乐园的服务端才带）和 `redeemed:{shards,coins}`。检查、计次、发奖和兑换记录在同一个事务里完成。碎片记进碎片流水，驼币记进驼币流水，来源都是 `redeem`。兑换码发的驼币不受持有上限限制；没有游乐园的服务端也照样发驼币，只是不能新建带驼币的码。

- 生成的码为 12 位，取自去掉 `0 O 1 I L` 的 31 个字符，显示成三段，例如 `K7QM-3XRP-WD9H`。管理员也可以自己写一个好记的码（4–32 个字母、数字或汉字）。
- 每个码有可用次数：一人一码为 1 次，通用码为 N 次。不管哪种，每个存档只能兑换一次。
- 接入了主站账号的服务端上，只有绑定账号的存档能兑换；没有接入主站账号的服务端不要求登录。

错误码：

| code | HTTP | 含义 |
| --- | --- | --- |
| `bad_code` | 409 | 码不存在。停用的码也返回这个，不透露码是否存在过 |
| `already_redeemed` | 409 | 这个存档已经兑换过这个码（码之后过期或用完也先报这个） |
| `code_expired` | 409 | 已过期 |
| `code_used_up` | 409 | 次数已用完 |
| `login_required` | 401 | 服务端接入了主站账号，这份存档还没绑定账号 |
| `too_many_tries` | 429 | 输错太多次被锁定。`detail.seconds` 为剩余锁定秒数，响应头 `Retry-After` 相同 |

防猜码：同一存档 10 分钟内有 5 次 `bad_code`，锁 15 分钟，锁定期间输对的码也返回 `too_many_tries`。输对和其他错误码不计数；解锁后从零重新计数。每次锁定记进每天计数 `redeem_lock`，每个存档的锁定次数和最近一次锁定时间记在 `redeem_locks` 表。不按 IP 限制。

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
- 结算：向全房间广播 `duel_result {duel,winner,loser,prize,hands}`（hands 里没出拳的一方为 null）。客户端在赢家桌宠旁显示到手碎片。
- 只结算一次：出拳、超时、掉线、离开可能同时发生。服务端在内存里先把对局标为结束再访问数据库，数据库里用 `UPDATE duels SET state=... WHERE id=? AND state='open'` 的条件更新确认，只有第一次成功的结算发碎片。
- `duel_over` 的 reason：`declined`、`timeout`（邀请没回应）、`gone`、`no_shards`、`duel_cap`、`idle`、`draws`；后两种已退款。
- 余额：客户端收到 `duel_start`、`duel_result`、`duel_over` 后重新读一次 `GET /api/me`。

## 数据迁移

刮刮乐新增 `scratch_cards` 表和 `players.scratch_pity` 列，启动时自动补上。已揭开的卡保留 30 天，启动时清理更早的。

猜拳新增 `duels` 表（启动时自动创建）：扣款时写入一行，state 从 `open` 变为 `won`（winner 为赢家存档）或 `refunded`，只变一次。房间只在内存里，服务端重启后上次没结算的对局没法继续，启动时把 `open` 的对局全部退款。


首次启动新版本时，旧碎片乘 16，旧抽卡次数和箱余额每份换成 160 碎片，随后清零旧余额。迁移由 skin_pity 列的存在性标记，只执行一次。已拥有物品、draw_pity 大隐藏进度和 drawn_total 累计次数保留。发布前备份数据库并在备份副本验证换算；回滚时同时恢复匹配版本的数据库。
