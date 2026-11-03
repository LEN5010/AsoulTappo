# AsoulTappo

> 🇬🇧 **English:** A fan-made, open-source "desktop pet + rooms" app for A-SOUL fans. Your pet reacts to your keyboard/mouse; in a room (up to 20 people, joined by Room ID) you see each other's pets, emotes and taps. Self-hosted backend. **Early alpha: Tauri 2 + Vue 3 client (replaces the original PyQt6 one), not yet verified on a real Windows desktop.**

## 简介

AsoulTappo 是一个面向 A-SOUL 粉丝的桌宠 + 房间应用:每个人桌面上都有一只小桌宠,进入同一个**房间(Room ID,最多 20 人)**后,可以互相看到对方的桌宠、表情和点击(敲击)。服务端可自行部署。

客户端以 [ASoul-Little-Bun](https://github.com/Evelynall/ASoul-Little-Bun) 为起点(素材与交互设计),现已用 Tauri 2 + Vue 3 重写,并增加联机能力。

## 🙏 致谢 / Credits

**本项目的桌宠客户端(代码、素材与设计)源自 [Evelynall/ASoul-Little-Bun](https://github.com/Evelynall/ASoul-Little-Bun)(作者 [@Evelynall](https://github.com/Evelynall)),并已获得原作者的许可。** 衷心感谢原作者的创作与开源!

- 原仓库使用 **GPL v2** 协议,本项目作为衍生作品同样以 **GPL-2.0** 发布,并保留原有的版权与协议声明。
- 原仓库的 PyQt6 代码原样保留在 `legacy/pyqt-client/`(含原 README `README.upstream.md`),新的 Tauri 客户端沿用其角色素材与图层/动画的设计思路,并保留原项目的版权与 GPL-2.0 声明。

*The desktop-pet client is derived from [Evelynall/ASoul-Little-Bun](https://github.com/Evelynall/ASoul-Little-Bun) (GPL-2.0), used with the original author's permission.*

## 🎴 素材、收藏与主题(Phase 2)

- **A-SOUL 五位角色**(嘉然 / 乃琳 / 贝拉 / 心宜 / 思诺)的表情、B 站装扮主题、收藏集卡片与头像框 / 徽章,详见 [ASSETS.md](ASSETS.md)(来源、压缩配方、素材包结构、稀有度规则)。
- **主题皮肤**:17 套装扮(默认「嘉然今天吃什么」内置,其余从服务器素材包按需加载),映射到面板背景、顶栏、底部标签栏、点赞动画、加载动画与角色主题色。
- **图鉴与开箱**:敲得越多宝箱越多(服务器记录**点击次数**,每 600 次或 10 个活跃分钟一个,有每日上限与保底),开出 54 张卡(普通 / 稀有 / 史诗 / 传说),史诗卡可看视频;未获得的卡显示为剪影。数据存于服务端 SQLite。
- **表情面板**:375 个表情按角色 / 套组分组,另有主题专属的动态点赞。
- **头像框 / 徽章**:集卡解锁,在房间成员列表中展示。
- 支持系统「减少动态效果」与键盘焦点样式。全部非商业、无任何付费。

> 素材版权归 A-SOUL / 乐华娱乐及原作者所有,本项目为非商用粉丝作品,**仅限 5 位角色**,详见 [ASSETS.md](ASSETS.md) 与下方免责声明。重新生成素材:`python scripts/build_assets.py`(需要 Pillow、ffmpeg 与原始素材目录)。

## 状态

🚧 **早期阶段(early alpha)**。技术栈已从原项目的 PyQt6 **更换为 Tauri 2 + Vue 3 + TypeScript**。

**已可用**
- `client/`:Tauri 桌宠客户端——透明置顶无边框窗口、全局键鼠钩子(Rust,**只统计次数**)、分层桌宠渲染(键盘按下弹跳 / 鼠标跟随 / 左右键点击图)、角色切换(沿用原项目素材)、托盘(显示隐藏 / 点击穿透 / 面板)、设置持久化、房间面板(创建房间、按 Room ID 加入、成员列表、表情选择器、远端成员迷你桌宠 + 点击 `+N` 气泡 + 表情)、WebSocket 客户端(100–200ms 点击合并、心跳、断线自动重连并重新加入)
- `server/`:FastAPI + WebSocket 房间服务(房间在内存,最多 20 人,随机长房间号,CORS,pytest 测试);另有 SQLite 持久化的玩家进度 / 开箱 / 收藏 HTTP API 与素材包托管(`/packs`)
- `protocol/`、`deploy/`、`docs/`、CI(服务端测试 / 前端构建与类型检查 / Windows 上 `cargo check`)

**占位 / 未完成**
- 窗口多显示器 / 高 DPI 适配未充分测试;点击穿透只能从托盘菜单关闭
- 无安装包发布与自动更新;无限流、房间口令等加固
- 原项目的自定义图层、按键显示、按键水平位移等功能**未移植**(为隐私起见不会再向界面暴露具体按键)
- 仅面向 Windows(macOS / Linux 未测试)

## 目录结构

```
client/    Tauri 2 + Vue 3 + TS 桌宠客户端(src/ 前端,src-tauri/ Rust:全局钩子、托盘、窗口)
server/    FastAPI + WebSocket 房间服务 + 开箱 / 收藏 API(app/, tests/)
assets-packs/  服务器托管的素材包(卡片原图 / 视频 / 主题大图)+ manifest.json / index.json
scripts/   build_assets.py 素材压缩与 manifest 生成
ASSETS.md  素材来源、压缩与稀有度说明
protocol/  PROTOCOL.md 消息协议(只传点击次数,不传按键内容)
deploy/    Dockerfile、docker-compose.yml、Caddyfile 示例
docs/      ARCHITECTURE.md 架构说明
legacy/    pyqt-client/ —— 原 ASoul-Little-Bun 的 PyQt6 代码,仅作参考与署名保留
.github/   CI
```

## 运行

### 服务端

```bash
cd server
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q                                        # 运行测试
uvicorn app.main:app --host 0.0.0.0 --port 8000  # 启动
# 健康检查: http://localhost:8000/healthz   WebSocket: ws://localhost:8000/ws
```

Docker 部署示例(含 Caddy 自动 HTTPS):

```bash
cd deploy
DOMAIN=tappo.example.com docker compose up -d --build
```

镜像从仓库根目录构建(含 `assets-packs/`),SQLite 存于卷 `server_data`(`ASOULTAPPO_DB`,默认 `data/asoultappo.db`);素材包目录可用 `ASOULTAPPO_PACKS` 覆盖。

升级本次点击结算修复时，服务端与客户端一起更新。活动 API 新增 `session` 和 `sequence`；服务端启动时创建计数额度与批次序号表，沿用现有玩家进度。详见 [协议升级说明](protocol/PROTOCOL.md#upgrade)。

### 客户端(Windows)

准备:[Node.js 20+](https://nodejs.org/)、[Rust(rustup)](https://rustup.rs/) + MSVC 生成工具(Visual Studio Build Tools,勾选“使用 C++ 的桌面开发”),系统自带 WebView2(Win10/11 通常已有)。详见 [Tauri 前置要求](https://tauri.app/start/prerequisites/)。

```powershell
cd client
npm install
npm run tauri dev        # 开发模式(首次编译 Rust 较慢)
npm run tauri build      # 打包安装程序(NSIS),产物在 src-tauri/target/release/bundle/
```

使用:先启动服务端(默认 `http://localhost:8000`),点桌宠右上角 ⚙(鼠标悬停显示)或托盘菜单打开面板 → “创建房间”或输入 Room ID 加入;在“设置”里改昵称和角色；修改服务器地址后点“应用服务器”，再加入新服务器的房间。分享 Room ID 给朋友即可同房。

仅调试前端界面(无桌面壳,用页面内键鼠事件模拟):

```bash
cd client
npm install
npm run dev     # http://localhost:1420
npm test        # vitest
npm run build   # vue-tsc 类型检查 + vite build
```

> 原 PyQt6 版本保留在 [`legacy/pyqt-client/`](legacy/pyqt-client/),不再维护;其更新检查仍指向原仓库。

## 路线图(MVP)

1. **Phase 0 — 骨架**:仓库结构、服务端原型、协议草案、CI ✅
2. **Phase 1 — 新客户端 + 联机最小闭环**(当前 PR):Tauri + Vue 桌宠、全局钩子、房间面板、同屏远端桌宠、重连 🟡 (待 Windows 实机验证)
3. **Phase 2 — 打磨**:多显示器 / 高 DPI、拖拽位置记忆、点击穿透热键、更多表情与动画、角色自定义图层
4. **Phase 3 — 加固与发布**:限流、房间口令、安装包与自动更新(指向本仓库 Release)、服务端指标
5. **Phase 4 — 扩展**:更多角色 / 皮肤导入、房间内排行榜、可选持久化

## 隐私

只发送**点击次数**,绝不上传按键内容、输入文本或鼠标坐标。详见 [protocol/PROTOCOL.md](protocol/PROTOCOL.md)。

## 许可证

[GPL-2.0](LICENSE)(因衍生自 GPL v2 项目而必须采用)。

## 免责声明

- 本项目为**非商业的粉丝作品**,与任何官方无关。
- 仓库中的 A-SOUL 角色图片、表情、装扮与卡片(`client/src/assets/characters/`、`client/public/assets/`、`assets-packs/`、`legacy/pyqt-client/img/`)**版权归其各自权利人所有(乐华娱乐 / 字节跳动 A-SOUL 相关方及原作者)**,GPL 协议**不适用于**这些美术素材,请勿用于商业用途。
- 如权利人希望移除相关素材,请在本仓库提交 Issue,我们会尽快处理。
- 本项目与**库洛游戏(Kuro Games)/ WuwaTappo** 及 **Bongo Cat** 无任何关联,也未使用其任何素材或品牌。
