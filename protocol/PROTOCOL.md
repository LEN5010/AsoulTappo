# AsoulTappo 协议

## 身份与房间

HTTP 请求使用 `X-Player-Token`（16–128 字符）；客户端本地生成，服务端以 SHA-256 前 16 位标识玩家。登录主站账号后改用 `Authorization: Bearer <主站令牌>`，服务端向 `MAIN_API_URL/auth/me` 确认账号（结果缓存 5 分钟；主站连不上时沿用该令牌 1 小时内的上次结果，没有则返回 503 `account_unavailable`，失败后 15 秒内不再请求主站），再按 `account_links` 找到绑定的存档。游客存档绑定账号后，原来的 `X-Player-Token` 返回 401 `save_linked`。`GET /healthz` 返回服务状态，`POST /rooms` 返回随机房间号。房间在首次加入时创建、最后一个成员离开时回收，最多 20 人。

第一个进入房间的成员是房主；房主离开（包括连接因超时或积压被断开）后，房主传给剩下成员里最早进入的一位。房间默认私密，房主可以随时设为公开或改回私密，公开房间出现在 `GET /rooms` 里。设为公开要求房主带存档（见下），否则返回 `host_needs_save`。接入了主站账号的服务端（配置了 `MAIN_API_URL`）还要求房主这条连接加入时带了有效的 accountToken，否则返回 `host_needs_account`；两项都检查时先查账号，所以没登录的房主收到 `host_needs_account`，登录了但账号没绑定存档的收到 `host_needs_save`。改回私密不受这两条限制。房主传给没登录账号的成员时，房间保持公开，新房主可以改回私密，但不能再设为公开。公开以后，新加入的成员必须带存档；设为公开前已经在房间里的无存档成员留下。这里的带存档指加入时的 token 或 accountToken 能解析出存档，与 HTTP 接口的身份规则相同。

房主可以移出其他成员，不能移出自己。被移出成员的存档记在这个房间的封禁名单上，房间回收前这份存档无法再进入；同一存档在房间里的其他连接一起移出。无存档的成员也可以移出，但没有存档可封，他拿着房间号还能再进来（公开房间除外，因为公开房间不收无存档成员）。房主在另一条连接上的同一存档只移出、不封禁。房间回收后封禁名单随之清空。正在猜拳的成员（下注已扣）不能被移出，返回 `in_duel`。成员被移出房间（被移出、连接写入失败）后如果连接还没关，这条连接再发来的消息按未加入处理：`ping` 和 `join` 照常，其余返回 `not_joined`。房间没有文字聊天。

服务端重启会清空所有房间，客户端重连后按原房间号重新加入。服务端收到停止信号时记下每个房间的公开状态、房主的存档和封禁名单，重启后 10 分钟内有效：房间重新建起时带回封禁名单；原房主的存档回来时房主交还给它（向其他成员广播 `room_info`），房间原来公开的，这时一起恢复公开（接入了主站账号的服务端仍要求房主带了有效的 accountToken）。原房主回来之前，第一个回来的成员暂时当房主，房间保持私密。合力应援当前这一轮的进度不保留。

`GET /rooms` 在接入了主站账号的服务端上要求 `Authorization: Bearer <主站令牌>`：没带令牌返回 401 `account_required`，令牌无效返回 401 `account_expired`，主站连不上返回 503 `account_unavailable`；账号不必绑定存档。没接入账号的服务端不检查身份。凭房间号加入不受影响，游客存档照样能进公开房间。返回 `{rooms:[{room,name,host:{nick,character},members,max}, ...]}`：公开房间的房间号、房间名（打码后，没起名时为空字符串）、房主昵称和显示的角色、当前人数和人数上限，最多 50 个。有空位的房间排在前面，同类按人数从多到少，人数相同按创建先后。满员房间照样列出。

WebSocket 地址为 `/ws`，每帧一个 JSON 对象。不是 JSON 文本或字段不合格式的帧返回 `error` `bad_message`，连接保持。

| 客户端 type | 字段 |
|---|---|
| join | room（1–64）、nick（1–24）、character（≤32，成员名或以成员名开头的皮肤名，如 `贝拉山海经`；存档未拥有的皮肤或未知名称改为显示名称开头的成员，都不匹配时显示第一位成员）、token（可选）、accountToken（可选，主站令牌，优先于 token）、plate（可选，铭牌 ID，存档未解锁或不认识时忽略）、dnd（可选，布尔，猜拳免打扰，见猜拳一节）、ddz（可选，布尔，客户端会打斗地主，见斗地主一节）、status（可选，联机状态 ID，见下）、motionVersion（可选，整数 ≥1，客户端能读的最新动作格式，见动作格式一节；不带为 1） |
| leave | 无 |
| tap | count（1–500），客户端每 100–200ms 合并；服务端按连接限速（每秒 15、最多攒 75），超出部分不广播。这只限制房间显示，每条连接各算各的，重连会重新计，不是每人总上限；收益只看 `POST /api/activity`，按存档共用一份额度（存在数据库里，并发、多连接、重连都不叠加）。其他软件模拟的按下（连点器、宏，客户端能分辨时）不发：不算进 tap，也不进 motion、pose 的按下状态，本机桌宠照常动。这份存档发到房间的输入被判定为自动输入期间（见敲击收益与活动），服务端不广播它的 tap、motion 和 pose：它在其他成员眼里保持静止，房间内的敲击数不涨；判定解除后恢复，并补发它当前的动作 |
| motion | dx、dy（桌宠图层偏移，−20 至 20）、keyDown、left、right（按下状态）；移动每 100ms 合并，按键状态即时发送。格式 1 的客户端用它 |
| pose | x、y（四分之一像素，−80 至 80 的整数）、b（按键位：1 键盘、2 左键、4 右键，0 至 7），只带有变化的字段；格式 2 起的客户端用它代替 motion |
| motion_subscribe | ids（成员 id，最多 20 个）：要接收谁的动作。格式 2 起有效，格式 1 的连接发来会被忽略；每次发送替换上一次的名单 |
| poke | id（成员 id）：戳一戳同房间的另一位成员。每条连接每 3 秒最多一次，同一位成员 10 秒内只能戳一次，没到时间返回 `poke_cooldown`；id 不在房间里或是自己返回 `no_member`。只发给 `joined.features` 里有 `poke` 的服务端 |
| drink | 无字段：玩家在桌宠的喝水提醒上点了喝了。服务端向房间里其他成员广播 `drink {id}`，不发回给本人；每条连接 30 秒最多一次（`rooms.DRINK_INTERVAL`），太快的直接丢弃、不回错误。只发给 `joined.features` 里有 `drink` 的服务端 |
| profile | id（成员 id，可以是自己）、showcase（可选，请求方能摆几张展示卡；1.2.5 以前的客户端不带，按 3 张给）：要这位成员的主页。服务端回 `profile`，只发给请求的人。每条连接 0.3 秒最多一次，太快返回 `rate_limited`；id 不在房间里返回 `no_member`。只发给 `joined.features` 里有 `profile` 的服务端 |
| emote | emote（≤32），表情 key；初始表情免费，其余验证所有权 |
| state | character、nick、plate、status，至少提供一个；plate 为空字符串时取下铭牌，status 为空字符串或不在列表里时不显示状态。character 为存档未拥有的皮肤（或未知名称）、plate 未解锁时返回 `locked` 并忽略整条消息 |
| ping | 无 |
| set_public | public（布尔），仅房主；值有变化时向全房间广播 `room_info`，没有变化时只把当前的 `room_info` 回给房主 |
| set_name | name（最多 64 个字符，超过返回 `bad_message`），仅房主，不是房主返回 `not_host`：给房间起名，空字符串取消。服务端去掉控制字符和格式字符，连续空白合成一个空格并去掉首尾空白，再截到 16 个字符（`rooms.ROOM_NAME_MAX`），按屏蔽词表打码。房间显示的名字有变化时向全房间广播 `room_info`，没有变化时只回给房主。只发给 `joined.features` 里有 `name` 的服务端 |
| kick | id（成员 id），仅房主；不是房主返回 `not_host`，id 不在房间里或是房主自己返回 `no_member`，要移出的连接正在猜拳或斗地主对局中返回 `in_duel` |
| dnd | dnd（布尔），猜拳免打扰开关，斗地主的邀请也按它处理；只发给有猜拳的服务端 |
| duel_invite | id（成员 id）、bet（下注，必须是 `economy.duel.stakes` 里的一档） |
| duel_answer | duel（对局 id）、accept（布尔），只有被邀请的一方能回应 |
| duel_throw | duel、hand（`rock` / `scissors` / `paper`），每局只认第一次 |
| ddz_invite | ids（两位成员的 id）、base（底分，必须是 `economy.doudizhu.stakes` 里的一档） |
| ddz_answer | table（牌桌 id）、accept（布尔），只有被邀请的两位能回应 |
| ddz_bid | table、bid（0 不叫，1–3 叫分，必须高于已有的叫分） |
| ddz_play | table、cards（牌号 0–53 的数组，最多 20 张；空数组为不出） |
| ddz_auto | table、on（布尔）：打开或取消自己座位的托管 |
| ddz_again | table：结算后要求和同样两位、同样底分再来一局 |
| ddz_leave | table：离桌。邀请阶段等于取消或拒绝，对局中座位交给托管，结算后关闭牌桌 |

服务端消息：`joined {room,you,members,info,features,cheer}`、`cheer {target,minShare,total,shares,rounds}`、`cheer_done {round,rewards}`（合力应援，见下文）、`profile {id,showcase,progress}`（回给请求的人：showcase 为这位成员存档里选的展示卡 ID，没选时为空，张数不超过请求里的 `showcase`（不带时 3 张，最多 5 张）；progress 为 `{cards,emotes,skins}`，每项 `[已拥有, 总数]`，计法和图鉴一致，初始表情算已拥有；没有存档的成员为 null）、`poke {from,to,quiet?}`（全房间都收到，包括发起人；被戳的人开了猜拳免打扰时，发给被戳者的那份带 `quiet: true`，客户端只让桌宠弹一下，不出气泡）、`drink {id}`（这位成员喝了水，客户端在它的桌宠旁边显示一个杯子）、`room_info {host,public}`、`member_joined {member}`、`member_left {id}`、`tap {id,count,total}`、`motion {id,dx,dy,keyDown,left,right}`、`motion_batch {motions:[{id,dx,dy,keyDown,left,right}, ...]}`、`motion_snapshot`、`motion_delta`、`motion_edge`、`motion_edges`（见动作格式一节）、`emote {id,emote}`、`scratch {id,shards}`、`state {id,character,nick,plate,status}`、`duel_invite`、`duel_start`、`duel_round`、`duel_result`、`duel_over`（猜拳一节）、`ddz_*`（斗地主一节）、`pong`、`error {code,message,reason?}`。`features` 列出这个服务端在 1.1 之外支持的房间消息，现在是 `["poke", "profile", "cheer", "status", "drink", "name"]`（`drink`：`drink` 消息；`name`：`set_name`），`features` 和 `cheer` 只发给加入时带了 motionVersion（2 及以上）的客户端，更早的客户端收到的 `joined` 保持原样；旧服务端没有这个字段。`info` 和 `room_info` 是房间级状态：host 为房主的成员 id，public 表示房间是否公开，name 为房主起的房间名（屏蔽词已打码，没起名时为空字符串）；房主、公开状态或房间名变化时服务端广播 `room_info`。房间名跟着房间走：房主离开后名字留下，新房主可以改；服务端停机时和房主、公开状态一起保存（`room_restore`），10 分钟内重启后房间重新建立时恢复。屏蔽词表更新后，名字显示有变化的房间会收到一条 `room_info`。成员包含 `id,uid,nick,character,taps,motion,plate,status,ddz`，ddz 为这条连接加入时是否带了 `ddz: true`（没有斗地主的服务端一律为 false），plate 为经服务端核对的铭牌 ID，没有时为 null；status 为联机状态 ID，只能是 `fish`（摸鱼）、`work`（工作）、`study`（学习）、`game`（打游戏）、`music`（听歌）、`live`（看直播）之一（`rooms.ROOM_STATUSES`），其他值一律当作没有，没有时为 null。状态由玩家自己选，只在内存里随连接保存。之前的服务端不认识 status，而且 state 至少要有 character、nick、plate 之一，所以客户端改状态时连同昵称一起发；加入时的 motion 为该成员最近一次桌宠动作。`uid = sha256(player_id + ':' + room)[:10]` 用于记录同桌位置。

