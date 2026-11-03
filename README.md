# AsoulTappo

> 🇬🇧 **English:** A fan-made, open-source "desktop pet + rooms" app for A-SOUL fans. Your pet reacts to your keyboard/mouse; in a room (up to 20 people, joined by Room ID) you see each other's pets, emotes and taps. Self-hosted backend. **Early skeleton — not usable yet.**

## 简介

AsoulTappo 是一个面向 A-SOUL 粉丝的桌宠 + 房间应用:每个人桌面上都有一只小桌宠,进入同一个**房间(Room ID,最多 20 人)**后,可以互相看到对方的桌宠、表情和点击(敲击)。服务端可自行部署。

客户端以 [ASoul-Little-Bun](https://github.com/Evelynall/ASoul-Little-Bun) 为起点,在此基础上增加联机能力。

## 🙏 致谢 / Credits

**本项目的桌宠客户端代码源自 [Evelynall/ASoul-Little-Bun](https://github.com/Evelynall/ASoul-Little-Bun)(作者 [@Evelynall](https://github.com/Evelynall)),并已获得原作者的许可。** 衷心感谢原作者的创作与开源!

- 原仓库使用 **GPL v2** 协议,本项目作为衍生作品同样以 **GPL-2.0** 发布,并保留原有的版权与协议声明。
- `client/` 目录下的代码是原仓库的导入版本(仅做最小改动,如新增 `client/net/`),原 README 保留为 `client/README.upstream.md`。

*The desktop-pet client is derived from [Evelynall/ASoul-Little-Bun](https://github.com/Evelynall/ASoul-Little-Bun) (GPL-2.0), used with the original author's permission.*

## 状态

🚧 **早期骨架(early skeleton)**:
- ✅ `server/`:FastAPI + WebSocket 房间服务(内存存储,加入/离开/点击批量计数/表情/状态广播,单房间最多 20 人),附 pytest 测试
- ✅ `protocol/`:协议草案
- 🟡 `client/`:原桌宠代码可运行;`client/net/` 仅为接口占位,**尚未接入 UI**
- ❌ 联机体验、远端桌宠渲染、打包发布:尚未开始

## 目录结构

```
client/    PyQt6 桌宠客户端(源自 ASoul-Little-Bun)+ net/ 联机接口占位
server/    FastAPI + WebSocket 房间服务(app/, tests/)
protocol/  PROTOCOL.md 消息协议(只传点击次数,不传按键内容)
deploy/    Dockerfile、docker-compose.yml、Caddyfile 示例
docs/      ARCHITECTURE.md 架构说明
.github/   CI(运行 server 测试)
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

### 客户端(Windows)

```bash
cd client
pip install -r requirements.txt
python main.py
```

> 注意:客户端中的更新检查(`update_checker.py` / `updater*.py`)目前仍指向原仓库的 Release,后续会改为指向本仓库或关闭。

## 路线图(MVP)

1. **Phase 0 — 骨架**(当前):仓库结构、服务端原型、协议草案、CI
2. **Phase 1 — 联机最小闭环**:客户端接入 `net/`(连接、加入房间、点击批量上报),界面可显示房间成员列表与点击数
3. **Phase 2 — 同屏桌宠**:渲染房间内其他人的桌宠、表情与点击动画;协议稳定
4. **Phase 3 — 完善与加固**:限流、房间口令、断线重连、设置界面、打包与更新渠道
5. **Phase 4 — 评估**:性能与稳定性评估,视情况重构 `main.py` 或更换 UI 框架

## 隐私

只发送**点击次数**,绝不上传按键内容、输入文本或鼠标坐标。详见 [protocol/PROTOCOL.md](protocol/PROTOCOL.md)。

## 许可证

[GPL-2.0](LICENSE)(因衍生自 GPL v2 项目而必须采用)。

## 免责声明

- 本项目为**非商业的粉丝作品**,与任何官方无关。
- 仓库中来自原项目的 A-SOUL 角色图片(`client/img/` 等)**版权归其各自权利人所有(乐华娱乐 / 字节跳动 A-SOUL 相关方)**,GPL 协议**不适用于**这些美术素材。
- 如权利人希望移除相关素材,请在本仓库提交 Issue,我们会尽快处理。
- 本项目与**库洛游戏(Kuro Games)/ WuwaTappo** 及 **Bongo Cat** 无任何关联,也未使用其任何素材或品牌。
