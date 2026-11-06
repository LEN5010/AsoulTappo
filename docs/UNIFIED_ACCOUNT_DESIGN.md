# 主站、Asasfans 与桌宠的统一账号方案

状态：实施方案。先实现第 2 节（主站后端）和第 3 节（Asasfans），第 4 节（桌宠）随后接入。

## 1. 结论

- 主站（dynamic_asoul）现有的 users 表是唯一账号库。Asasfans 和桌宠都登录主站账号，沿用已有用户 ID、密码和恢复码。
- 登录方式是授权码加 PKCE：客户端打开系统浏览器到主站登录并确认，拿回一次性授权码，再用只有客户端自己知道的随机串换取令牌。PKCE 保证授权码被别的程序截走也换不到令牌。
- 换来的令牌就是主站 sessions 表里的一行，客户端放在请求头 `Authorization: Bearer <令牌>` 里使用。现有的会话校验、authVersion（账号安全版本，改密码或找回时加一，旧会话全部失效）和撤销逻辑直接覆盖客户端。
- 首期只做上面这套授权码登录。三端都是自营客户端，用不到 OIDC 的 ID Token、JWKS、discovery。以后接入第三方或自建服时，再在这套流程上补 OIDC。
- 业务数据各管各的：内容收藏在主站 user.db，桌宠的卡片、碎片、保底在桌宠服务端，桌宠服务端只记录主站用户 ID 和存档的对应关系。
- 邮箱用于验证和找回密码，通过 Resend 的 HTTPS API 发信。邮箱是可选绑定，现有账号照常使用。

### 数据归属

| 数据 | 存放位置 | 使用方 |
| --- | --- | --- |
| 账号、密码、邮箱、恢复码、各设备登录状态 | 主站 user.db | 三端 |
| 动态、二创、小说收藏 | 主站 user.db 的 favorites | Web、Asasfans |
| Asasfans 收藏夹结构、稍后看、历史、订阅、音乐收藏 | App 本地 | App，首期不同步 |
| 桌宠卡片、皮肤、表情、碎片、保底、装备 | 桌宠服务端 SQLite | 桌宠 |
| 主站用户 ID 与桌宠存档的对应关系 | 桌宠服务端 account_links | 桌宠 |
| 窗口位置、缩放、伙伴摆放 | 各客户端本地 | 当前设备 |

## 2. 主站后端（dynamic_asoul）

API 对外地址是 `https://len5010.top/dynamics/api/`（nginx 同时转发 `/api/`），Web 页面在 `/dynamics/` 下。下文的接口路径按 API 内部的 `/api/...` 写。

新表和新列放在 `packages/db/user-migrations/0018_*.sql` 起的新迁移里，上线按仓库 AGENTS.md 的数据库规定先备份 user.db。

### 2.1 Bearer 令牌

- sessions 表加 `client_id TEXT`。Web 登录写 NULL，客户端换令牌时写客户端 ID。
- `apps/api/src/auth/session.ts` 的 `loadAuth`：有 `Authorization: Bearer` 时按令牌查 sessions，否则读 `sid` Cookie。两条路径的校验相同：用户 active、authVersion 一致、未过期。
- `AuthContext` 增加 `via: "cookie" | "bearer"`。`csrfGuard` 对 bearer 请求直接放行，CSRF 防护只针对浏览器自动携带的 Cookie。
- 客户端会话有效期 90 天，每次使用时剩余不足 45 天就续到 90 天，持续使用的设备一直保持登录。Web 会话保持现有的 30 天。
- `/api/auth/me` 对 bearer 请求同样返回 `user`，桌宠服务端用它确认身份。

### 2.2 授权码登录

客户端登记写在代码常量里，首期两个：

| client_id | 名称 | 允许的回调地址 |
| --- | --- | --- |
| `asasfans` | Asasfans | `asasfans://oauth/callback`；回环地址 `http://localhost:<任意端口>/callback` 和 `http://127.0.0.1:<任意端口>/callback`（Windows 用） |
| `asoultappo` | AsoulTappo 桌宠 | 回环地址 `http://127.0.0.1:<任意端口>/callback` |

回环地址回调指桌面客户端在本机临时开一个端口接收授权码。

流程：