合力应援：存档上报 `/api/activity` 后，服务端把这次计入收益的敲击（每分钟计入收益的部分，已过防连点冷却）加到这份存档最近加入的房间的应援条上；累计敲击不满 1 万下的存档不计入。房间里至少有 2 份不同存档时条才会涨。一份存档本轮出力满 50 下就算出力，从这时起它的出力才上条（不满 50 下的先记着，不上条）；条的目标是 300 × 出力人数（至少按 2 人算），所以满条等于出力的人平均每人 300 下，很多人各敲几十下凑不满条；条满并且至少 2 人出力时这一轮结束，每位出力的存档得 10 × 出力人数 碎片（账本来源 `cheer`，每份存档每天最多 1000），条清零。中途加入：出力立刻上条，满 50 下后计入人数，目标和每人奖励随之变大。中途离开：已出的力留在条上；离开后 60 秒内仍计入人数、仍能领本轮奖励（掉线重连的同一份存档接着算），过了 60 秒不再计入人数，但已上条的出力留在条上，目标随之变小，下一次有人上报时再判断是否满条。`cheer` 为条的现状：`target` 为当前目标，`total` 为已上条的出力（不超过 `target`），`shares` 为在场成员（按成员 id）本轮的出力，包括还没满 50 下的，`count` 为出力人数，`reward` 为现在满条时每人能得的碎片，`rounds` 为这个房间完成的轮数；条在涨时最多每 2 秒发一次，有人离开时、一轮结束后（跟在 `cheer_done` 后面）也发，加入时放在 `joined.cheer` 里。`cheer_done.rewards` 为这一轮每位在场得奖成员拿到的碎片，当天已到上限的为 0。状态里的 `cheer {day,got,cap,minTaps}` 为当天从应援拿到的碎片、每日上限和参与门槛。

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
| not_host | 非房主发送 `set_public`、`set_name` 或 `kick` |
| no_member | `kick` 的 id 不在房间里或是房主自己；`poke` 的 id 不在房间里或是自己 |
| host_needs_save | 无存档的房主设置公开 |
| host_needs_account | 接入了主站账号的服务端上，没带有效 accountToken 加入的房主设置公开 |
| in_duel | 要移出的成员正在猜拳，或斗地主对局中 |
| no_duel | 服务器没有猜拳（manifest 没有 `economy.duel`） |
| duel_locked / duel_target_locked | 自己 / 对方没有存档，或累计敲击不足 |
| duel_busy / duel_target_busy | 自己 / 对方的存档已有一场对局或待回应的邀请 |
| duel_self | 邀请自己，或同一存档的另一条连接 |
| duel_cooldown | 对方 30 秒内拒绝过或没回应过你的邀请 |
| duel_cap | 这一档赢了会让某一方今天的净赢超过上限 |
| no_shards | 邀请方碎片不够这一档猜拳的下注或斗地主的押金 |
| duel_gone | 回应或出拳时对局已经结束（客户端不提示） |
| no_ddz | 服务器没有斗地主（manifest 没有 `economy.doudizhu`） |
| ddz_locked / ddz_target_locked | 自己 / 被邀请的某一位没有存档，或累计敲击不足 |
| ddz_busy / ddz_target_busy | 自己 / 被邀请的某一位的存档已在一张牌桌上（待回应的邀请也算） |
| ddz_target_old | 被邀请的某一位的客户端不会打斗地主（加入时没带 `ddz`） |
| ddz_self | 三位里有重复的成员，或两条连接是同一个存档 |
| ddz_cooldown | 被邀请的某一位 30 秒内拒绝过或没回应过你的邀请 |
| ddz_target_poor | 被邀请的某一位碎片不够押金（自己不够返回 `no_shards`） |
| ddz_cap / ddz_target_cap | 自己 / 被邀请的某一位今天斗地主的净赢已到上限 |
| ddz_gone | 牌桌已经不在这个阶段，或这条连接不在桌上（客户端不提示） |
| ddz_turn / ddz_bad | 没轮到这个座位 / 叫分或出的牌不合规则（客户端不提示，按服务端的状态继续） |

`room_full` 的 reason：`kicked`（被房主移出，发完这条后服务端关闭这条连接）、`banned`（存档在这个房间的封禁名单上，加入被拒，连接保持）、`need_save`（无存档加入公开房间，加入被拒，连接保持）。其他错误不带 reason 字段。

### 与 1.1 及更早版本的兼容

- 旧客户端只在收到 `room_full` 时停止重连，关闭码和其他错误码都会让它重连。所以被移出、被封禁、无存档进公开房间都用 `room_full` 加 reason 表示，旧客户端会当成最终失败并停止，但界面显示的是房间已满的文案（它按 code 选文案，不读 message 和 reason）。
- 旧客户端忽略 `room_info` 和 `joined` 里的 `info`，不显示房主，也不会发送 `set_public` 和 `kick`。旧客户端作为房主时，房间保持私密，直到房主传给新客户端。
- 新客户端连旧服务端：`joined` 没有 `info` 时不显示房主标记、公开开关和移出键，也不发送 `set_public` 和 `kick`；`GET /rooms` 在旧服务端返回 405（只有 `POST /rooms`），客户端收到 404 或 405 时不显示公开房间列表。
- 公开房间要求账号：客户端先读 `GET /api/info`，`accountLogin` 为 true 且没登录时不请求列表，公开房间一节只显示登录键；登录后带主站令牌请求，令牌只发给登录时所在的服务器。列表返回 401 时按未登录处理（`account_expired` 同时清除本地的登录状态）。房主没登录时不显示公开开关，房间已经公开时除外（用来改回私密）。`/api/info` 读不到时按没接入账号处理，服务端返回 401 时同样显示登录键。
- 喝水和房间名：旧客户端忽略 `drink` 和 `room_info` 里的 name。新客户端只在 `features` 有 `drink` 时发送 `drink`，有 `name` 时给房主显示改名键；旧服务端的 `room_info` 和 `GET /rooms` 没有 name，客户端按没起名显示。客户端开了隐藏昵称时也不显示房间名。
- 猜拳：旧客户端忽略 `duel_*` 消息（`RoomClient` 不认识的类型直接丢弃），成员字段没有变化；它收不到也回应不了邀请，邀请它的人 15 秒后看到超时。新客户端只在 `GET /api/me` 带 `duel` 时显示猜拳键、发送 `dnd` 和猜拳消息；旧服务端的状态没有这一项。`join` 里的 dnd 只在打开时带上，旧服务端忽略多出来的字段。
- 斗地主：新客户端在 `join` 里带 `ddz: true`，旧服务端忽略多出来的字段；成员的 `ddz` 标出哪些连接能被邀请，邀请旧客户端返回 `ddz_target_old`。旧客户端忽略 `ddz_*` 消息和成员的 `ddz` 字段。新客户端只在 `GET /api/economy` 带 `doudizhu`、`GET /api/me` 带 `ddz` 时显示斗地主入口，旧服务端没有这两项。

## HTTP API

| 路由 | 请求与响应 |
|---|---|
| GET /api/manifest | v4 素材清单：`assets-packs/manifest.json` 加上 economy 配置（不含服务端私有的 `antiCheat`） |
| GET /api/economy | economy 配置（价格、概率、上限，不含 `antiCheat`），另加 `tapGuard {fastPerSecond, fastStreakSec, cooldownSec}`。客户端同意协议并连上服务器后读取，缓存在本地；字段说明见 `server/app/economy.py`，示例数值见 `server/economy.example.json`。`resonance.rates` 按 `X-Client-Version` 给：这个版本的共鸣池里没有内容的档位（1.2.4 以前的客户端没有限定档）不列出，概率并入普通档，和它实际抽到的一致；抽不到镭射款的版本（1.2.4 以前）不带 `resonance.holoChance`。`resonance.banners` 是这个版本现在能抽、或一小时内开始的限定卡池 `[{id,name,start,end,items,rate?,rates?,share?,pity?}]`（start、end 为秒，后四项没设的不带），`resonance.held` 是被限定卡池留住、暂时不在常驻池里的物品 id；都没有时不带。配置文件里的整份卡池日程不下发 |
| GET /api/me | player、shards、income、dailyTaps、resonance、totals、checkin、tapCooldown、autoInput（见敲击收益与活动）、scratch、duel（`{net}`，今天猜拳的净赢；没有猜拳的服务端不带）、ddz（`{net}`，今天斗地主的净赢；没有斗地主的服务端不带）、cheer（`{day,got,cap,minTaps}`，见合力应援）、updateRewards（进行中且这个存档还没领的更新奖励 `[{id,version,shards}]`，按创建先后）、park（`{coins,news,gifted?}`，见乐园一节；没有乐园的服务端不带） |
| POST /api/activity | `{taps,session,sequence,cooldown?,injected?}`，返回状态和 credited；cooldown 是客户端自己触发冷却后剩余的秒数；injected 是这批敲击里由其他软件模拟的次数，客户端分辨不了时不带 |
| POST /api/presence | `{session}`，记录在线并返回状态；在线本身不给碎片 |
| POST /api/resonance/draw | `{count, banner?}`，count 为 1–100，实际次数取 count、100、余额可支付次数的最小值，返回状态和 drops。皮肤池按 `X-Client-Version` 过滤，见共鸣一节。banner 是限定卡池的 id，不带就抽常驻池；卡池不在进行中或这个版本抽不了时返回 409 `no_banner`，不扣碎片 |
| POST /api/craft | `{item}`，兑换未拥有的普通卡，以及普通、罕见、稀有表情，返回状态和 item |
| GET /api/checkin | 签到日历：today（北京时间日期）、available（今天还能不能签）、days（本月已签的 `{day,prize,shards}`，按日期排列，prize 为奖励档下标） |
| POST /api/checkin | 每日签到，每个存档每天一次，北京时间（UTC+8）零点刷新。服务端按 economy 配置 `economy.checkin.prizes` 的权重抽一档，实发碎片在该档数额上下浮动 `economy.checkin.spread`（均匀分布，按比例上下浮动，四舍五入取整），返回状态和 `prize:{index,shards,day}`，index 为奖励档的下标；当天已签返回 409 `checked_in` |
| POST /api/update-reward | 领取更新奖励：`X-Client-Version` 不低于奖励版本的、进行中且还没领的奖励一次全部发放，返回状态和 `reward:{shards,ids}`。预发布版本低于同号正式版。没有可领的返回 409 `no_reward` |
| GET /api/park | 乐园状态（见乐园一节）：coins、unlocked、gift、stamps、stampsTotal、badge、today、jackpot（每日夺宝的全服奖池） |
| POST /api/park/coins | `{count}`，用碎片买驼币，返回状态和 `park`。见乐园一节的错误码 |
| POST /api/park/gift | 领今天送的驼币，返回状态、`park` 和 `gift`（这次到账的枚数，今天已送过时为 0；状态接口通常已经送过） |
| GET /api/park/ledger | 我自己的驼币明细和兑换记录：`days`、`redeems`，见乐园一节的驼币 |
| POST /api/redeem | `{code}`，兑换码：返回状态、`park`（有乐园的服务端才带）和 `redeemed:{shards,coins}`。错误码和防猜码见乐园一节的兑换码 |
| GET /api/scratch | 刮刮乐状态：day（北京时间日期）、left（今天还能买几张）、pity（距上次出阿草表情已买的张数）、card（已买未揭开的卡 `{id,cells}`，没有时为 null） |
| POST /api/scratch | 买一张刮刮乐，返回状态和 `card:{id,cells}`。已有未揭开的卡时原样返回这张卡，不再扣费。当天卖完返回 409 `sold_out`，碎片不足返回 409 `no_shards` |
| POST /api/scratch/reveal | `{card}`，揭开这张卡并发放奖品，返回状态和 `prize:{shards,item}`。重复揭开返回同一份奖品，不再发放；卡不存在或不属于该存档返回 404 `no_card` |
| GET /api/collection | owned（物品 ID → 数量）、recent（最近获得记录）。1.2.4 以前的客户端看不到镭射款（`holo:` 物品） |
| GET /api/loadout | character、favorites、plate、showcase、nick、board。根据 `X-Client-Version`，1.2.5 以前的客户端收到可编辑的前三个展示卡位置。 |
| POST /api/loadout | 更新 character、favorites（最多 8 个且已拥有）或 plate；五位原皮直接可用，皮肤要求已拥有；plate 必须是已解锁的铭牌 ID，null 或空字符串取下铭牌；不是铭牌的 ID 返回 `bad_item`，未集齐返回 `locked`；showcase 为主页展示卡的卡片 ID 列表，最多 5 张，必须已拥有，超过或不认识返回 `bad_item`，未拥有返回 `locked`。1.2.5 以前的客户端可更新或清空前三个位置，服务端保留后两个位置；nick 为收藏榜上显示的昵称（最多 24 字，空字符串用默认昵称），board 为 false 时不上收藏榜。这两项客户端只上传，读取装备时不会覆盖本地设置 |
| GET /api/board | 全服收藏榜。`order` 为 `score`（按收藏分，显示收藏分的客户端）或 `cards`（默认，按卡片数，之前的客户端）。`cards`（前 50：`[{id,rank,nick,character,plate,cards,big,skins,score}]`，cards、big、skins 为卡片、大隐藏、皮肤数量，score 为收藏分；order=score 时按收藏分、大隐藏数、最后一件计分物品的获得时间排序，order=cards 时按卡片数、大隐藏数、最后一张卡的获得时间排序，只列有卡片的存档；昵称取 loadout 的 nick，为空时取这个存档最近一次在房间里用的昵称（加入或改名时记录，默认昵称不记），都没有时为默认昵称，经屏蔽词处理；铭牌未集齐时为 null）、`total`（卡片总数）、`points`（收藏分表，见下）、`me`（`{rank,cards,big,skins,score,off}`，rank 为所选排序下的名次，off 为 `hidden`（自己关了上榜）、`account`（服务端启用了主站账号而存档未关联）或 null）。榜单每 5 分钟重算一次 |
| GET /api/board/profile/{id} | 收藏榜前 50 里某一行（`id`）的主页：`{showcase,progress}`，格式同房间消息 `profile`；查询参数 `showcase` 是请求方能摆几张展示卡，不带时按 3 张给；不在榜上返回 404 `no_member` |
| GET /api/info | accountLogin（是否接入主站账号）、mainApi（主站 API 地址，未接入时为 null） |
| GET /api/client/release | 最新客户端版本 version 和更新说明 notes，读自主站 `/tappo/release`（未配置 `MAIN_API_URL` 时读官方主站），缓存 10 分钟；查不到时返回 503 `release_unavailable`。同时返回 minVersion（服务端要求的最低客户端版本，未设置时为 null）和 announcements（未过期的公告，每项 `{id,title,body,until,daily,since}`；since 为服务端第一次保存这条公告的时间（Unix 秒），客户端显示为发布日期；daily 为 true 时客户端每个北京时间日第一次打开面板都显示，直到玩家选不再出现，1.2.2 以前的客户端只显示一次）。客户端用它检查更新，安装包仍由 Tauri 更新器从 GitHub 下载，失败时打开主站下载页 |
| GET /api/account | Bearer；user、save（账号存档摘要，未绑定时为 null） |
| POST /api/account/link | Bearer，可带 `X-Player-Token`。账号未绑定时把这份游客存档（或新存档）绑定到账号，返回 user、save、linkedGuest；账号已有存档且游客存档玩过时返回 409 `account_has_save`，附 account 和 guest 两份摘要；游客存档已属于其他账号时返回 401 `save_linked` |
| GET /packs/index.json | 素材文件路径、大小及 SHA-256 |
| GET /packs/... | 卡面原图及主题动画资源 |

