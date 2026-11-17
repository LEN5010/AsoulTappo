# 运维手册

官方服务端的部署、改数值、发版和撤回。只写流程，不写主机地址、密钥和数值；数值在私有仓库 AsoulTappo-config。

## 官方服务端的布局

服务端跑在 docker 容器 `asoultappo` 里，用 host 网络，uvicorn 监听 `127.0.0.1:8000`，由 nginx 的 `/tappo/` 反向代理。

| 路径 | 内容 |
| --- | --- |
| `/opt/asoultappo/app` | 运行的服务端代码，以只读方式挂到容器的 `/srv/app`。镜像里打包的代码是旧的，不用它 |
| `/opt/asoultappo/data` | SQLite 数据库，挂到 `/srv/data` |
| `/opt/asoultappo/config` | 私有数值文件 `economy.json` 和自动输入的判定规则 `guard.py`，挂到 `/srv/config`。没有这个挂载，服务端起不来 |
| `/opt/asoultappo/server.env` | 环境变量，其中有管理密钥、`ASOULTAPPO_ECONOMY=/srv/config/economy.json` 和 `ASOULTAPPO_GUARD=/srv/config/guard.py`。没有后一项时服务端照常运行，只是不判定自动输入 |
| `/root/asoultappo-build-<提交>` | 每次部署的构建目录：这次提交的 `server/app` 和资源包清单 |
| `/root` 下的 `asoultappo-*.db`、`asoultappo-app-*` | 每次切换前的数据库和代码备份 |

镜像 `asoultappo-server:<提交>` 只装依赖和资源包。代码和数值都走挂载，所以大多数部署不用重建镜像。

## 部署服务端

```bash
scripts/deploy-server.sh <主机> trial <提交> [--manifest]
scripts/deploy-server.sh <主机> switch <提交>
```

1. **trial**：上传这次提交的 `server/app` 和清单，准备好镜像，再用线上数据库的副本在 8011 端口起一个临时容器，检查三个接口是否返回 200，最后删掉临时容器。线上容器不受影响。
   - 清单 `assets-packs/manifest.json` 变了就加 `--manifest`：在线上镜像上加一层，只复制新清单。
   - 没加 `--manifest` 时，直接给线上镜像打上新标签。
2. **switch**：备份数据库和代码目录，把旧容器停掉（等 30 秒，让它把房间写进 `room_restore`），改名为 `asoultappo-<旧提交>` 留作回滚，同步代码后按固定参数起新容器。之后检查接口状态、房间是否全部读回、启动后有多少 503。
   - 启动后一分钟内出现几十到一百多个 `presence`、`activity` 的 503 是正常的：重启清空了账号缓存，会自己恢复。
3. **回滚**：switch 结束时会打印回滚命令：停掉新容器，把代码备份同步回去，再把旧容器改回原名并启动。

以下情况脚本不处理，要手动构建完整镜像：

- `server/requirements.txt` 变了
- 资源包里清单以外的文件变了

构建前先确认磁盘空间够用，pip 要换成国内镜像源。

## 只改数值

数值在私有仓库的 `server/config/economy.json`。改完提交私有仓库，然后：

```bash
scripts/deploy-server.sh <主机> economy <私有仓库>/server/config/economy.json
scripts/deploy-server.sh <主机> economy <私有仓库>/server/config/economy.json --apply
```

不带 `--apply` 只列出和线上文件不同的字段。确认后带 `--apply`：备份旧文件和数据库，替换文件，重启容器，检查接口。

如果改动会影响已经产生的状态（例如奖池的抽成比例），要在停机时另外换算，这一步脚本不做。

猜拳、斗地主、乐园这类玩法由数值文件里有没有对应的一节决定开关（`duel`、`doudizhu`、`park`）：没有这一节，服务端不提供这个玩法，客户端也不显示入口。新玩法上线要先部署带这个玩法的服务端，再往数值文件里加这一节；格式见 `server/economy.example.json` 和 `server/app/economy.py`。重启时进行中的猜拳和斗地主对局作废，下注和押金在启动时退回。

### 限定卡池

限定卡池写在数值文件的 `resonance.banners`（格式见 `server/app/banners.py` 和示例文件）。几条要记住的：

- 限定物品从写进文件、服务端重启的那一刻起就不在常驻池里，卡池没开始也一样。新皮肤要做成限定时，带这些皮肤的服务端上线前就要把卡池写进数值文件，否则它们会先进常驻池。
- 开始和结束到点自动生效，不用重启。结束后限定物品自动进入常驻池。
- 卡池的 `id` 是存档里限定保底的键，开了以后不要改；复刻用新的 `id`。
- 同一时间的两个卡池不能有相同的限定物品，时间不带时区、物品 id 写错时服务端不启动：换文件前先用 `deploy-server.sh ... economy` 的不带 `--apply` 那一步看差异，并在本机用这份文件跑一次 `Manifest.load()`。

## 最低版本和公告

在服务器上运行 `scripts/notice.py`，需要环境变量 `ASOULTAPPO_ADMIN_KEY`，值在 `server.env` 里。设置最低版本时，1.1.3 之前的客户端也会一起被挡在外面。

## 发版

1. 改 `client/src-tauri/tauri.conf.json` 的版本号。服务端改动要先部署，再发客户端。
2. 推 `test-<版本>-rc.<n>` 标签，`debug-build.yml` 会按正式版方式打包。在 Windows 测试机上装一次，确认桌面透明、桌宠和面板正常。只测调试版不够，调试版和正式版走的代码路径不同。
3. 写 `release.yml` 里的 `releaseBody`：技术中性、一条一句，数值改动写不写由维护者决定。推 `v<版本>` 标签。
4. 两个平台都构建完以后，如果在 GitHub 网页上改过发版说明，要用 `gh release edit --notes-file` 再写一次，同时改 `latest.json` 的 notes。macOS 的任务后跑完，会把网页上改的内容覆盖掉。
5. 在主站仓库运行 `bun run tappo:release:upload`，把安装包同步到下载页。房间服务端会缓存发版列表 10 分钟。
6. 带新皮肤的版本：清单里新皮肤的 `since` 写成这个版本号。服务端带着这个清单部署后，更早的客户端抽不到这些皮肤。

Windows 安装包有 100 MiB 的上限（蓝奏云），发版前看一下大小。

## 撤回一个版本

1. `gh release edit v<版本> --draft=true`，`releases/latest/download/latest.json` 会回到上一版。
2. 主站下载目录的 `releases.json` 删掉这个版本，删之前先备份。
3. 服务端如果也要退回，切回上一个容器。不退回也要重启一次，清掉发版列表的缓存。

已经更新的玩家不会自动降级。
