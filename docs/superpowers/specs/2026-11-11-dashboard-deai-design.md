# 大屏「去 AI 味」设计稿：双主题 · 蓝色玻璃工业风

日期：2026-11-11
范围：`backend/index.html`（单文件大屏）、`THEMES` 图表色板
目标：去除模板感与塑料感，建立「深灰蓝玻璃 / 白灰工业」两套克制但有质感的视觉语言。霓虹发光保留，但必须是分层、受光、带纹理的真实材质，而不是单层大 blur 泛光。同时补足图表交互与动效节奏。

---

## 1. 设计语言

两套主题共用同一套结构规则，只在材质与明度上区分。**不使用黑底、不使用大圆角渐变堆叠、不用单层大 blur 泛光。**

| 令牌 | 深色 · 深灰蓝玻璃 | 浅色 · 白灰工业 |
|---|---|---|
| `--bg-0` 页面底 | `#1B2129` | `#F6F8FA` |
| `--bg-1` 面板 | `#222A33` | `#FFFFFF` |
| `--bg-2` 卡片面 | `rgba(41,54,68,.72)` | `rgba(255,255,255,.78)` |
| `--bg-3` 悬停层 | `#2F3A47` | `#F0F3F6` |
| `--border` 边框 | `rgba(126,160,196,.18)` | `#D0D7DE` |
| `--fg-0` 主文字 | `#C9D6E2` | `#1F2328` |
| `--fg-1` 次文字 | `#93A4B6` | `#59636E` |
| `--fg-2` 弱文字 | `#6B7C8F` | `#8C959F` |
| 强调色 | `#539BF5` | `#0969DA` |
| 绿 / 橙 / 红 / 紫 | `#57AB5A` / `#C69026` / `#E5534B` / `#986EE2` | `#1A7F37` / `#9A6700` / `#CF222E` / `#8250DF` |

深色卡片 = 半透明蓝玻璃 + `backdrop-filter: blur(14px) saturate(1.1)` + 分层受光高光（见第 2 节）。
浅色卡片 = 实色白 + 1px 边框 + 极浅投影，**不用玻璃模糊**。

## 2. 霓虹质感化（保留发光，去掉塑料感）

塑料感的成因是「单一高饱和色 + 均匀大 blur + 全卡通亮高光」。真实感的做法是把光拆成多层，并让材质本身有瑕疵。参考 GitHub 上的真实实现：Radix Colors 的 alpha 色阶叠加、Vercel Geist 的渐变描边、shadcn / Aceternity UI 的 BorderBeam 局部流光、Primer 的多层阴影。

### 2.1 卡片光影分层（替代单层 `box-shadow: 0 0 Npx`）

```css
  /* 深色：4 层叠加，模拟主光 + 环境光 + 接触影 + 顶部受光边 */
  --shadow-glow:
    inset 0 1px 0 rgba(255,255,255,.07),      /* 顶部受光边，只 1px */
    inset 0 -1px 0 rgba(0,0,0,.28),           /* 底部自阴影 */
    0 1px 2px rgba(0,0,0,.28),                /* 接触影，小半径 */
    0 10px 28px -12px rgba(0,0,0,.55);        /* 环境影，大半径低透明 */
  /* 发光时追加一层小半径色光，而不是大 blur */
  --shadow-neon: 0 0 0 1px rgba(83,155,245,.22), 0 0 18px -4px rgba(83,155,245,.35);
```

关键约束：色光半径 ≤ 18px、负 spread、透明度 ≤ 35%。大 blur + 高透明是塑料感的直接来源。

### 2.2 渐变描边（Vercel Geist 做法）

边框不用纯色，改用 `mask-composite` 做上亮下暗，模拟受光方向：

```css
  .card::after {
    content: ''; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
    padding: 1px;
    background: linear-gradient(180deg, rgba(126,160,196,.34), rgba(126,160,196,.10) 40%, rgba(0,0,0,.20));
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    -webkit-mask-composite: xor; mask-composite: exclude;
  }
```

### 2.3 局部流光（BorderBeam，不是全卡呼吸）

只在卡片顶边跑一段 120px 的渐变光，`8s` 一轮，透明度峰值 55%：