收藏分按每件物品平均要抽几次折算，1 分约等于 1 抽：大隐藏 300 分，皮肤 150 分，史诗卡、限定卡和镭射款 20 分，普通卡 2 分；镭射款和它的普卡各算各的，按卡片数排名时不算镭射款。表情约按合成价的比例计分：普通 1、罕见 2、稀有 3，阿草表情按稀有算，初始表情不计分。`points` 为 `{big,skin,epic,limited,holo,card,emoteRare,emoteScratch,emoteUncommon,emote}` 各一件的分数，客户端据此显示分数表；之前的客户端不认识 `limited` 和 `holo`，分数表里不显示这两行。之前的客户端不带 order，看到的仍是按卡片数的排名；它们都不在线后，order 的默认值可以改为 score。

从 1.1.4 起，状态中的 `dailyTaps` 为 `{day,count}`，day 是北京时间日期，count 是当天全部有效敲击数，包含每分钟收益上限以外的有效敲击。`income.taps` 继续记录参与碎片收益计算的次数。客户端的今日计数也按北京时间换日，并使用 `dailyTaps` 跨设备同步。旧库升级时以已有的当日收益计数初始化新统计，后续按全部有效敲击累加。

铭牌显示在其他成员桌面上该玩家桌宠的下方。`plate` 字段是铭牌 ID，有三种：

- 大隐藏卡的卡片 ID（形如 `c1762331462002`）。解锁条件是集齐这张卡所在收藏集里该成员的全部卡片（包括大隐藏本身）：几位成员共用的收藏集只要求该成员的卡，双人卡要求整个双人收藏集。客户端取卡面眼睛所在的一条横条，播放卡面视频。
- manifest 顶层 `plates` 里的铭牌 ID，每项为 `{id,name,emoteSet}`，拥有表情套 `emoteSet` 的全部表情即解锁。目前只有阿草铭牌 `achao`，由刮刮乐的 20 个阿草表情解锁。客户端显示侧栏的阿草图，横条从手臂慢慢扫到脸上再回到手臂。
- manifest 顶层 `plates` 里带 `series` 的铭牌，每项为 `{id,name,series,video,poster,still,aspect}`，拥有收藏集 `series` 的全部卡片即解锁。现在是三个衣橱铭牌 `wardrobe-jiaran`、`wardrobe-nailin`、`wardrobe-beila`，各由对应成员衣橱的 12 张限定卡解锁。video 是随客户端安装的视频，poster 是它的首帧，still 是 `/packs` 里的原尺寸静帧（个人主页名片用），aspect 是画面的高比宽。客户端按固定裁切播放视频。

`plates` 的 ID 不与卡片 ID 重复。服务端和客户端读同一份 manifest 判断解锁；没有 `plates` 的旧 manifest 只认大隐藏卡，认不出 `emoteSet` 或 `series` 的铭牌不能解锁。存档里已装备但未集齐的铭牌，读取装备和进房间时会被取下。裁切位置和动效节奏保存在客户端 `client/src/pet/plates.ts`。联机页的座位仍显示普通名牌。

动态卡的 `video` 字段使用 `bundle:cards/<系列>/<id>.mp4`，随客户端安装并在本地播放。`/packs/index.json` 只索引服务端的静态卡面和主题资源。

物品 ID 为 `card:<id>`、`emote:<key>`、`char:<皮肤名称>`、`holo:<卡片 id>`（镭射款，见共鸣一节）。五位成员原皮默认拥有，初始表情不参与共鸣。`drops[]` 包含 `item,rarity,new,count,shards`，卡片额外包含 `tier`（`big` / `small` / `normal`）。抽到镭射款时 item 仍是普卡的 `card:<id>`，另带 `holo: true` 和 `cardNew`：这时 new 指镭射款是不是第一次得到，cardNew 指普卡是不是。rarity 为 `legendary`、`skin`、`epic`、`limited`、`rare`、`uncommon` 或 `common`。重复物品自动兑换成碎片，不再累计数量：新物品的 shards 为 0，重复物品按 `economy.resonance.duplicateRefund` 返还。表情取 `emote`，镭射款优先取 `holo`，史诗档且 `tier: normal` 的跳舞卡优先取 `dance`，其余情况按卡片的 `tier` 取值。1.1 之前累计的重复卡片在服务端启动时一次性按同样标准折算，数量改为 1。

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
  "autoInput": 0,
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
| GET /admin/online?days= | 联机。days 为 1–90，默认 14。返回 `{today,now,series,recent,recentStep}`。now 为此刻的 `{rooms,members,saves,largest,public}`：有成员的房间数、成员数、其中不同存档数、最大房间人数、公开列出的房间数。series 每天一行 `{day,samples,peakMembers,peakRooms,peakSaves,avgMembers,sharedMinutes,counts,duels,cheer}`：服务端每分钟记一次房间采样，samples 为当天采样数（服务端停机时没有采样），sharedMinutes 为有房间至少两人的分钟数；counts 为当天次数 `{room_join,poke,drink,profile,board_profile,emote,duel_invite,cheer_round}`（进房间、戳一戳、房间里看到的喝水、房间里看主页、收藏榜看主页、表情、猜拳邀请、应援满条）；duels `{played,bets:{下注:局数}}` 为当天结束的猜拳局数；cheer `{shards,saves}` 为当天应援发出的碎片和领到的存档数。recent 为最近 24 小时，每 recentStep（10）分钟一个点 `{ts,rooms,members,saves}`，取那段时间的最大值 |
| GET /admin/anomalies?day= | 异常。day 为 `YYYY-MM-DD`，默认今天。返回 `{day,tapCap,taps,heavy,shards}`。taps 为当天有标记的存档，按自动输入判定次数（加上匀速冷却次数）、服务端冷却次数、被丢弃的敲击数倒序，最多 50 个 `{player,userId,credited,dropped,serverCooldowns,clientCooldowns,steadyCooldowns,autoFlags,injected,tapShards}`：dropped 为上报了但没有计入的敲击（超过速率或冷却中），serverCooldowns 为服务端判定连续过快而开始的冷却次数，clientCooldowns 为客户端自己的防连点开始的冷却次数，steadyCooldowns 为服务端判定匀速而开始的冷却次数（这条规则已由自动输入判定取代，只有它运行过的日期有数），autoFlags 为这份存档当天被判定为自动输入的次数（一段连续的判定算一次），injected 为客户端报告的由其他软件模拟的敲击数，credited、tapShards 为当天计入的敲击和敲击碎片。heavy 为当天计入敲击最多的 20 个存档，格式同 taps（判定和冷却都没抓到的连点器只会出现在这里）。shards 为当天靠玩法得到碎片最多的 50 个存档 `{player,userId,gained,sources}`，不算初始碎片、更新奖励、兑换码和后台调整 |
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
| `ddz_deposit`、`ddz_return`、`ddz_refund` | 斗地主的押金、结算时退回的押金加减输赢、没有胜负时原样退回的押金（后两项按结算当天记） | 1 |
| `coin_buy` | 买驼币花费 | 买的枚数 |
| `park_scratch`、`lottery_prize` | 乐园的碎片奖：驼币刮刮乐、每日夺宝（团子赛跑发驼币，记在驼币流水） | 1 |
| `redeem` | 兑换码发的碎片 | 1 |
| `admin` | 管理接口的调整 | 1 |

同一存档同一天的多次 `admin` 调整合并为一行，正负相抵，所以 `admin` 在 issued、spent 里是净值。

### 最低版本与公告

| 接口 | 说明 |
| --- | --- |
| GET /admin/notice | minVersion 和 announcements（含已过期的，每条带 since） |
| PUT /admin/notice | 整体替换。minVersion 为空字符串时取消限制；announcements 最多 20 条，每条 id、title（最多 40 字）、body（最多 2000 字）、until（Unix 秒，0 为不过期）、daily（布尔，缺省 false）。since 由服务端记录：id 已有的沿用原来的，新 id 记保存时间，请求里带的 since 不采用；没有 since 的旧公告在服务端启动时记为启动时间 |

客户端从 1.1.3 起在每个 HTTP 请求里带 `X-Client-Version`，房间连接地址带 `?v=`。设置 minVersion 后，版本更低或没有带版本的请求返回 426 `client_outdated`，加入房间收到 reason 为 `client_outdated` 的最终拒绝；`GET /api/client/release` 不受限制。1.1.3 及以后的客户端读到 minVersion 高于自己时，更新弹窗不能关闭；更早的客户端不带版本，只会看到请求失败。客户端 1.2.4 起把当前公告放在公告板里（面板顶栏的公告键），一条一页，新的在上；有没看过的公告时面板打开就弹出公告板，关掉后列表里的都算看过，已读记录在本机。更早的客户端每条单独弹出一次。`scripts/notice.py` 是这两个接口的命令行包装。

### 更新奖励

| 接口 | 说明 |
| --- | --- |
| GET /admin/update-rewards | `{rewards:[...]}`，从新到旧，每项 `{id,version,shards,created,ended,claims,paid}`；ended 为结束时间（Unix 秒），进行中为 null；claims 为领取的存档数，paid 为已发出的碎片 |
| POST /admin/update-rewards | `{version,shards}`，新建奖励：客户端版本不低于 version 的存档各能领一次 shards（1–1000000）。version 格式不对返回 400 `bad_version`；同一版本已有进行中的奖励返回 409 `reward_open`。返回同 GET |
| POST /admin/update-rewards/{id}/end | 结束奖励，没领的存档不能再领。奖励不存在或已结束返回 409 `no_reward`（不用 404，主站把 404 当作服务不可用）。返回同 GET |

