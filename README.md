# AsoulTappo

面向 A-SOUL 粉丝的开源桌宠与同桌联机应用。桌宠会响应你的键盘与鼠标操作；加入同一个房间（最多 20 人）后，大家可以在桌面上互相看到彼此的桌宠、表情、键鼠动作与敲击计数。支持自行部署服务端。

客户端基于 [Evelynall/ASoul-Little-Bun](https://github.com/Evelynall/ASoul-Little-Bun) 的桌宠素材与分层动画设计，使用 **Tauri 2 + Vue 3 + TypeScript** 构建，并扩展了收藏集、表情收集与联机房间功能。

## 致谢 / Credits

**本项目的桌宠角色素材与分层交互源自 [Evelynall/ASoul-Little-Bun](https://github.com/Evelynall/ASoul-Little-Bun)（作者 [@Evelynall](https://github.com/Evelynall)），已获得原作者许可。**

- 本项目遵循 **GPL-2.0** 协议发布，原 PyQt6 客户端代码保留在 `legacy/pyqt-client/`。
- 界面字体使用 [Noto Sans SC](https://github.com/notofonts/noto-cjk) 与 [Barlow](https://github.com/jpt/barlow)，均为 SIL Open Font License 1.1。
- A-SOUL 标志与角色美术的版权归其权利人所有，不在 GPL-2.0 许可范围内。本项目为非官方粉丝作品。

## 功能概览

- **桌面桌宠**：收录嘉然、乃琳、贝拉、心宜、思诺五位分层桌宠，支持键盘弹跳、鼠标跟随、左右键点击反馈与置顶/点击穿透。
- **同桌联机**：输入或创建房间号即可与朋友同房（最多 20 人），伙伴的桌宠会显示在你的桌面上，可自由拖动并按房间记忆位置。
- **本地动态卡**：36 段动态卡视频随客户端内置，卡池预览、卡片详情和共鸣展示直接播放本地资源。
- **背包与图鉴**：475 个表情（26 套）、88 张卡片和 3 款皮肤。背包用于选择已拥有角色、皮肤和 8 个常用表情；图鉴查看全部内容，并用碎片兑换普通卡和普通、罕见、稀有表情。
- **此间共鸣**：五位成员共用一个池子，每次消耗 160 碎片，可获得卡片、表情和皮肤。大隐藏 0.5%、皮肤 0.5%、小隐藏与跳舞卡 4.5%、稀有表情 3%、罕见表情 6%、普通 85.5%（初始单抽普卡 45%、普通表情 40.5%）；重复表情返还 10 碎片，重复卡片累计数量。大隐藏 400 次、皮肤 200 次独立保底，进度分别累计。在线每分钟获得 16 碎片，上一分钟每 60 下有效敲击达到 ×5；新玩家赠送 1600 碎片。

素材构建说明见 [ASSETS.md](ASSETS.md)，前后端接口见 [protocol/PROTOCOL.md](protocol/PROTOCOL.md)，架构说明见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 目录结构

```
client/        Tauri 2 + Vue 3 + TS 客户端（src/ 前端界面，src-tauri/ 全局键鼠钩子、托盘与透明覆盖层窗口）
server/        FastAPI + WebSocket 房间与进度服务端（SQLite 持久化）
assets-packs/  服务端托管的高清卡面与主题素材包
scripts/       素材压缩与 manifest 生成脚本
protocol/      HTTP 与 WebSocket 协议说明
deploy/        Docker Compose 与 Caddy 部署配置
legacy/        原 ASoul-Little-Bun PyQt6 客户端存档
```

## 快速开始

### 1. 启动服务端

```bash
cd server
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q                                        # 运行测试
uvicorn app.main:app --host 0.0.0.0 --port 8000  # 启动服务
```

使用 Docker Compose 部署：

```bash
cd deploy
DOMAIN=tappo.example.com docker compose up -d --build
```

打包客户端默认连接 `http://121.36.224.230:8000`，可在设置里改。

### 2. 启动客户端

环境要求：[Node.js 20+](https://nodejs.org/)、[Rust](https://rustup.rs/) 及对应平台的 Tauri 依赖。

```bash
cd client
npm install
npm run tauri dev        # 启动桌面客户端
npm run tauri build      # 打包安装包
```

仅在浏览器中调试前端界面：

```bash
cd client
npm run dev              # http://localhost:1420
npm test                 # 运行单元测试
npm run build            # 类型检查与前端构建
```

## 许可证

[GPL-2.0](LICENSE)