1. 客户端生成 `code_verifier`（随机串）和 `state`，打开浏览器访问 `https://len5010.top/dynamics/oauth/authorize?client_id=…&redirect_uri=…&state=…&code_challenge=…&code_challenge_method=S256`。
2. Web 页面 `apps/web/src/pages/oauth/authorize.astro`：未登录时跳转登录页，登录后返回（`login.astro` 增加 `next` 参数，只接受站内路径）；已登录时显示确认按钮 `以 <用户名> 身份登录 <客户端名称>`。确认按钮防止本机其他程序在用户不知情时静默拿到令牌。
3. 确认后页面调用 `POST /api/oauth/authorize`（Cookie 加 CSRF），服务端校验 client_id 和回调地址，生成授权码，页面跳转到 `redirect_uri?code=…&state=…`。
4. 客户端调用 `POST /api/oauth/token`，提交 `grant_type=authorization_code`、`code`、`code_verifier`、`client_id`、`redirect_uri`。服务端校验通过后创建一行带 client_id 的 session，返回：

   ```json
   { "access_token": "<session id>", "token_type": "Bearer", "expires_in": 7776000, "user": { "id": "…", "username": "…" } }
   ```

5. `POST /api/oauth/revoke`（Bearer）撤销当前令牌，用于客户端退出登录。

授权码规则：32 字节随机数，库里只存 SHA-256；有效 5 分钟，只能使用一次；绑定 client_id、redirect_uri、code_challenge、user_id 和当时的 authVersion。回调地址按登记规则精确匹配，回环地址只放开端口。

新表：

```sql
CREATE TABLE oauth_codes (
  code_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  client_id TEXT NOT NULL,
  redirect_uri TEXT NOT NULL,
  code_challenge TEXT NOT NULL,
  auth_version INTEGER NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT
);
```

`/api/oauth/token` 套用现有 `createAuthRateLimit`。桌宠接入时，`/api/oauth/token` 和 `/api/oauth/revoke` 再允许 Tauri 窗口的来源跨域访问（`tauri://localhost`、`http://tauri.localhost`）。

### 2.3 设备管理

- 账号安全页的会话列表显示客户端名称（client_id 为空时显示浏览器和 user_agent）。
- 新增 `POST /api/account/sessions/:id/revoke`，退出指定设备。现有的退出其他设备、改密码、恢复码找回都会让客户端令牌一起失效。

### 2.4 收藏同步接口

Web 和 App 对同一份内容的记法不同。同步接口统一用内容键，主站负责和 favorites 表互相转换：

| 内容键 | 对应 favorites 行 | App 中的来源 |
| --- | --- | --- |
| `bili:<动态ID>` | `(dynamic, <动态ID>)` 和/或 `(fanart, <动态ID>)` | `bilibiliDynamic` |
| `douban:<话题ID>` | `(fanart, douban:<话题ID>)` | `doubanTopic` |
| `novel:<作品ID>` | `(novel, <作品ID>)` | App 暂无 |

规则：同一份源内容只算一份收藏。App 收藏 `bili:X` 时，主站用现有收藏读取的同一套查询判断 X 在动态库还是二创库，存在于哪边就写哪边；App 取消收藏时两边一起删除。Web 的收藏表和现有接口保持原样。

接口：

- `POST /api/favorites/sync`，body 为 `{ "ops": [{ "key": "bili:123", "op": "add" }, …] }`，每次最多 200 条，按顺序执行。加入和移除都是集合操作，重复提交结果相同。返回 `{ "unknown": [...] }`，列出主站内容库里找不到的键。
- `GET /api/favorites/keys`，每页最多 100 条，返回 `{ "items": [{ "key", "target", "addedAt", "item" }], "nextCursor" }`。`target` 是 `dynamic`、`fanart` 或 `novel`；`item` 和 `/api/favorites/items` 返回的条目格式相同，内容已下架时为 null。同一个 `bili:` 键在动态和二创里都有时可能出现两次，App 按键去重。

`bilibiliVideo` 和歌曲在主站没有对应内容，首期留在 App 本地。

### 2.5 邮箱绑定与找回

- users 加 `email TEXT`、`email_verified_at TEXT`；已验证邮箱建唯一索引。
- 新表 `email_tokens(token_hash, user_id, purpose, email, expires_at, used_at)`，purpose 为 `verify` 或 `reset`；链接有效 30 分钟，只能使用一次。
- `POST /api/account/email`：验证当前密码后给新邮箱发验证链接。
- `POST /api/account/email/verify`：消费验证链接，写入邮箱和验证时间。
- `POST /api/auth/password-reset/request`：输入用户名或已验证邮箱，有已验证邮箱就发找回链接，接口统一返回成功。
- `POST /api/auth/password-reset/confirm`：消费找回链接并设置新密码，authVersion 加一，所有设备重新登录。
- 发信模块直接请求 `https://api.resend.com/emails`。环境变量 `RESEND_API_KEY`、`MAIL_FROM=账号中心 <account@notify.len5010.top>`，链接域名用 `PUBLIC_SITE_URL`。
- 注册的 IP 限制目前是同一网络 24 小时内一个账号。三端共用账号后，宿舍和校园网会频繁触发，建议放宽到 5 个。