新建档也能领，奖励按存档发，不看存档创建时间。客户端在面板里弹出可领的奖励，只列出自己版本够得着的。

### 兑换码管理

码的格式和兑换规则见乐园一节的兑换码。每个码在下列接口里表示为 `{id,code,custom,shards,coins,uses,used,expires,disabled,note,createdBy,created}`：code 为显示形式（生成的码分三段）；custom 为管理员自己写的码；uses 为可用次数，used 为已兑换次数；expires 为过期时间（Unix 秒），不过期为 null；disabled 为停用时间，没停用为 null；createdBy 为生成它的主站管理员。

| 接口 | 说明 |
| --- | --- |
| POST /admin/codes | `{shards,coins,count,uses,expires,note,code}`，生成兑换码。shards 0–1000000、coins 0–1000，两者至少一个大于 0，否则返回 400 `bad_reward`；没有乐园的服务端 coins 必须为 0。count 为 1–500（默认 1），uses 为每个码的可用次数 1–1000000（默认 1），expires 为 Unix 秒（0 或缺省为不过期，已过去的时间返回 400 `bad_expiry`），note 最多 200 字。code 为自定义码，可选：带 code 时 count 只能为 1（否则 400 `bad_count`），格式不对返回 400 `bad_code_text`，已有同样的码返回 409 `code_taken`。返回 `{codes:[...]}`，按生成顺序 |
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

客户端每 20 秒发送心跳和累计敲击数。碎片只来自敲击，在线本身不给碎片。每个北京时间自然日按当天计入的敲击数 n 累计发放 `dailyCap × (1 − e^−x)` 碎片，x = a·m + b·m² + c·m³，m 是 n 除以 1000：越往后每下给得越少，逐渐接近每天上限、不会超过；每下不到 0.01 时状态里的 `perTap` 记为 0，客户端显示今日已满。次日零点重新计算。每个 UTC 分钟只有前 `tapsPerMinute` 下计入 n，超出的仍计入总敲击数和活跃分钟。小数碎片留到下次结算。参数在 economy 配置 `economy.income`：`dailyCap`、`curve`（[a, b, c]）、`tapsPerMinute`。管理接口里的到顶人数按 `perTap` 记为 0 的那一下算。

状态里的 `income`：`day` 是这些数字所属的北京时间日期（YYYY-MM-DD），`today` 是今天已从敲击拿到的碎片，`cap` 是每天上限，`taps` 是今天计入的敲击数，`perTap` 是下一下值多少碎片（达到上限后为 0）。`multiplier` 固定为 1、`perMinute` 为 `perTap × 60`，只给 1.0 版客户端显示，新客户端不读。

服务端只接收敲击次数，按每秒上限限速；相同 session 的 sequence 去重。上报的速度连续一段时间过快时，这份存档进入冷却：触发的那一批和冷却期间所有 session 的上报都不计入，也不给碎片。状态里的 `tapCooldown` 是冷却剩余秒数，没有冷却时为 0。客户端按 `GET /api/economy` 的 `tapGuard`（`fastPerSecond`、`fastStreakSec`、`cooldownSec`）逐秒判断：连续 `fastStreakSec` 秒每秒都有 `fastPerSecond` 下及以上时触发，之后 `cooldownSec` 秒内不计数、不广播敲击，并在桌宠上方提示剩余秒数；触发时立刻上报一批（没有敲击也报），带上 `cooldown` 剩余秒数，服务端据此让这份存档进入冷却（不超过服务端自己的冷却时长，只会延长不会缩短），这一批不计入。服务端判定的冷却客户端也照样显示。

自动输入判定：服务端把每个 session 的每一批上报（敲击数、`injected`、距上一批的时间）交给判定模块，由它判断这份存档的输入是不是连点器、宏一类的自动输入。判定成立期间，状态里的 `autoInput` 是剩余秒数（没有时为 0，更早的服务端不带这个字段）：客户端在桌宠上方提示一次，每天最多一次。收益和冷却不受影响。

房间里只算手按的：带 `injected` 的客户端自己不把模拟的按下发到房间（见房间一节的 `tap`），服务端另外只拿每批里其余的敲击（`taps - injected`）再判定一次，这一份成立期间房间不显示这份存档的敲击和动作；不带 `injected` 的客户端发到房间的就是全部输入，按上面那一份判定隐藏。合力应援的进度同样只算手按的：每批计入的敲击去掉 `injected`，房间隐藏这份存档期间不计。判定规则不在公开仓库里：服务端从环境变量 `ASOULTAPPO_GUARD` 指向的文件读取（接口见 `server/app/guard.py`），没有配置时不做判定。

每个 UTC 分钟累计 10 下计一个活跃分钟。

## 共鸣与兑换

五位成员共用一个池子，所有非初始卡片、表情和皮肤一起参与共鸣。三张心宜与思诺共有卡各自只入池一次，共用同一个拥有记录。可抽内容是清单里的全部卡片（含限定卡）、全部皮肤，以及除初始表情和阿草表情以外的成员表情。

清单 `skins` 每项为 `{name, member, title?, since?}`。name 是皮肤 ID（素材目录、`char:<name>` 物品、房间的 character 字段），以成员名开头，之后不再改动；title 是界面上显示的名称（成员名加皮肤自己的名字，如 `嘉然帝江`），没有时显示 name；since 是带上这款皮肤图片的客户端版本（x.y.z）。共鸣时客户端版本低于 since 的，这款皮肤不进它的皮肤池；预发布版本按对应正式版算（1.2.0-rc.3 算 1.2.0），不带版本或版本读不出时，带 since 的皮肤都不进池。这样老客户端不会抽到自己显示不了的皮肤。客户端把 since 最新的那一批皮肤作为开屏公告展示一次。卡片也可以带 since，规则相同：衣橱的限定卡 since 为 1.2.4，之前的客户端抽不到，它们的限定档并入普通档。

| 档位 | 内容 |
|---|---|
| 传说 | 大隐藏卡 |
| 皮肤 | 成员皮肤 |
| 史诗 | 小隐藏与跳舞卡 |
| 稀有 | 动态表情 |
| 罕见 | 绽放收藏集与脑洞波表情 |
| 限定 | 衣橱卡：嘉然、乃琳、贝拉的个性装扮立绘各 12 张 |
| 普通 | 普通卡与普通表情 |

常驻池各档概率在 `economy.resonance.rates`，传说和皮肤两档的保底次数在 `economy.resonance.pity`。常驻池抽取概率大于 0 的档位，限定池可独立设置档位概率。限定档在普通档之前判定，其他档位的区间不变；没有保底，集齐 36 张后概率并入普通档。

每次消耗 `economy.resonance.cost` 碎片。两个保底各自累计，抽中对应档位时清零；同时到期先出大隐藏，下次出皮肤。对应档位全部拥有时保留进度，新增内容后可继续触发。高档集齐后的概率并入普通档，`repeatTiers` 里的档位（目前只有史诗档）除外：史诗档集齐后保留原概率，在整档里等概率抽，出的都是重复。普通档先按 `commonKindWeights`（普卡 : 表情）选类型，再在该类型内等概率选择未拥有物品，该类型集齐后产生重复。重复按上面的标准兑换成碎片。某类集齐后仍保持类型比例。其他档位在未拥有物品内等概率选择。

稀有表情为此间为爱、绮梦漫游、匣中惊鸿三套动态表情，共 60 个；罕见为绽放收藏集与脑洞波各三套，共 75 个；普通表情共 320 个。已有物品按原 ID 保留。

新玩家获得初始碎片。兑换价格按稀有度在 `economy.craftCost`；史诗、限定、传说、皮肤、镭射款和初始表情不参与兑换。

### 限定卡池

服务端在 `economy.resonance.banners` 里排限定卡池，每个有开始和结束时间（带时区的 ISO 8601）、限定物品（卡片或皮肤的物品 id），以及下面两种出法里的至少一种：限定概率 `rate`（百分比，可带限定保底 `pity`），或者主打份额 `share`（百分比）。卡池还可以带自己的档位概率 `rates`。

- 限定物品从写进配置起就不在常驻池里，卡池还没开始时也一样；卡池结束后进入常驻池，按自己的档位和概率出。被留住期间不能兑换，刮刮乐也不出。
- 抽限定卡池等于抽常驻池再多一档：`rate` 从普通档的区间里取，抽中时在还没有的限定物品里等概率选一件，drop 带 `featured: true`，rarity 仍是物品自己的档位。限定物品不出重复，全部拥有后这个卡池和常驻池抽到的一样。
- `rates` 是 `{<档位>: 百分比}`，只在这个卡池里替换常驻池同名档位的概率，没写的档位照常驻池；普通档不能写，取剩余。常驻池省略一个档位或把它写成 0 时，该档只在设置了正概率的限定卡池里出。常驻池显式配置的 0 随 `/api/economy` 下发。`rates` 换过之后的各档位加上 `rate` 不能超过 100。
- `share` 不加档位：抽到某个档位、限定物品里又有这个档位还没有的，`share`% 出其中一件（等概率，drop 带 `featured: true`），其余照这个档位在常驻池里的出法。这个档位在常驻池里已经没有可出的东西时，只要限定物品里还有就出限定物品。`rate` 和 `share` 可以同时用。
- 大隐藏和皮肤的保底是存档的，抽哪个池都累计；抽到限定皮肤也算抽到皮肤，皮肤保底清零。限定保底只在这个卡池里累计：距上次限定物品 `pity` 抽必出。大隐藏保底和限定保底同时到期时先出大隐藏，下一抽出限定。
- 状态的 `resonance.banners` 是 `{<卡池 id>: {pity, drawn}}`：这份存档在进行中卡池里的限定保底进度和抽数，没抽过的卡池不列。
- 限定物品里有这个客户端版本显示不了的（`since` 更新）时，不向它下发这个卡池，它带着这个 id 抽卡返回 `no_banner`。不带 banner 的旧客户端只抽常驻池。
- 同一时间进行的两个卡池不能有相同的限定物品；配置有误时服务端不启动。

### 镭射款

此间为爱、匣中惊鸿、绮梦漫游三个收藏集各有 7 张静态普卡有镭射款，共 21 张。清单里这些卡带 `holo {mask, shine, since}`：mask 是 `/packs` 里的官方遮罩（白色是镭射区域），shine 是着色参数 `{laserIntensity, skinProtection, clothBoost, hueStart, hueRange}`，since 为 1.2.4。

- 镭射款是独立的物品 `holo:<卡片 id>`，不进任何档位，只在共鸣抽到对应普卡时按 `economy.resonance.holoChance`（百分比）变成镭射款；没有这一项的服务端不出镭射款。刮刮乐等其他来源不出镭射款。
- 抽到镭射款时同时得到这张普卡。第一次得到某张镭射款时这一抽不退碎片，普卡是重复的也一样，普卡数量不变；已拥有这张镭射款时按 `duplicateRefund.holo` 返还碎片，省略该键时按对应普卡档位返还。同一批里第二次抽到同一张镭射款算重复。
- 客户端版本低于 since 的不出镭射款，也不为它多掷一次；预发布版按对应正式版算，不带版本或版本读不出的也不出。
- 镭射款算进收集进度（按卡片算）和收藏分，可收集的总数是共鸣池的件数加镭射款的张数。

## 刮刮乐

每张 `economy.scratch.price` 碎片，每个存档每天 `economy.scratch.daily` 张，北京时间零点刷新。配置在 `economy.scratch`，没有这一项的服务端不提供刮刮乐，状态里也没有 `scratch`，三个接口返回 404 `no_scratch`。

奖品是 `prizes` 里的碎片档（权重为百分比）和阿草表情（`emote.weight`，第 `emote.pity` 张保底），剩下的概率是没中。

奖品在买卡时由一次随机数决定，揭开时才发放，所以买卡后的余额只少了卡价。一个存档同时只有一张未揭开的卡；未揭开的卡跨天仍可揭开。

阿草表情是表情套 `achao` 的 20 个表情（`source: "scratch"`），只从刮刮乐获得，不进共鸣池，也不能兑换。每次给一个存档还没有的；保底按买卡张数累计，出表情时清零，计数方式与共鸣保底相同。

20 个集齐后没有表情这一档，也不再触发保底：只按碎片奖品的权重抽，表情那一档并入没中，不给重复表情。是否集齐在买卡时判断，拿到最后一个表情的那张卡揭开之后，下一张才按集齐后的规则抽。集齐后 `pity` 不再变化；最后一个表情出现时已清零，所以通常是 0。