```css
  .card::before {
    content: ''; position: absolute; top: 0; left: 0; height: 1px; width: 120px;
    background: linear-gradient(90deg, transparent, var(--cyan), transparent);
    opacity: .55; animation: beam-move 8s linear infinite;
  }
  @keyframes beam-move {
    0% { transform: translateX(-120px); }
    100% { transform: translateX(calc(100% + 120px)); }
  }
```

### 2.4 材质瑕疵（去均匀感）

- 全局噪点 3%（深）/ 2%（浅），叠加在卡片之上，打破纯色块的塑料感
- 玻璃面叠加极淡的 45° 斜向反光，透明度 2.5%，只在上半部分：

```css
  .card {
    background-image: linear-gradient(135deg, rgba(255,255,255,.030) 0%, transparent 42%);
  }
```

### 2.5 图表发光降级为「贴边光」

- 折线：`lineStyle.width: 1.8` + `shadowBlur: 6, shadowOffsetY: 2`（沿线的柔光，不是各向同性雾）
- 柱状：保留 `shadowBlur: 8` 但只给 top1 色，normal 色不加发光
- 渐变统一 3 段（0 / 60% / 100%），中间段做缓冲，避免"塑料渐变"

### 2.6 保留不动的既有动效

扫描线、光柱呼吸、雷达扫描这些**结构性的**动效保留，只把透明度峰值下调 20%，避免抢视觉。

## 3. 版式去模板感

- 驾驶舱改 12 列栅格：KPI 区「1 张大卡（4 列）+ 5 张小卡（各 1.6 列）」混排，不再 6 等分
- 主趋势图跨 8 列，右侧 4 列放结论摘要卡（不是图表）；地图卡跨满 12 列
- 子页统一规则：每页至少一个跨列主卡，禁止「标题条 + N 等分卡片」的连续出现
- 卡片标题改为「序号 + 标题 + 右侧一句话结论」，删除统一左侧竖色条
- 全站圆角统一收敛到 8px（小卡）/ 10px（大卡），不再 14px

## 4. 材质

- 全局噪点层：`feTurbulence` 生成 SVG data-uri，深色 3% / 浅色 2%，`pointer-events:none` 固定层
- 卡片内高光：仅深色，`inset 0 1px 0 rgba(255,255,255,.06)`
- 数据区表格：斑马纹改为 1px 底线 + 悬停整行底色，去掉交替色块

## 5. 动效

- 入场：按 DOM 顺序 stagger 60ms，缓动 `cubic-bezier(.16,1,.3,1)`，位移 10px
- 数字：`easeOutExpo`，1.2s
- hover：卡片边框提亮 + 背景 `--bg-3`，不做位移；图表卡不做 transform
- 鼠标柔光：`radial-gradient` 60px，透明度 6%，仅深色

## 6. 图表交互与形态差异化

| 页面 | 主图形态 | 交互 |
|---|---|---|
| 驾驶舱 | 双线趋势 + 面积 | brush 框选缩放、点击月份下钻 |
| 金融 | 帕累托柱线 | 点击柱子联动下方企业榜 |
| 电信 | 堆叠面积（按议题） | 图例点击隔离序列 |
| 文本 AI | 混淆矩阵热力 | 悬停显示样本数/占比 |
| 预警 | 镜像柱（红上黄下） | 点击等级筛选明细表 |

统一规则：
- 折线 `width: 1.8`，发光用 `shadowBlur: 6 + shadowOffsetY: 2` 的贴边光
- 柱状圆角 2px；浅色用 3 段同级渐变，深色用 8% 同色渐变，只有 top1 加发光
- tooltip 统一：标题加粗 + 数值等宽字体 + 一行结论
- `emphasis.focus = 'series'` 全站开启

## 7. 性能兜底

- `body[data-fx="off"]` 关闭：噪点、鼠标柔光、入场动画、BorderBeam 流光
- 软件渲染（SwiftShader / llvmpipe）自动置 `off`
- 3D 场景保持既有离屏停画策略

## 8. 验收标准

1. 1920×1080 下两套主题均无横向溢出，控制台 0 报错
2. 正文对比度 ≥ 4.5:1，大号数字 ≥ 3:1
3. 全站发光均为「小半径 + 低透明 + 分层」：无 `shadowBlur > 20`、无色光透明度 > 40%（grep 校验）
4. 每页主图均有可点击下钻或筛选联动
5. 空闲帧率 ≥ 50fps，首屏长任务 < 200ms
