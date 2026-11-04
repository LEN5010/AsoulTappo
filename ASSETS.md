# 素材说明 / Assets

本项目收录五位角色相关素材：**嘉然、乃琳、贝拉、心宜、思诺**。

## 目录与体积

| 路径 | 内容 | 体积 |
|---|---|---|
| `client/public/assets/` | **客户端内置**：表情（375 个 / 21 套）、卡片缩略图（414×621）、默认主题部件 | ≈ 15 MB |
| `assets-packs/` | **服务端素材包**（按需加载）：卡片高清原图（1080 宽）、动态卡视频（32 个）及扩展主题资源 | ≈ 103 MB |

### 素材包结构

```
assets-packs/
  manifest.json         完整元数据（角色、卡片系列与稀有度档位、表情套组、初始物品与碎片经济配置）
  index.json            素材包文件清单（path / size / sha256）
  cards/<系列>/         卡片原图 *.webp 与动态视频 *.mp4
  themes/<主题 id>/     扩展主题资源
```

服务端将该目录挂载在 `/packs/...`，并通过 `GET /api/manifest` 提供清单（路径可通过环境变量 `ASOULTAPPO_PACKS` 指定）。

### 素材引用格式

- `bundle:<path>` → 客户端内置资源（`assets/<path>`）
- `pack:<path>` → 服务端托管资源（`<server>/packs/<path>`）

## 桌宠皮肤

在 `client/src/assets/characters/` 下新建以成员名开头的文件夹（如 `贝拉山海经/`），放入透明背景的 `bgImage.png`，构图与成员原皮保持一致。

- 键盘、鼠标、点击图层可省略，缺失时沿用成员原皮；主题色、初始表情和头部位置跟随成员。
- 皮肤随客户端发布，服务端无需更新。对方客户端没有这个皮肤时显示成员原皮。

## 构建脚本

运行 `python scripts/build_assets.py [--src <原始素材目录>] [--force]`（需安装 Pillow 与 ffmpeg），可从原始素材生成压缩产物与 `manifest.json`。

| 类型 | 处理规格 |
|---|---|
| 表情 | 等比缩放到 ≤ 320px，WebP |
| 卡片 | 原图 1080 宽 WebP q82；缩略图 414×621 |
| 卡片视频 | H.264 720p，crf 28，AAC 64k，`+faststart` |

## 界面字体与图形

| 文件 | 内容 | 来源与许可 |
|---|---|---|
| `client/src/assets/fonts/NotoSansSC-subset.woff2` | 正文字体，保留 400–800 字重，按界面用字裁剪 | [Noto Sans SC](https://github.com/notofonts/noto-cjk)，SIL Open Font License 1.1 |
| `client/src/assets/fonts/NotoSansSC-Slanted-subset.woff2` | 标题字体，由 Noto Sans SC Black 倾斜 8° 生成，按界面用字裁剪 | 同上，修改版以 Noto Sans SC Slanted 命名 |
| `client/src/assets/fonts/BarlowCondensed-ExtraBoldItalic.woff2` | 英文与数字粗斜体 | [Barlow](https://github.com/jpt/barlow)，SIL Open Font License 1.1 |
| `client/src/assets/patterns/halftone.svg` | 半调网点，作为 CSS 遮罩使用 | 由脚本生成 |
| `client/src/assets/brand/asoul-logo.svg` | A-SOUL 标志的矢量描摹，作为 CSS 遮罩使用 | 版权归权利人所有，见同目录 `COPYRIGHT.md` |

新增界面文字后运行 `python scripts/build_ui_assets.py --noto <NotoSansSC[wght].ttf>`（需安装 fonttools 与 brotli）重新裁剪字体。未包含在子集内的字符会回退到系统字体。

## 收藏集与表情规则

收藏集共 6 套、70 张卡牌：绽放（24）、绚烂心迹（9）、此间为爱（9）、沉沦醉与爱（9）、时空旅人（9）、双声巡梦（10）。

| 收藏集 | 大隐藏 | 小隐藏 |
|---|---|---|
| 绽放 | 时序系列三张 | 舞台系列三张 |
| 绚烂心迹 | 绘心物语 | 天使奇遇 |
| 此间为爱 | 珍馐派对 | 月纱花信 |
| 沉沦醉与爱 | 蝶影共醉 | 绮梦妖狐 |
| 时空旅人 | 时空行者 | 引爆枝江大楼 |
| 双声巡梦 | 巡梦漫游 | 魔女契约 |

除绽放外，每个收藏集的抽卡页使用同期主题的配色和 Q 版图标（`client/src/cards.ts` 的 `POOL_THEME`）：绚烂心迹对应 2025 嘉然的画册，此间为爱对应 2026 嘉然的画册，沉沦醉与爱对应 2025 乃琳的酒馆，时空旅人对应 2025 贝拉的冒险，双声巡梦对应心宜和思诺的交响乐谱。

- **抽卡概率**：大隐藏 0.5%、小隐藏 4.5%、普通 95%，同档位内等概率抽取，全卡池共用 400 抽大隐藏保底。
- **表情宝箱**：共 375 个表情（每位角色含 4 个初始表情）。普通 / 稀有表情重复获得分别转化为 1 / 3 碎片，兑换价格分别为 10 / 30 碎片。