`cells` 是九个格子的图案，碎片数额写成数字串，表情写成表情 key。中奖图案恰好出现三次，其余图案最多出现两次，其中最大的数额最多出现一次；没中的卡没有出现三次的图案。

揭开的碎片奖品达到 `economy.scratch.announce` 时，服务端向该存档所在的每个房间广播 `scratch {id,shards}`，客户端在这位成员的桌宠上方显示。出表情由客户端在揭开后发送这个表情。

## 乐园

1.2.1 之后的客户端。配置在 `economy.park`（`coin`、`scratch`、`race`、`lottery`），没有这一项的服务端不提供乐园，状态里也没有 `park`，接口返回 404 `no_park`。

### 驼币

- 用碎片买，每枚 `coin.price`，每天能买的数量和持有数量都不限，一次请求最多买 100 枚。驼币不能换回碎片，也不能转让。
- 每天送 `coin.gift` 枚，不用打开乐园：状态接口（`GET /api/me`、心跳和其他返回状态的接口）发现存档累计敲击满 `coin.minTaps`、今天还没送过时直接到账，驼币流水记 `gift`；到账的那一次返回里 `park.gifted` 为到账的枚数，其余时候没有这个字段；乐园接口和兑换码接口返回的 `park` 是乐园状态，不带这个字段，所以 `gifted` 只在 `park` 来自状态接口时出现（`GET /api/me`、`POST /api/activity`、`POST /api/presence` 等）。`POST /api/park/gift` 仍可用，今天已送过时返回 `gift: 0`。
- 买和领都要累计敲击满 `coin.minTaps` 下，不够时返回 409 `park_locked`。
- 每花 1 枚驼币得 1 个印章，累计数到 `coin.stampsPerCoin` 的整数倍时自动换 1 枚驼币。`stamps` 是当前这一轮的印章数（`stampsTotal` 除以 30 的余数），`badge` 是 `stampsTotal` 达到的 `coin.badges` 档数，0 到 3。
- 赛跑停机退币时，印章和它换出的驼币一起退回。

`GET /api/park` 的 `today` 为 `{spent, won}`：今天买驼币花的碎片，和今天从乐园奖品拿到的碎片（`park_scratch`、`lottery_prize`，不含兑换码；团子赛跑的奖金是驼币，不算在内）。`jackpot` 为每日夺宝头奖的全服奖池现在的金额（见每日夺宝），各接口返回的 `park.jackpot` 相同。

错误码：`park_locked`、`no_shards`、`no_coins`（玩法要花的驼币不够），都是 409；`bad_count` 为 400。

驼币流水记在 `coin_ledger`，结构同碎片流水：花费按玩法记（`scratch`、`race`、`lottery`），获得记 `buy`、`gift`、`stamp`、`scratch_again`、`race_refund`、`race_prize`、`redeem`、`admin`。

`GET /api/park/ledger` 只返回请求者这份存档的数据，没有乐园的服务端返回 404 `no_park`：

- `days`：驼币流水里最近有记录的 14 天（北京时间日期），从新到旧，每天 `{day, items: [{source, amount, count}]}`。`amount` 带符号，获得为正、花费为负；`count` 同流水表（买的是枚数，玩法是次数）。`amount` 为 0 的行不返回（例如同一天集章换出又被退币扣回），只有这类行的日子也不返回。`items` 按 source 排序。
- `redeems`：这份存档兑换过的码，按兑换时间从新到旧，最多 50 条，每条 `{code, ts, shards, coins}`。`code` 按兑换码一节的显示格式（生成的码分三段，自定义的码原样）；之后停用的码照样列出。

### 全服消息

大奖要让所有在线的桌宠知道，但服务端没有房间以外的推送。状态里的 `park.news` 带最近 15 分钟的最多 5 条：`{id, ts, kind, nick, ...}`，按 id 从旧到新，其余字段因 kind 而异。客户端每 20 秒的心跳会拿到状态，记住看过的 id，没看过的在桌宠上显示一次。昵称按房间昵称同样的规则做屏蔽词处理。消息保留 7 天。

<!-- park: scratch -->
### 刮刮乐

两种卡，奖表在 `scratch.cards`：普通卡 `basic` 花 1 枚驼币，豪华卡 `premium` 花 5 枚。和旧刮刮乐一样，奖品在买卡时定好，揭开时才发放，买卡后的余额只少了驼币；一个存档同时只有一张未揭开的驼币刮刮乐，和旧刮刮乐的卡互不影响。不限每天张数。

卡的配置带 `hidden: true` 时暂停发售（目前豪华卡是这样）：服务端不卖，客户端不显示；之前买下还没揭开的这种卡照常返回、揭开和发放。

| 路由 | 请求与响应 |
|---|---|
| GET /api/park/scratch | card（未揭开的卡 `{id,kind,cells}`，没有时为 null）、pity（阿草表情保底计数，和旧刮刮乐共用）、emotesWhole（阿草表情是否已集齐） |
| POST /api/park/scratch | `{kind}`，kind 为 `basic` 或 `premium`。返回状态、`park` 和上一行的字段。已有未揭开的卡时原样返回这张卡，不再扣币。驼币不够返回 409 `no_coins`；没有未揭开的卡时买 `hidden` 的卡返回 409 `card_hidden` |
| POST /api/park/scratch/reveal | `{card}`，揭开并发放，返回状态、`park`、上上行的字段和 `prize:{tier,shards,coins,item}`。重复揭开返回同一份奖品，不再发放；卡不存在或不属于该存档返回 404 `no_card` |
| GET /api/park/scratch/history | 我自己的驼币刮刮乐记录 `{days:[{day, spent, kinds:[{kind, cards, shards, coins, items}]}]}`：30 天内有卡的最近 14 天（北京时间，按买卡日期），从新到旧。spent 为当天买卡花的驼币（驼币流水的 `scratch`）；kinds 按 kind 排序，cards 为买的张数（含还没揭开的），shards、coins 为已揭开的卡发放的碎片和驼币（`again` 退回的驼币），items 为发放的物品 ID，按买卡顺序。只返回请求者这份存档的数据；没有乐园的服务端返回 404 `no_park` |

`tier` 是奖项：

| tier | 普通卡 | 豪华卡 | 发放 |
|---|---|---|---|
| `again` | `again` | `again` | 退回买卡的驼币（`coins`），驼币流水记 `scratch_again` |
| `shards` | `prizes` | `prizes` | 碎片，流水记 `park_scratch` |
| `emote` | `emote.weight`，第 `emote.pity` 张保底 | 没有 | 一个还没有的阿草表情（`item`） |
| `skin` | 没有 | `skin.weight` | 一款还没有的皮肤；全都有时给 `skin.shards` 碎片 |
| `big` | 没有 | `big.weight` | 一张还没有的大隐藏卡；全都有时给 `big.shards` 碎片 |
| `miss` | 其余 | 其余 | 没有 |

- 阿草表情的保底计数就是旧刮刮乐的 `pity`，两种卡一起累计，规则相同。豪华卡不计数。集齐后表情那一档并入 `miss`（不再退回驼币），计数不再变化。
- 皮肤池和共鸣一样按 `X-Client-Version` 过滤。刮出皮肤和大隐藏卡不影响共鸣保底。
- 买卡到揭开之间从别处得到了同一件东西：皮肤和大隐藏卡改发对应的碎片，表情改成退回驼币（`tier` 变成 `again`）。

**首张卡**：每个存档每种卡的第一张不按奖表抽，固定中这种卡的 `first` 碎片，`tier` 为 `shards`，卡面和发放同其他碎片奖。每个存档每种卡只有一次，以 `park_scratch_cards` 里有没有这种卡为准。首张普通卡照常计入阿草表情保底。

刮刮乐没有奖池；买卡花的驼币和其他玩法一样计入每日夺宝的全服奖池。

**卡面**：`cells` 的写法同旧刮刮乐，另有 `again`、`skin`、`big` 三个图案；豪华卡另有填空用的 `blank`，不对应任何奖。中奖图案恰好三次，其余最多两次；最高档图案（达到 `serverAt` 的数额、`skin`、`big`）除中奖图案外最多出现一个，只出现一次。

**广播**：揭开的碎片达到 `roomAt[kind]` 时，向该存档所在的房间广播 `scratch {id,shards}`，同旧刮刮乐。全服消息（`park.news` 的 kind）：

| kind | 时机 | 其他字段 |
|---|---|---|
| `scratch_big` | 奖表的碎片达到 `serverAt[kind]` | card（`basic` 或 `premium`）、shards |
| `scratch_item` | 刮出皮肤或大隐藏卡 | card、item |

驼币刮刮乐的卡记在 `park_scratch_cards` 表，启动时自动建表；已揭开的卡保留 30 天，每个存档每种卡的第一张一直保留。
<!-- park: race -->
### 团子赛跑

配置在 `economy.park.race`。每 `interval` 秒一场，下注 `betting` 秒，之后开跑，动画播完时结算，然后开下一场的下注。场次的边界（场次 `id`，即开始下注的 Unix 秒）相隔 `interval`；有 `startAt`（北京时间当天第几分钟）时整体平移，让开跑时刻落在这一分钟，没有时按 Unix 时间的整倍数对齐。

规则（`server/app/race.py`）：

- 成员是 manifest `characters` 的五个 id，按 manifest 里的顺序。每场给每个成员发一个技能（见地图和技能），没有配置技能的服务端发一个状态（一颗骰子），都没有时五个团子掷同一颗骰子。
- 赛道是一圈 `track` 格：第 0 格是起点，第 `track` 格是终点，两者是棋盘上同一个角格。配置了地图时，格数和特殊格都跟这一场的地图走；地图带路线时，格子沿路线铺在棋盘上，起点和终点是两个格子，规则不变。
- 起跑时五个团子一起站在第 0 格，排位顺序随机，记在 `start`。第 0 格不叠放：从第 0 格出发只走自己，不带别人。
- 起跑时五个各掷一颗六面骰（1 到 6，和走路用的 `dice` 分开）定行动顺序，点数高的先走；同点的几个在它们之间重掷，直到分出先后。顺序记在 `order`，整场不变。
- 每轮五个按 `order` 各走一次，掷 `dice`。走的时候头上叠着的团子一起带走；落到第 0 格以外有团子的格子时叠在最上面。
- 必须正好走到终点。`from + 点数 > track` 时先走到终点，再往回退多出的格数，落点是 `2 × track − (from + 点数)`；叠着被带走的团子一起退。
- 特殊格每场五个，互不相同，都在 `squares.range` 里：加速格、绊脚格、传送门的两端、翻转格。一组团子（走的团子和它带着的）按点数落到的格子是特殊格时，这个格子作用一次：
  - 加速格（+`squares.boost`）、绊脚格（`squares.trip`）：整组再移动这么多格，越过终点时同样往回退，叠到落点最上面。
  - 传送门 `[a, b]`（a < b，b − a 在 `squares.portalGap` 范围内）：落在任意一端，整组移到另一端，按原来的上下顺序叠在那一端已有团子的最上面。落在 b 时往回移。
  - 翻转格：整组先叠到这一格最上面，然后这一格上的整叠团子上下颠倒：从下到上的顺序整个反过来，原来最下面的变成最上面。颠倒的是这一格上所有的团子，包括之前就在这里、这一步没有移动的；只有这一组时就颠倒这一组。
  - 不连锁：加速、绊脚、传送之后到达的格子不再起作用，哪怕它也是特殊格。弹回后才落到的特殊格照常起作用。
  - 起点和终点不会是特殊格。
- 不限轮数，直到有一组正好落在终点，这一组结束比赛。名次按格子，同一格越靠上越靠前；比赛结束时仍在第 0 格的按排位，`start` 里靠前的在前（正常配置下不会出现：第二轮起每个团子都离开了第 0 格）。

地图和技能（客户端 1.2.5 起）：

