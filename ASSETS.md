# 素材说明 / Assets

本项目收录五位角色相关素材：**嘉然、乃琳、贝拉、心宜、思诺**。

## 目录与体积

| 路径 | 内容 | 体积 |
|---|---|---|
| `client/public/assets/` | **客户端内置**：表情（375 个 / 21 套）、卡片缩略图（414×621）、36 段动态卡视频、默认主题部件 | ≈ 91 MB |
| `assets-packs/` | **服务端素材包**（按需加载）：卡片高清原图（1080 宽）及扩展主题资源 | ≈ 27 MB |

### 素材包结构

```
assets-packs/
  manifest.json         完整元数据（v4 角色与皮肤、卡片系列与稀有度档位、表情套组、初始物品与共鸣经济配置）
  index.json            素材包文件清单（path / size / sha256）
  cards/<系列>/         卡片原图 *.webp
  themes/<主题 id>/     扩展主题资源
```

动态卡视频位于 `client/public/assets/cards/<系列>/*.mp4`，清单中的 `video` 使用 `bundle:` 引用。全部动画时长和音轨保留，服务端素材包仅包含高清静态卡面与主题资源。

服务端将该目录挂载在 `/packs/...`，并通过 `GET /api/manifest` 提供清单（路径可通过环境变量 `ASOULTAPPO_PACKS` 指定）。

### 素材引用格式

- `bundle:<path>` → 客户端内置资源（`assets/<path>`）
- `pack:<path>` → 服务端托管资源（`<server>/packs/<path>`）

## 桌宠皮肤

在 `client/src/assets/characters/` 下新建以成员名开头的文件夹（如 `贝拉山海经/`），放入透明背景的 `bgImage.png`，构图与成员原皮保持一致。

- 键盘、鼠标、点击图层可省略，缺失时沿用成员原皮；主题色、初始表情和头部位置跟随成员。
- 在 `scripts/asset_catalog.py` 的 `SKINS` 中增加名称和所属 member，重新生成两份 manifest。皮肤随客户端发布，并自动进入此间共鸣池。对方客户端缺少该皮肤素材时显示成员原皮。

## 构建脚本

运行 `python scripts/build_assets.py [--src <原始素材目录>] [--force]`（需安装 Pillow 与 ffmpeg），可从原始素材生成压缩产物与 `manifest.json`。

只补指定收藏集时，可使用成员目录形式的素材源，保留现有主题、表情和其他收藏集：

```sh
python scripts/build_assets.py --src /path/to/A-SOUL装扮收藏集大全 --cards-only --series reverie casket
```

| 类型 | 处理规格 |
|---|---|
| 表情 | 等比缩放到 ≤ 320px，WebP |
| 卡片 | 原图 1080 宽 WebP q82；缩略图 414×621 |
| 卡片视频 | 客户端内置，H.264 640px 宽、30 fps、crf 28，AAC 48k，`+faststart` |

## 界面字体与图形

| 文件 | 内容 | 来源与许可 |
|---|---|---|
| `client/src/assets/fonts/NotoSansSC-subset.woff2` | 正文字体，保留 400–800 字重，按界面用字裁剪 | [Noto Sans SC](https://github.com/notofonts/noto-cjk)，SIL Open Font License 1.1 |
| `client/src/assets/fonts/BarlowCondensed-ExtraBold.woff2` | 英文与数字粗体 | [Barlow](https://github.com/jpt/barlow)，SIL Open Font License 1.1 |
| `client/src/assets/patterns/halftone.svg` | 半调网点，作为 CSS 遮罩使用 | 由脚本生成 |
| `client/src/assets/brand/asoul-logo.svg` | A-SOUL 标志的矢量描摹，作为 CSS 遮罩使用 | 版权归权利人所有，见同目录 `COPYRIGHT.md` |
| `client/src/assets/brand/side-cat.svg` | 侧栏羊驼线稿，依参考图手绘，作为 CSS 遮罩使用 | 线稿为项目绘制，原形象版权归权利人所有 |

新增界面文字后运行 `python scripts/build_ui_assets.py --noto <NotoSansSC[wght].ttf>`（需安装 fonttools 与 brotli）重新裁剪字体。未包含在子集内的字符会回退到系统字体。

## 收藏集与表情规则

收藏集共 8 套、88 张卡牌：绽放（24）、绚烂心迹（9）、此间为爱（9）、沉沦醉与爱（9）、时空旅人（9）、双声巡梦（10）、绮梦漫游（9）、匣中惊鸿（9）。

| 收藏集 | 大隐藏 | 小隐藏 |
|---|---|---|
| 绽放 | 时序系列三张 | 舞台系列三张 |
| 绚烂心迹 | 绘心物语 | 天使奇遇 |
| 此间为爱 | 珍馐派对 | 月纱花信 |
| 沉沦醉与爱 | 蝶影共醉 | 绮梦妖狐 |
| 时空旅人 | 时空行者 | 引爆枝江大楼 |
| 双声巡梦 | 巡梦漫游 | 魔女契约 |
| 绮梦漫游 | 歌剧之星 | 纯白誓约 |
| 匣中惊鸿 | 月下童话 | 夜的终章 |

所有卡片进入同一个此间共鸣池。大隐藏卡为 legendary，小隐藏和带视频的跳舞卡为 epic，其余卡为 common；原有 tier 字段保留用于卡册展示。三张心宜与思诺共有卡各自只入池一次。

- **共鸣概率**：大隐藏 0.5%、皮肤 0.5%、史诗 4.5%、稀有表情 3%、罕见表情 6%、普通 85.5%。普通档先按普卡 62.65 : 表情 22.85 的权重选类型，再在类型内优先补缺；对应类型集齐后产生重复。初始单抽普卡为 62.65%、普通表情为 22.85%。高档集齐后概率并入普通档。
- **表情与皮肤**：共 375 个表情，每位成员 4 个初始表情；355 个非初始表情入池，普通 280 个、罕见 60 个、稀有 15 个。脑洞波三套为罕见，绽放三套为稀有，其他为普通。3 款山海经皮肤通过共鸣解锁，背包展示全部皮肤，未解锁项压暗且不可选择。
- **图鉴卡册**：系列栏含「全部」；未拥有卡保持彩色并压暗。目录内可见且已拥有的动态卡循环播放；所有未拥有卡使用静态缩略图，跳舞卡同样显示其静态封面。滚出可视区域的视频卸载，回到视野时开始播放。共鸣页的卡池演示独立于持有状态，动态卡保持正常亮度并自动播放。
- **碎片**：共鸣每次 160。重复表情返还 10 碎片，重复卡片累计持有数量。普通兑换价 480、罕见 960、稀有 1600；皮肤、史诗、传说和初始表情按共鸣与初始规则获取。
