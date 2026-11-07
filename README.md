<p align="center">
  <img src="client/src-tauri/icons/128x128.png" width="96" height="96" alt="AsoulTappo">
</p>

<h1 align="center">AsoulTappo</h1>

<p align="center">
  A-SOUL 五位成员的桌面桌宠。敲键盘、动鼠标，桌宠跟着动；和朋友进同一个房间，就能在桌面上看到彼此的桌宠。
</p>

<p align="center">
  <a href="https://len5010.top/download?app=tappo"><b>下载</b></a> ·
  <a href="https://github.com/LEN5010/AsoulTappo/releases">GitHub Releases</a> ·
  Windows / macOS
</p>

非官方粉丝作品，开源，免费。

## 安装

**Windows**：下载 `AsoulTappo_<版本>_x64-setup.exe` 并运行。安装包没有 Microsoft 签名，SmartScreen 拦截时点更多信息，再选仍要运行。

**macOS**：下载 `.dmg`，Apple 芯片和 Intel 用同一个包。把 AsoulTappo 拖进应用程序。第一次打开如果提示已损坏或无法验证开发者，在终端执行：

```bash
xattr -dr com.apple.quarantine /Applications/AsoulTappo.app
```

桌宠跟随键鼠需要在系统设置的隐私与安全性 → 辅助功能里允许 AsoulTappo。

**更新**：设置里点检查更新，有新版本时会自动下载安装。1.0.0 之前的测试版不能自动更新，需要重新下载安装一次。

## 功能

- **桌宠**：嘉然、贝拉、乃琳、心宜、思诺。敲键盘会跳，会跟随鼠标，左右键点击有反馈。可以置顶，也可以开点击穿透。
- **同桌**：创建房间或输入房间号，最多 20 人。伙伴的桌宠、表情和敲击计数会出现在你的桌面上，位置可以拖，按房间记住。
- **收集**：475 个表情（26 套）、85 张卡片（其中 33 张动态卡）和 9 款皮肤。背包里选角色、皮肤和 8 个常用表情；图鉴里看全部内容，并可以用碎片兑换普通卡和普通、罕见、稀有表情。
- **账号**：可以登录 Asasfans 账号，和 Asasfans Web、Asasfans Next 通用，换电脑也能拿回存档。不登录时使用游客存档。

### 此间共鸣

五位成员共用一个池子，每次 160 碎片。

| 结果 | 概率 |
|---|---|
| 大隐藏 | 0.5%，400 次保底 |
| 皮肤 | 0.5%，200 次保底 |
| 小隐藏与跳舞卡 | 4.5% |
| 稀有表情 | 3% |
| 罕见表情 | 6% |
| 普通卡 | 45% |
| 普通表情 | 40.5% |

两个保底分开计数。重复的表情返还 10 碎片，重复的卡片累计数量。

碎片的来源：新玩家送 1600；在线每分钟 16，上一分钟敲得越多倍数越高，满 60 下是 5 倍。

## 自己部署服务端

客户端默认连官方服务器 `https://len5010.top/tappo`，可以在设置里换成自己的地址。

```bash
cd deploy
DOMAIN=tappo.example.com docker compose up -d --build
```

这会启动服务端和 Caddy，Caddy 自动申请 HTTPS 证书。自建服务器没有配 `MAIN_API_URL` 时不能登录 Asasfans 账号，只有游客存档；检查更新仍然读取官方的版本列表。

## 开发

需要 [Node.js 20+](https://nodejs.org/)、[Rust](https://rustup.rs/) 和对应平台的 [Tauri 依赖](https://tauri.app/start/prerequisites/)；服务端需要 Python 3.12。

```bash
# 服务端
cd server
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q
uvicorn app.main:app --port 8000

# 客户端
cd client
npm install
npm run tauri dev        # 桌面客户端
npm run dev              # 只在浏览器里调界面，http://localhost:1420
npm test                 # 单元测试
npm run build            # 类型检查和前端构建
```

`npm run tauri build` 在 Windows 上生成 NSIS 安装器，在 macOS 上生成 `.app` 和 `.dmg`。配置里开了更新包签名，本机没有 `TAURI_SIGNING_PRIVATE_KEY` 时加 `--no-sign`。

发版：推送 `v*` 标签后，GitHub Actions 先打 Windows 安装器，再打 macOS 通用 DMG，写进同一个 Release 并更新 `latest.json`。标签要和 `client/src-tauri/tauri.conf.json` 里的版本一致。

```
client/        Tauri 2 + Vue 3 + TypeScript 客户端；src-tauri/ 是全局键鼠钩子、托盘和透明覆盖层窗口
server/        FastAPI + WebSocket 的房间和存档服务，SQLite 存储
assets-packs/  服务端提供下载的高清卡面和主题素材
scripts/       素材压缩和 manifest 生成
protocol/      HTTP 和 WebSocket 协议
deploy/        Docker Compose 和 Caddy 配置
```

更多文档：[素材构建](ASSETS.md)、[协议](protocol/PROTOCOL.md)、[架构](docs/ARCHITECTURE.md)。

## 致谢

- 角色皮肤由画师 [神秘三文鱼_](https://space.bilibili.com/2061322519) 绘制。
- 界面字体使用 [Noto Sans SC](https://github.com/notofonts/noto-cjk) 和 [Barlow](https://github.com/jpt/barlow)，均为 SIL Open Font License 1.1。
- A-SOUL 标志和角色美术的版权归其权利人所有，不在本项目的许可范围内。
- 项目最早基于 [Evelynall/ASoul-Little-Bun](https://github.com/Evelynall/ASoul-Little-Bun)，五位成员的基础桌宠素材来自该项目，已获作者许可。

## 许可证

[GPL-2.0](LICENSE)