- `maps` 是地图表，每张 `{id, name, track, squares, path?}`：`track` 是这张地图的格数（至少 14，没有路线时是偶数），`squares` 是特殊格 `[{at, kind, by?, to?}]`，数量不限，都不在起点和终点上，互不重叠。每场随机用一张，整张抄进 `setup.map`。
- `path` 是地图的路线。数值文件里写 `{from: [列, 行], runs: "R8 U2 L8"}`：从 `from` 这一格出发，每段向右（R）、左（L）、上（U）、下（D）走若干格，一共正好 `track` 格；列从左数、行从上数，都从 0 开始。棋盘最大 16 列 10 行，路线不经过同一格两次，除了前后相连的两格，任何两格都不相邻（这样从棋盘上能看出走向）。`setup.map.path` 是展开后的结果：从起点到终点每一格的 `[列, 行]`，共 `track + 1` 个。没有 `path` 的地图画成一圈，起点和终点在同一个角。
- 特殊格的 `kind`：`boost`、`trip`（各自带 `by`，前进或后退的格数，正整数）、`portal`（`to` 是另一端，`to` > `at`，两端都能进）、`flip`，规则同上；另有两种：
  - `again` 再掷：走的团子再掷一次自己的骰子，整组接着走这么多格（越过终点同样往回退）。
  - `hook` 钩索：整组移到前方最近的有团子的格子，叠在最上面；前方没有团子时留在原地。
  - 同样不连锁：再掷和钩索之后到达的格子不起作用。
- `skills` 是技能表，每个 `{id, dice, chance?, by?}`：`dice` 是带这个技能的团子这一场掷的骰子，`chance` 是百分比，`by` 是格数。每场发牌方式同状态：技能不少于成员时每个成员一个互不相同的，否则各抽一个。发到的技能抄进 `setup.skills`（不含 `dice`），骰子抄进 `setup.dice`。配置了技能的服务端不再发状态。
- 技能按 `id`：
  - `steady` 稳健：没有效果，只是骰子不同。
  - `burst` 爆发：每次行动有 `chance` 的概率走两倍点数。
  - `chase` 追赶：行动时排在最后一名（按名次规则，起点上按排位），多走 `by` 格。
  - `porter` 驮运：行动时头上有团子，多走 `by` 格。
  - `solo` 独行：行动时头上有团子，有 `chance` 的概率把它们留在原地（顺序不变，叠在它下面那些团子上），自己多走 留下的个数 × `by` 格。
  - `dash` 冲线：不用正好走到终点，会越过终点的一步（包括加速格和再掷的那一段）停在终点。
  - `shield` 护盾：落到绊脚格、或者落到会把它往回送的传送门一端时，这个格子对它这一组不起作用。
  - `climb` 登顶：别的一组落到它所在的格子（包括翻转之后）而它不在最上面时，它移到最上面。
- 多走的格数加在点数上一起走，落点的特殊格照常起作用。
- 更早的客户端不认识地图和技能：对它们，用了地图或技能的场次开跑后只给结果，`replay` 为 false，没有播放用的字段，往期里这样的场次 `replay` 也是 false，取回放返回 `no_replay`。它们仍然能下注，看得到每个团子的骰子和赔率。上线地图和技能时建议同时把最低版本提到 1.2.5。

| 接口 | 说明 |
| --- | --- |
| GET /api/park/race | `{now, nextAt, race, last, winners}`。`race` 是现在展示的一场（下注中、跑着或刚跑完），没有时为 null；`last` 是它之前最近结算的一场；`winners` 是最近 5 场的冠军 `[{id, member}]`，从新到旧；`nextAt` 是下一场开始下注的时间 |
| GET /api/park/race?view=summary | 与默认响应结构相同，含赔率、下注与比赛结果，省去回放的骰子、步序和播放时序。 |
| GET /api/park/race?view=schedule | `{now, nextAt, race}`，供开赛提醒和回放中的直播入口使用。当前场次为 `{id, phase, startsAt, endsAt?}` 或 null。 |
| POST /api/park/race/bet | `{race, kind, member, coins, odds?}`，返回状态、`park` 和 `race`。`odds` 是客户端显示的这个选项的赔率，可省略 |
| GET /api/park/race/history | `{races}`：最近 30 场已结束的场次（已结算或作废），从新到旧，见往期 |
| GET /api/park/race/replay/{id} | `{race}`：一场已结算场次，字段和 GET /api/park/race 的一场相同，用来重播。没有这一场或还没结算为 404 `no_race`；没有回放数据（见往期）为 404 `no_replay` |

一场的字段：

- `id`（等于 `opensAt`，unix 秒）、`phase`、`opensAt`、`startsAt`、`hash`。
- `setup`：用地图和技能的场次是 `{map, skills, dice, chance}`：`map` 是这一场的地图，`skills: {成员 id: {id, chance?, by?}}` 是每个成员的技能，`dice` 和 `chance` 同下。之前的场次是 `{boost, trip, portal: [a, b], flip, forms, dice, chance}`，特殊格的位置，这一场每个成员的状态 `forms: {成员 id: 状态 id}` 和它这一场掷的骰子 `dice: {成员 id: [点数…]}`，以及模拟出的名次次数 `chance: {sims, win|top2|last: {成员 id: 次数}}`（见赔率）。加入状态之前准备好的场次没有 `forms`、`dice`、`chance`，每个成员都掷 `dice`（经济配置里的），有 `popularity: {成员 id: 整数}` 的按人气开盘，都没有的开盘赔率都一样。加入传送门和翻转格之前准备好的场次只有 `boost` 和 `trip`，照旧规则跑。
- `odds`：`{win|top2|last: {成员 id: 赔率}}`，按目前的押注算出的当前赔率，一位小数。
- `pool`：`{win|top2|last: {成员 id: 驼币数}}`，这一场所有存档押的合计，五个成员都有，没人押为 0。
- `bettors`：押过这一场的存档数。
- `mine`：自己押的每一注 `[{kind, member, coins, odds}]`，按下注顺序，同一选项押几次就有几条，`odds` 是那一注锁定的赔率。结算后每条多一个 `prize`：这一注赢到的驼币，`coins × odds`，一位小数，没押中为 0。
- 开跑后另有 `seed`、`endsAt`、`ranking`（第一到最后）、`replay`，以及播放用的 `leadMs`、`rollMs`、`stepMs`、`slowFrom`、`slowMs`、按格数计时的场次的 `stepsMs` 和 `pace`（见播放）、`start`（第 0 格里的排位，五个成员 id）、`order`（行动顺序，五个成员 id，先走的在前）、`rolls`（定顺序的每一轮骰子，见下）、`moves`、`rest`（见下）；有技能特写的场次还有 `cuts`、`cutMs`（见播放）。`replay` 为 false 的旧场次（见往期）没有播放用的这些字段，只有结果。
- 结算后，押过的人另有 `result: {staked, won, net}`，单位驼币，按这一场所有注合计：`staked` 押的驼币，`won` 实际发的驼币（见结算），`net` = `won − staked`。

`phase`：`betting` 下注中；`starting` 已停止下注，服务端几秒内开跑；`running`；`done` 已结算；`void` 停机错过开跑，已退币。

`rolls` 是定顺序时掷的每一轮，第一轮是全部五个，之后是重掷轮；每轮是 `[{m, face}]`，按抽取顺序（成员在 manifest 里的顺序）排列。

`moves` 的每一步：

- `m`：走的团子。
- `dice`：掷出的点数，`[n]`；落在再掷格时是 `[n, 再掷的点数]`。
- `steps`：按点数走的格数：点数加上技能多走的格数，不含再掷的那一段。
- `from`、`to`：起点和落点。`to` 是弹回之后的落点；`from + steps > track` 说明这一步到过终点又往回退，路径是 `from` 一格一格走到 `track`，再一格一格退到 `to`。正好到终点时 `to` 为 `track`。
- `carry`：被带着走的团子，从下到上；没有时省略。从第 0 格出发的一步没有这个字段。
- `skill`：走的团子的技能在这一步起了作用时，是技能的 id（`burst`、`chase`、`porter`、`solo`、`dash`、`shield`）。`dash` 的一步 `from + steps > track` 而 `to` 等于 `track`，没有往回退。`shield` 的一步没有 `square` 和 `end`。
- `left`：`solo` 留在原地的团子，从下到上；它们不在 `carry` 里。
- `react`、`stack`：这一步落地后移到最上面的 `climb` 团子，和落点格子这时从下到上的整叠。客户端按 `stack` 摆放这一格。
- `square`、`end`：落到的特殊格（`boost`、`trip`、`portal`、`flip`、`again`、`hook`），以及它作用之后整组所在的格子；`flip` 的 `end` 等于 `to`，`hook` 前方没有团子时也是。翻转后的叠放顺序不单独给出，按上面的规则从开局一步步推出来：每一步先把整组按原顺序叠到 `end` 最上面，`square` 为 `flip` 时再把 `to` 上的整叠反过来。

`rest` 是最后一轮里排在冲线那一步之后、还没轮到的团子的骰子 `[{m, face}]`，按 `order` 排列；冲线的是这一轮最后一个时为空。它们只用来显示：每一轮五颗骰子同时掷出，最后一轮也凑满五颗，观众不会因为这一轮骰子少了几颗就提前知道比赛要结束。`rest` 不影响 `moves` 和 `ranking`。

轮：`moves` 每 5 步是一轮（第 r 轮是第 5r 到 5r + 4 步，按 `order`），最后一轮可能不满 5 步。第 r 轮的五颗骰子是这一轮各步 `dice` 的第一个点数，最后一轮再接上 `rest`。

播放：开跑后先演定顺序的骰子，`leadMs` = 4000 + (`rolls` 的轮数 − 1) × 1500：第 k 轮（从 0 起）在 `startsAt + 1500 + k × 1500` 开始掷，骰子翻滚 800 毫秒后停在点数上；最后一轮开始掷之后 1500 毫秒（落定后 700 毫秒），五个团子按 `order` 排好，1 秒后进入第一轮。之后每一轮先用 `rollMs` 同时掷这一轮的五颗骰子（前一半时间里抛起落下，后一半停着），再按 `order` 一步一步走：第 i 步（从 0 起，所在的轮 r = ⌊i ÷ 5⌋）在 `startsAt + leadMs + (r + 1) × rollMs + i × stepMs` 开始，每步 `stepMs`；从 `slowFrom`（最后一轮的第一步，`5 × ⌊(步数 − 1) ÷ 5⌋`）起放慢，第 i 步在 `startsAt + leadMs + (r + 1) × rollMs + slowFrom × stepMs + (i − slowFrom) × slowMs` 开始，每步 `slowMs`。`endsAt` 是最后一步结束后再过 4 秒，这时全部播完并结算。每一步里先点亮走的团子、抬起它的骰子（前 0.28），然后整组一格一格跳到落点（0.28 到 0.6，到过终点的先跳到终点再往回跳），特殊格从 0.6 起作用（到 0.88）：加速格、绊脚格再一格一格移动；传送门整组缩进这一端，从另一端冒出来，不经过中间的格子；翻转格这一叠每个团子弧线跳到新的高度；剩下的时间停着。特殊格不加时间。

技能特写：`cuts` 是 `[{at, m}]`，每个成员的技能在这一场第一次起作用的那一步（走的团子自己的技能先于被踩到的登顶；一步只有一个特写，同一步里第二个第一次起作用的成员留到它下一次）。第 `at` 步轮到时先停 `cutMs`，演成员 `m` 的技能名和说明，然后这一步照常走；这一步之后的每一步、每一轮的骰子都顺延 `cutMs`，`endsAt` 也包含全部特写的时间。没有特写的场次不带这两个字段。

按格数计时：带地图或技能的场次每一步的长短跟着它要演的内容走，另带 `stepsMs`（每一步的毫秒数，和 `moves` 等长）和 `pace` `{lit, hop, gap, act, rest}`。第 i 步在 `startsAt + leadMs + (r + 1) × rollMs + stepsMs` 前 i 项之和开始（再加上它之前的特写），长 `stepsMs[i]`。一步里依次是：点亮走的团子 `lit`；整组每格 `hop` 跳到落点，共 `steps × hop`；特殊格或登顶起作用时先停 `gap`，再每移动一格 `hop`（加速、绊脚、再走一次、钩子），不走格子的（传送门、翻转、登顶）用 `act`；最后停 `rest`。最后一轮的每一项都乘 `slowMs ÷ stepMs`。通常 `pace` 是 `{lit: 600, hop: 360, gap: 150, act: 600, rest: 500}`、`rollMs` 2800、`cutMs` 2000；一场太长时这些时间按同一比例缩短，`stepMs` 和 `slowMs` 只用来算最后一轮的倍数。按示例数值模拟一万二千场：步数中位 42，p99 79；播放时长中位约 160 秒，p99 约 290 秒，最长约 434 秒。