### 2.6 主站测试

- 授权码：PKCE 校验失败、授权码重复使用、过期、回调地址不匹配、client_id 不存在，各自返回错误。
- 改密码、恢复码找回、邮箱找回之后，旧的客户端令牌返回 401。
- bearer 请求不需要 CSRF 头，Cookie 请求仍然需要。
- 收藏同步：`bili:X` 同时存在于两个库时两边都写入；移除时两边都删除；未知键原样返回。
- 发信模块用注入的发送函数测试。

## 3. Asasfans

按该仓库 AGENTS.md 的规定，实施前把本节写进 `docs/next.md`。

### 3.1 登录

- 我的页增加账号入口 `登录主站账号`。用 `flutter_web_auth_2` 打开系统浏览器完成第 2.2 节的流程：Android、iOS、macOS 用 `asasfans://oauth/callback`，Windows 用回环地址。这是本次唯一新增的依赖。
- 令牌存进现有的 flutter_secure_storage。
- 令牌只附加在账号和收藏同步请求上（`oauth/*`、`favorites/*`、`auth/me`）。二创问号反馈等匿名请求保持不带令牌。
- 退出登录：调用 `oauth/revoke`，删除本地令牌，切回游客。任何账号请求返回 401 时同样切回游客，并提示重新登录。

### 3.2 本地收藏按账号区分

- 个人库 schema 升到 v12：collection_folders 和 collection_items 加 `owner TEXT NOT NULL`，主键带上 owner。游客的 owner 是 `local`，登录后是主站用户 ID。每个 owner 有自己的默认收藏夹。
- 收藏相关查询都带当前 owner。content_refs 存内容快照，各账号共用。稍后看、历史、订阅、音乐收藏和偏好设置首期保持设备级，所有账号共用。
- 首次登录某个账号时询问一次：`把本机收藏带进这个账号` 或 `从空白开始`。带进账号就是把 local 的收藏夹和条目复制一份到新 owner，并把其中可同步的条目写进待同步表。

### 3.3 同步

- 新表 `cloud_outbox(owner, key, op, queued_at, PRIMARY KEY(owner, key))`，待同步表。每个内容键只保留最新一次操作，和收藏改动写在同一个事务里。
- 收藏与否：条目在当前 owner 的任意一个收藏夹里就算已收藏。从未收藏变成已收藏时写 add；移出最后一个收藏夹，或删除收藏夹后条目不在任何收藏夹里时，写 remove。
- 参与同步的来源：`bilibiliDynamic` 对应 `bili:`，`doubanTopic` 对应 `douban:`。`bilibiliVideo` 留在本地。
- 同步时机：启动、登录后、回到前台、本地收藏改动后几秒。
- 同步过程：
  1. 把 cloud_outbox 分批提交到 `favorites/sync`。成功后删掉提交时读到的、queued_at 没变、且不在 `unknown` 里的行。`unknown` 的键继续留在表里，下次同步重试，本地照常显示。
  2. 拉取 `favorites/keys` 的全部分页。
  3. 云端有、本地没有的键：用返回的 `item` 和现有解析写入 content_refs，放进默认收藏夹。`item` 为 null 且本地没有快照的跳过。
  4. 本地有、云端没有、cloud_outbox 里也没有的可同步条目：从当前 owner 的所有收藏夹移除。
- Web 上新增的收藏由此进入 App 的默认收藏夹，App 的多收藏夹结构留在本地。

### 3.4 测试

按该仓库 AGENTS.md 只写直接相关的：同一个键先 add 后 remove 只留 remove；同步第 3、4 步的对账；切换账号后只看到当前 owner 的收藏。

## 4. 桌宠（AsoulTappo，随后接入）

### 4.1 存档码

可以和主站、Asasfans 并行做，只改客户端：设置里显示当前游客 token，支持复制，以及在新设备粘贴替换本地 token。重装和换电脑立刻能恢复存档。绑定账号后存档码作废，设置里改为显示账号。

### 4.2 身份解析

现在 `server/app/game.py` 的 `player_id_for(token)` 用游客 token 的哈希直接当玩家 ID。改为在 `server/app/main.py` 集中解析请求身份，Game 的方法改为接收已解析的玩家 ID：