没有地图也没有技能的场次按固定步长播放：通常 `rollMs` 4800、`stepMs` 5000、`slowMs` 6600、`cutMs` 2600；一场太长、会播到下一场下注时，`stepMs` 和 `slowMs` 按同一比例缩短，`rollMs` 和 `cutMs` 跟着 `stepMs` 缩短（`stepMs × 4800 ÷ 5000`、`stepMs × 2600 ÷ 5000` 向下取整），`leadMs` 不变。加入每轮掷骰之前的场次没有 `rest`，`rollMs` 为 0，按旧时间轴播放；节奏放慢之前存下的场次按它自己的 `stepMs` 播放，按格数计时之前存下的带地图或技能的场次没有 `stepsMs`，也按固定步长播放。示例的比赛窗口是 590 秒（86400 − 85800 − 10），更长的场次按上面的办法播快。客户端用 `now` 校正本机时钟。

公平：

- 种子 32 字节，下注时只公布 `hash` = SHA-256(种子)，开跑后公布 `seed`（hex）。
- 整场由 `setup` 和种子决定，包括 `start`、`order` 和 `rolls`。随机数流是 SHA-256(种子 ‖ 8 字节大端计数器)，计数器从 0 起，每块取 8 个 32 位大端整数。`below(n)` 跳过不小于 2^32 − 2^32 mod n 的数后取余。
- 抽取顺序：先洗跑道；再定行动顺序；然后每一步掷一次走的团子自己的骰子 `setup.dice[m][below(面数)]`（没有 `setup.dice` 的场次是经济配置的 `dice`），接着按需要再抽：`burst` 每一步抽一次 `below(100)`，小于 `chance` 时生效；`solo` 只在头上有团子时抽一次 `below(100)`，规则相同；落在再掷格时再掷一次自己的骰子；比赛结束后，按 `order` 给 `rest` 里的每个团子同样各掷一次自己的骰子。洗牌从成员列表（manifest 顺序）出发，i 从 4 到 1 依次与 `below(i + 1)` 位置交换。
- 定行动顺序：每轮里要掷的成员按 manifest 顺序各取一次 `below(6) + 1`。第一轮五个都掷。每个成员掷过的点数按轮排成一个序列；一轮掷完后，序列和别人完全相同的成员都进下一轮重掷，不同的平局组在同一轮里一起掷，但只在组内比较。没有相同的序列时结束，`order` 按序列从大到小排，逐位比较。例：第一轮 6 6 3 3 1，前四个重掷得 5 2 4 4，第三、四个再掷一轮。
- `setup` 在下注开始前单独随机，和种子无关。配置了地图时先随机取一张地图，再发技能。状态在特殊格之后发：经济配置的 `forms`（每个 `{id, dice}`）随机排列，按 manifest 顺序每个成员一个；状态比成员少时每个成员各抽一个。`chance` 是用这一场的特殊格和骰子另外模拟 `sims` 场数出来的，用的随机数和种子无关，只影响赔率。

赔率：每个成员这一场的概率 p 按状态不同。开盘赔率是 `payout` ÷ p，之后随押注变化，三种押法分开算：

- 权重：w_m = `chance[k][m]`（至少 1），也就是模拟里成员 m 拿到押法 k 那些名次的次数；`win` 和 `last` 的 Σw = `sims`，`top2` 的 Σw = 2 × `sims`，所以 w_m × 名次数 ÷ Σw 就是 p。
- 没有 `chance` 的旧场次：有人气时 `win` 和 `top2` 的权重 w_m = u_m（这一场的人气），`last` 的权重 w_m = 2 × Σu − 5 × u_m（关于平均数翻转）；都没有时每个成员 w_m = 1，概率 `win` 1/5，`top2` 2/5，`last` 1/5。
- 对押法 k，S_m 是这一场押在成员 m 上的驼币（所有存档合计），S = Σ S_m。
- share_m = (S_m + `depth` × w_m ÷ Σw) ÷ (S + `depth`)。
- 赔率 = `payout` ÷ (share_m × 名次数)，名次数 `win` 和 `last` 为 1、`top2` 为 2，向下取到一位小数；再不超过 `fairCap` ÷ p（向下取到一位小数），没有 `chance` 的旧场次 p 按团子相同算（`win` 和 `last` 1/5，`top2` 2/5，人气不算）；最低 `minOdds`，最高 99。
- 押某个成员的人越多，它的赔率越低，其他成员的越高，但不超过 `fairCap` ÷ p：任何一注的 p × 赔率都不超过 `fairCap`（`minOdds` 托底的除外）。
- 开盘时 p × 赔率 = `payout`。按人气开盘的旧场次，开盘赔率最高的选项 p × 赔率也不超过 0.98。
- 每一注锁定下注前那一刻的赔率（在同一个事务里算），之后不再变。

下注：

- 只能押 `betting` 状态的场次，否则 409 `race_closed`；场次不存在或还没开始下注为 404 `no_race`。
- 每场每个存档合计最多 `maxCoins` 枚，超出 409 `race_cap`；`maxCoins` 为 0 或没有时不限（1.2.4 之前的客户端要求它是个数）。同一选项可以押多次，每次单独一注、单独锁定赔率。
- 带了 `odds` 而这个选项现在的赔率比它低时，返回 409 `odds_changed`，`detail` 多一个 `odds`（现在的赔率），什么都不改。现在的赔率不低于它时照常下注，按现在的赔率锁定。
- `kind` 或 `member` 不对为 400 `bad_bet`。驼币不够为 409 `no_coins`。

结算：

- 奖金是驼币。每一注押中时的奖金是 `coins × 这一注的赔率` 枚，以十分之一枚为单位记下（`coins × 赔率 × 10`，整数）。一个存档一场的各注奖金先相加，再四舍五入到整枚（`(十分之一枚的合计 + 5) ÷ 10` 向下取整，0.5 进位），记在驼币流水 `race_prize`。例：2 × 4.2 和 1 × 2.1 押中，合计 10.5，发 11 枚。每场只结算一次。
- 赛跑的奖金不是碎片，不计入乐园的 `today.won`。
- 一个存档一场拿到 `roomAt` 枚以上时，服务端向它所在的每个房间广播 `race_win {id, coins}`。旧客户端不认识这个消息，会直接忽略。

往期：

- 每场的步骤一直保存在服务端。1.2.4 之前的服务端在两天后删掉步骤，需要时按种子重算；这样的场次现在按当前规则重算，算出的 `ranking` 和结算时存下的一样、按算出的步数和定顺序轮数推出的 `endsAt` 也一样时才给回放，否则 `replay` 为 false，只给结果。规则改过之后，重算的结果可能和当时的比赛不同。
- `history` 的每一项：`id`、`day`（开跑那天的北京时间日期，`YYYY-MM-DD`）、`startsAt`、`phase`（`done` 或 `void`）；`done` 的另有 `ranking` 和 `replay`。自己押过的另有 `mine`：`done` 为 `{staked, won, net}`，和这一场的 `result` 相同；`void` 为 `{staked, net: 0}`，押的驼币已全部退回。
- 正在下注和正在跑的场次不在 `history` 里，也不能用 `replay` 取。

停机：

- 开跑时服务端不在（晚了 5 秒以上），这一场作废，押的驼币以 `race_refund` 退回，印章和印章换出的驼币一起扣回。
- 已经开跑的场次在重启后照常结算。
- 服务端启动时离开跑不到 30 秒的场次不开，等下一场。
- 旧测试版的赛跑表（按模拟算赔率、每个选项一行）启动时整表删掉重建，里面的场次和押注不保留。
<!-- park: lottery -->
### 每日夺宝

每天一期，开奖时间见 `drawAt`。配置在 `economy.park.lottery`。一期从上一期开奖开始，到这一期开奖为止，按开奖那天的北京日期命名：开奖之后买的注算下一期。

- 1 枚驼币一注，号码 `000` 到 `999`，自选或机选，同一个号码可以买多注。每个存档每期最多 `daily` 注。
- 开奖当天第 `closeAt` 分钟（北京时间）停售，第 `drawAt` 分钟开奖，开奖后立刻开卖下一期。
- 开奖号码和一个 256 位随机串在这一期第一注卖出之前生成（上一期开奖时由服务端生成，或开奖后第一次请求时生成），开奖前只公布 `hash = SHA-256(号码 + 随机串)`：号码的三位数字后面直接接随机串的十六进制文本，按 UTF-8 计算，结果为小写十六进制。开奖后公布号码和随机串，任何人都可以自己算一遍核对。
- 奖级，同一注只算最高一档：
  - 头奖，三位全对：全服奖池（`GET /api/park` 的 `jackpot`）。奖池从 `pool.seed` 碎片起步，乐园里每花 1 枚驼币（刮刮乐、赛跑、夺宝都算）加 `pool.perCoin` 碎片；赛跑停机退币时退回的驼币把对应的碎片扣回，最低到 0。
  - 二等，后两位对：每注固定 `secondEach` 碎片。经济配置没有 `secondEach` 时按旧规则：当天销量（注数 × 驼币价格，单位碎片）的 `second` 加上二等滚存。
  - 三等，末位对：每注固定 `third` 碎片。
- 头奖由中奖的注平分，向下取整到整数碎片。头奖有人中时，奖池变成 `pool.seed` 加上除不尽的余数；没人中时整个奖池留到下一期，继续累计。旧规则下二等也平分，除不尽的余数滚存到下一期的二等，没人中时整档滚存；每注固定的二等不滚存，换成固定后第一次开奖把旧的滚存清零。
- 开奖用开奖那一刻的奖池，停售到开奖之间花的驼币也算在内。
- 奖金按开奖当天记入碎片流水 `lottery_prize`；买注花的驼币记入驼币流水 `lottery`，同样得印章。
- 服务端停机错过的开奖在启动时按日期顺序补开，每期只开一次。

`GET /api/park/lottery` 返回：

| 字段 | 说明 |
| --- | --- |
| day | 这一期的日期（开奖那天） |
| hash | 这一期的哈希 |
| closeAt、drawAt | 这一期停售、开奖的 Unix 秒 |
| open | 现在能不能买 |
| drawn | 这一期是否已开奖。开奖时服务端会立刻换到下一期，所以通常为 false |
| sales | 这一期卖出的注数 |
| prize | `{top, second, third}`，这一期开奖的奖金。top 是现在的全服奖池，和 `park.jackpot` 相同。second 是每注奖金 `secondEach`；旧规则下是这一期的销量份额加上已经滚存过来的部分 |
| daily、left | 每期最多几注、我这一期还能买几注 |
| tickets | 我这一期的号码，按购买顺序 |
| last | 最近开过奖的一期，没有时为 null：`{day, number, salt, hash, drawnAt, sales, winners, each, mine, won}`。winners 是各档中奖注数 `{top, second, third}`，each 是各档每注奖金，mine 是我这期的号码 `[{number, tier, prize}]`（tier 为 `top`、`second`、`third` 或 null），won 是我这期一共中的碎片 |
| history | 我最近 7 期的结果 `[{day, number, won}]`，只算我买过注、已开奖的期，从新到旧 |
| draws | 全服最近 7 期已开奖的头奖名单 `[{day, number, top, each}]`，从新到旧，不管我买没买。top 是头奖得主 `[{id, nick}]`，每个存档只列一次，按最早买的那注排序，没人中时为空数组；id 是收藏榜的存档 id（不是 player id），nick 是带屏蔽词打码的昵称，和全服消息里的相同。each 是这一期每注头奖分到的碎片，没人中时为 0 |

`POST /api/park/lottery`：`{numbers?: ["007", ...], random?: n}`，自选号码和机选注数可以同时给，合计至少 1 注。机选的号码互不相同，也不和我这一期已有的、这次自选的重复。要么全部买成，要么一注都不买。返回状态、`park`、`lottery`（同上）和 `bought`（这次买到的号码，自选在前）。

错误码：`lottery_closed`（已停售）、`lottery_cap`（超过每期的注数）、`no_coins`，都是 409；`bad_number`（号码不是三位数字）、`bad_count`（一注都没有）为 400。

开奖后发一条全服消息，`kind` 为 `lottery_draw`，带 `day`、`number`、`winners`、`each`（`each.top` 为头奖每注分到的碎片，没人中时为 0），以及 `nicks`：头奖得主的昵称，每个存档一个，按最早买的那注排序，最多 5 个。消息只能带一个存档，`nick` 是第一位头奖得主，没人中头奖时为空字符串。这一期一注都没卖出时不发消息。
<!-- park: redeem -->
### 兑换码

`POST /api/redeem`，`{code}`（最多 64 字符）。码不分大小写，忽略 `-` 和空白。成功时返回状态、`park`（有乐园的服务端才带）和 `redeemed:{shards,coins}`。检查、计次、发奖和兑换记录在同一个事务里完成。碎片记进碎片流水，驼币记进驼币流水，来源都是 `redeem`。兑换码发的驼币不受持有上限限制；没有乐园的服务端也照样发驼币，只是不能新建带驼币的码。

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