- 请求带 `Authorization: Bearer`：用这个令牌请求 `{MAIN_API_URL}/auth/me`，得到主站用户 ID，再查 account_links 得到玩家 ID。查询结果按令牌哈希缓存 5 分钟。主站返回 401 时回 401 `account_expired`。
- 请求带 `X-Player-Token`：沿用现有哈希。这个玩家 ID 已经绑定账号时回 401 `save_linked`，客户端提示登录主站账号。
- WebSocket 的 join 消息增加可选的 `accountToken`，按同样规则解析，`profile_for` 和 `owns_emote` 改为接收玩家 ID。

新表：

```sql
CREATE TABLE IF NOT EXISTS account_links (
  main_user_id TEXT PRIMARY KEY,
  player_id TEXT NOT NULL UNIQUE,
  linked_at REAL NOT NULL
);
```

一个主站账号对应一个官方桌宠存档，一个存档对应一个主站账号。

### 4.3 接口

- `GET /api/info` 返回 `{ "accountLogin": bool }`。设置了 `MAIN_API_URL` 环境变量（官方服填 `https://len5010.top/dynamics/api`）时为 true，自建服不设置，客户端就只显示游客模式。
- `GET /api/account`（Bearer）返回是否已绑定，以及存档摘要（碎片、持有数量、最后活跃时间）。
- `POST /api/account/link`（Bearer，可选带 `X-Player-Token`）：
  - 账号未绑定，带了游客 token：把这份游客存档绑定到账号，玩家 ID 和全部库存原样保留。
  - 账号未绑定，没带游客 token：新建一份存档并绑定，按新玩家发放初始内容。
  - 账号已有存档：回 409 `account_has_save`，附上账号存档和当前游客存档的摘要，客户端让用户选择使用账号存档或继续当游客。两份存档分别保留。
  - 游客存档已绑定其他账号：回 409 `save_linked`。

### 4.4 客户端登录

- `/api/info` 为 true 时，设置里显示 `登录主站账号`。用 Tauri 打开系统浏览器，本机回环端口接收授权码，令牌存进系统钥匙串。登录后调用 `/api/account/link`，按返回结果处理选择。
- 切换账号时一起切换 HTTP 令牌、活动上报和房间连接。

### 4.5 桌宠测试

- 绑定后游客存档的碎片、卡片、保底、装备不变，旧游客 token 返回 `save_linked`。
- 同一账号在另一台设备上绑定时返回 `account_has_save` 和两份摘要。
- HTTP 和 WebSocket 用同一个令牌解析出同一个玩家 ID。
- 主站请求用注入的假实现测试，缓存期内不重复请求，主站返回 401 时接口返回 `account_expired`。
- 未设置 `MAIN_API_URL` 时，`/api/info` 返回 false，账号接口不可用，游客功能照常。

## 5. 实施顺序

1. 主站 2.1 到 2.3：Bearer 令牌、授权码登录、设备管理。
2. 主站 2.4：收藏同步接口。
3. Asasfans 第 3 节：登录、按账号区分收藏、同步。依赖前两步上线。
4. 主站 2.5：邮箱绑定与找回。
5. 桌宠第 4 节。4.1 存档码随时可以做，其余依赖第 1 步上线。

主站每一步单独发版。

## 6. 发信服务现状

2026-11-06 已完成域名验证和实际收件测试：

| 项目 | 当前配置 |
| --- | --- |
| 服务商、接入方式 | Resend，HTTPS API |
| 发信域名 | notify.len5010.top，DNS 在腾讯云 DNSPod，已添加 DKIM TXT 和两条发送用 CNAME |
| 域名状态 | Verified，区域 us-east-1 |
| 发件人 | 账号中心 <account@notify.len5010.top> |
| 测试 | 已向 QQ 邮箱发送，Resend 状态 delivered，已确认收到 |

API key 在本仓库 `.local/resend-setup.md`（Git 已忽略），主站上线时写进 lbot 的服务端环境变量。DMARC 在腾讯云给 `_dmarc.notify` 加一条 TXT 记录即可，例如 `v=DMARC1; p=none`。

## 参考

- [RFC 8252](https://www.rfc-editor.org/rfc/rfc8252.html)：原生应用通过系统浏览器授权，回环地址回调。
- [RFC 7636](https://www.rfc-editor.org/rfc/rfc7636.html)：PKCE。
- [flutter_web_auth_2](https://pub.dev/packages/flutter_web_auth_2)：Flutter 的系统浏览器授权。
- [Resend 发信接口](https://resend.com/docs/api-reference/emails/send-email)