房间里两位成员之间的石头剪刀布。数值在 economy 配置 `economy.duel`，服务端和客户端读同一份；没有这一项的服务端没有猜拳，状态里也没有 `duel`，猜拳消息返回 `no_duel`。

下注档位在 `stakes`，每档 `{bet, prize}`：双方各付 `bet`，赢家拿 `prize`。

两人下注合计减去 `prize` 的部分被销毁。邀请等 `inviteSec` 秒，每局出拳 `throwSec` 秒。

- 资格：双方都要有存档，且累计敲击（`totals.taps`）满 `minTaps`。新存档自带初始碎片，游客存档能无限新建，这条门槛防止拿新存档给别的存档送碎片。不能邀请自己，也不能邀请同一存档的另一条连接；对方必须在同一个房间。一个存档同一时间只能有一场对局或一个待回应的邀请（发出的和收到的都算，跨房间也算）。
- 每日净赢上限：每个存档每个北京时间日期，已结算对局的（到手 − 下注）累加，输的局是负数，退款的局不算，这个数不能超过 `dailyWinCap`。输不设上限。某一档赢了会让任意一方当天的净赢超过上限时，这一档的邀请返回 `duel_cap`；接受时再按同样的规则查一次。对局的日期取扣款时的日期。
- 邀请：服务端把 `duel_invite {duel,from,to,bet,prize,sec}` 发给双方。被邀请方开了免打扰时，服务端直接替他拒绝，他收不到邀请，邀请方收到的 `duel_over` 和普通拒绝一样是 `declined`。免打扰在 `join` 的 dnd 或 `dnd` 消息里设置，不广播；客户端在设置打开或点击穿透打开时都算免打扰。被拒绝或超时后，同一邀请方 30 秒内不能再邀请同一存档（`duel_cooldown`）。
- 扣款：接受时在一个数据库事务里扣双方的下注，任何一方碎片不够就都不扣，双方收到 `duel_over` `no_shards`。扣款成功后双方收到 `duel_start {duel,round,sec}`。
- 出拳：双方各自发 `duel_throw`。一方出拳后，对方出拳前收不到任何消息。平局时双方收到 `duel_round {duel,round,sec,hands}`，hands 是这次平局的双方出拳（按成员 id），然后重来；连续平局 10 次后双方退款（`duel_over` `draws`）。一局到时只有一方出了拳，没出的一方输；双方都没出，双方退款（`duel_over` `idle`）。
- 掉线和离开：对局绑定在发起和接受时的那条连接上。这条连接离开房间（`leave`、断线、写入失败）算输，即使同一存档的另一条连接还在房间里；邀请阶段任何一方离开，邀请作废（`duel_over` `gone`）；被邀请方离开不算拒绝，邀请方离开和被拒绝一样要等 30 秒才能再邀请同一存档，免得离开再进来反复弹邀请。
- 结算：向全房间广播 `duel_result {duel,winner,loser,prize,hands}`（hands 里没出拳的一方为 null）。客户端在赢家桌宠旁显示到手碎片。
- 只结算一次：出拳、超时、掉线、离开可能同时发生。服务端在内存里先把对局标为结束再访问数据库，数据库里用 `UPDATE duels SET state=... WHERE id=? AND state='open'` 的条件更新确认，只有第一次成功的结算发碎片。
- `duel_over` 的 reason：`declined`、`timeout`（邀请没回应）、`gone`、`no_shards`、`duel_cap`、`idle`、`draws`；后两种已退款。
- 余额：客户端收到 `duel_start`、`duel_result`、`duel_over` 后重新读一次 `GET /api/me`。

## 斗地主

房间里三位成员之间的斗地主，用碎片结算。数值在 economy 配置 `economy.doudizhu`，服务端和客户端读同一份；没有这一项的服务端没有斗地主，状态里也没有 `ddz`，斗地主消息返回 `no_ddz`。规则在 `server/app/ddz_rules.py`，牌局在 `server/app/ddz.py`；客户端的 `client/src/ddz/rules.ts` 是同一套规则，两边都用 `client/src/ddz/rules.fixture.json` 核对。

牌号 0–53：0–51 的点数为 `牌号 // 4 + 3`（3–10、J=11、Q=12、K=13、A=14、2=15），花色为 `牌号 % 4`（0 黑桃、1 红心、2 梅花、3 方块）；52 小王，53 大王。座位编号 0–2，按出牌顺序，0 是发起人。除 `ddz_live` 外，斗地主消息只发给桌上的三个座位，都带 `table`（牌桌 id）。

牌型：单张、对子、三张、三带一、三带一对、顺子（5 张起，到 A 为止）、连对（3 对起）、飞机（2 组三张起，可各带一张或各带一对）、四带二、四带两对、炸弹、王炸。带的对子不能是王。一手牌可能有多种读法（如 `333444` 加两张单牌），只要有一种读法能压过上家的某一种读法就可以出。

- 资格：三位都要有存档，累计敲击（`totals.taps`）满 `minTaps`，碎片不少于押金，连接加入时带了 `ddz: true`。三位必须在同一个房间，不能是同一个存档。一个存档同一时间只能在一张牌桌上（待回应的邀请也算，跨房间也算）；斗地主和猜拳各算各的。
- 押金：`底分 × capMult × 2`，是地主在封顶倍数下最多输的数。三位都接受后在一个数据库事务里扣三份押金，任何一位不够资格就都不扣，三位收到 `ddz_over`（`no_shards`、`ddz_cap` 或 `ddz_locked`）。结算时每个座位拿回押金加减自己的输赢。
- 每日净赢上限：每个存档每个北京时间日期，已结算对局的输赢累加（输的局是负数，退款的局不算）。这个数达到 `dailyWinCap` 后，这个存档当天不能再开新的一局；已经开始的一局照常结算，所以净赢可以超过上限一局的量。输不设上限。这个上限和猜拳的上限分开计算。对局的日期取扣押金时的日期。
- 邀请：发起人发 `ddz_invite`，服务端把 `ddz_invite {table,from,ids,base,deposit,sec}` 发给三位，ids 按座位顺序。被邀请方接受后三位收到 `ddz_answer {table,id}`。任何一位拒绝、`inviteSec` 秒内没有全部接受、有人离开房间，邀请作废，三位收到 `ddz_over {table,reason,by?}`。被邀请方开了免打扰时服务端替他拒绝，他收不到邀请。被拒绝或超时后，发起人 30 秒内不能再邀请拒绝或没回应的存档（`ddz_cooldown`）；发起人自己离开房间时对两位都计这 30 秒。
- 发牌：扣款成功后向全房间广播 `ddz_live {table,ids,on:true}`，然后每个座位收到 `ddz_deal {table,seats,you,hand,base,cap,deal,turn,sec,dealSec}`：seats 为三个座位的 `{id,nick,character,auto,away}`，you 为自己的座位，hand 为 17 张牌，cap 为封顶倍数，deal 为这桌第几次发牌，turn 为先叫分的座位（随机）。客户端用 dealSec 秒演发牌（盖着发到手里再翻开），演完才能叫分；turn 的 sec 秒从 dealSec 秒之后开始算。
- 叫分：从 turn 起每个座位叫一次，0 为不叫，1–3 必须高于已有的叫分。每次叫分三位收到 `ddz_bid {table,seat,bid,turn?,sec?}`。有人叫 3 分或三位都叫过后，叫分最高的座位当地主，三位收到 `ddz_landlord {table,seat,bid,bottom,mult,turn,sec}`，地主拿走 bottom 的三张底牌并先出。三位都不叫则重新发牌；连续 3 次没人叫，押金原样退回（`ddz_over` `nobid`）。
- 出牌：轮到的座位发 `ddz_play`，三位收到 `ddz_play {table,seat,cards,left,mult,bombs,turn?,sec?,lead?}`：cards 为空是不出，left 为这个座位剩下的张数，lead 为 true 时另外两位都没要，turn 重新领出。领出的座位不能不出。不合规则的出牌返回 `ddz_bad`，没轮到返回 `ddz_turn`。
- 倍数：`叫分 × 2^炸弹数`，春天或反春再乘 2，最多 `capMult`。炸弹和王炸都算一个炸弹。春天：地主赢，两位农民一手牌都没出过。反春：农民赢，地主只出过第一手。
- 结算：先出完牌的一方赢。每位农民输赢 `底分 × 倍数`，地主输赢两位农民的总和；赢到的部分扣掉 `rake`% 销毁（向下取整）。三位收到 `ddz_result {table,winner,landlord,bid,bombs,spring,mult,base,deltas,hands,sec}`：winner 为 `landlord` 或 `farmers`，spring 为 0、1（春天）、2（反春），deltas 为每个座位的输赢（赢家是扣过销毁后的数），hands 为每个座位剩下的牌。同时向全房间广播 `ddz_live {table,ids,on:false,gains}`，gains 为赢家的成员 id 和到手碎片，客户端在赢家桌宠旁显示。
- 再来一局：结算后 `againSec` 秒内，三位各发一次 `ddz_again`（每次三位收到 `ddz_again {table,seat}`），三位都发了就重新扣押金、发牌。到时间、有人离桌或离开房间、结算时已有座位没人，牌桌关闭，三位收到 `ddz_closed {table}`。
- 时间和托管：叫分 `bidSec` 秒，出牌 `playSec` 秒。到时间由服务端代打：叫分时不叫，出牌时能不出就不出，领出时出最小的一张。一个座位连续 2 次超时后进入托管，托管的座位每手 1.2 秒后由服务端代打，直到本人发 `ddz_auto {on:false}`；轮到自己时取消托管，这一手重新计时。座位状态变化时三位收到 `ddz_seat {table,seat,id,away,auto,turn?,sec?}`。
- 掉线和离开：座位属于存档。成员离开房间（`leave`、断线、被移出）后座位由服务端代打，输赢照常结算；同一存档再加入这个房间时拿回座位，收到 `ddz_state`（整局的状态：`phase,you,hand,seats,base,cap,deal,bid,landlord,bottom,mult,bombs,turn,lead,trick,sec,of`，seats 多带 `left` 和 `bid`，trick 为这一轮每个座位出的牌，sec 为这一手剩余秒数，of 为这一手的总秒数），其他座位收到带新成员 id 的 `ddz_seat`。发 `ddz_leave` 离桌的成员留在房间里，座位托管到这局结束，结算时照常收到 `ddz_result`；离桌后再离开房间又加入的，和掉线一样拿回座位。三个座位都离开了房间时这一局作废，押金退回（`ddz_over` `gone`）。对局中的成员不能被房主移出（`in_duel`）。
- `ddz_over` 的 reason：`declined`、`timeout`、`gone`（by 为离开的成员）、`nobid`、`no_shards`、`ddz_cap`、`ddz_locked`、`error`。扣过的押金都已退回。
- 只结算一次：服务端在内存里先把牌桌标为结算中再访问数据库，数据库里用 `UPDATE ddz_games SET state=... WHERE id=? AND state='open'` 的条件更新确认，只有第一次成功的结算发碎片。
- 新加入房间的成员收到房间里进行中牌桌的 `ddz_live {on:true}`，客户端用它在成员列表里标出牌局中的成员。
- 余额：客户端收到 `ddz_deal`、`ddz_state`、`ddz_result`、`ddz_over` 后重新读一次 `GET /api/me`。

## 数据迁移

刮刮乐新增 `scratch_cards` 表和 `players.scratch_pity` 列，启动时自动补上。已揭开的卡保留 30 天，启动时清理更早的。

猜拳新增 `duels` 表（启动时自动创建）：扣款时写入一行，state 从 `open` 变为 `won`（winner 为赢家存档）或 `refunded`，只变一次。房间只在内存里，服务端重启后上次没结算的对局没法继续，启动时把 `open` 的对局全部退款。

斗地主新增 `ddz_games` 和 `ddz_seats` 表（启动时自动创建）：扣押金时写入一局和三个座位，state 从 `open` 变为 `settled`（`ddz_seats.delta` 为每个座位的输赢，`burnt` 为销毁的碎片）或 `refunded`，只变一次。牌桌只在内存里，启动时把 `open` 的对局全部退还押金。


首次启动新版本时，旧碎片乘 16，旧抽卡次数和箱余额每份换成 160 碎片，随后清零旧余额。迁移由 skin_pity 列的存在性标记，只执行一次。已拥有物品、draw_pity 大隐藏进度和 drawn_total 累计次数保留。发布前备份数据库并在备份副本验证换算；回滚时同时恢复匹配版本的数据库。
