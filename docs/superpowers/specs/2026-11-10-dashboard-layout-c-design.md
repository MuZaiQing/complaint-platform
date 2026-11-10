# 综合数据驾驶舱重排 · 方案 C

## 背景
当前驾驶舱页（`backend/index.html`，`activePage === 'dashboard'`）共 9 块：
① 指标卡堆 → ② 3D 地球 → ③ 双业务趋势+④ TOP10 词云（2fr:1fr）→ ⑤ 企业 TOP5+⑥ 州热力地图 → ⑦ 电信 TOP5+⑧ 金融产品 TOP5 → ⑨ 五层架构粒子管道

用户反馈：③ 双业务趋势占太高（`grid-template-columns: 2fr 1fr` + 图表默认最小高度）、⑨ 五层架构管道占整行但信息密度低、整体想重排。

## 方案
把第二块「整宽 3D 地球」从视觉第一行下移到第三行，上方腾出一整行给「双业务趋势 + TOP10 词云 + 管道极简图标」。

最终视觉顺序：
1. 指标卡堆（不变）
2. **趋势三列**（新增）：③ 双业务趋势 1fr | ④ TOP10 词云 1fr | ⑨ 极简管道图标 1fr（~180px 高）
3. 3D 地球（下移，完整高度 ~280px，仍是视觉中心）
4. ⑤ 企业 TOP5 + ⑥ 州热力地图（不变）
5. ⑦ 电信 TOP5 + ⑧ 金融产品 TOP5（不变）

## 改动清单

### 1. HTML 结构（`backend/index.html`，PAGE 1 部分）
- 把原来独立一行的 `<!-- 3D 地球总览 -->` 块从 L1673–L1716 **移动到**当前 `<!-- 双业务月度趋势 + TOP10 词云 -->` 块之后
- 原来「趋势+词云」的 `grid-2` 行改为新的 3 行结构：`<div class="grid-3 mb-16">` 包着三块卡
- 在第三列新增 `.card`，标题「平台数据链路」，内部是 5 行极简管道图标（emoji + 关键词 + 悬停展开）
- 原「五层架构管道」卡（L1768–L1782）**删除**；粒子动画代码 `pipe-stage` 保留但默认隐藏，由新卡的「展开」按钮控制

### 2. CSS（`backend/index.html` `<style>` 块）
- 新 `.pipe-mini-card`：1fr 宽，5 行 flex 图标列表，字号 10–11px，单行省略
- `.pipe-mini-row`：图标 + 关键词 + 描述三列 flex 行
- `.refDashTrend` / `.refDashWord` ECharts 图表容器加 `.chart-compact` 变体：min-height 从 ~180px 降到 ~130px
- `.globe-wrap` 及 3D 球相关高度保持原样（方案 C 不压缩地球）

### 3. ECharts 配置
- `refDashTrend`：grid `bottom` 从 28 降到 18，`containLabel: true` 改 false 手动调，X 轴 label `fontSize: 10`，图例 `right: 0 top: 0` 移到右上角
- `refDashWord`：label `fontSize: 10`

### 4. ⑨ 管道极简实现
- 静态 5 行：📄 原始数据 · CCDB/FCC 工单 | 🗂 HDFS · 分布式存储 | ⚙️ MapReduce · 分词/聚合 | 🗄 MySQL · 10 张预聚合表 | 🖥 大屏 · 单文件 HTML
- 底部「完整架构 →」按钮，点击展开原 `pipe-stage` 粒子动画（`display:none` → `display:block`，位置浮层或下拉折叠）

### 5. 不动的部分
- 3D 地球 HTML / JS / CSS（保持原样，只动位置）
- 所有 ECharts 数据源（`refDashTrend` / `refDashWord` / `refDashCompany` / `refDashStateMap` / `refDashState` / `refDashIssue` / `refDashProduct`）都不换数据，只调容器尺寸
- 指标卡堆 / 顶部栏 / 侧栏 / 其他页面
- `.globe-wrap` 内部结构、3D 球、播放控制、州下钻弹层全部不动

## 验收标准
1. 首屏视觉顺序：指标卡堆 → 三列行（趋势/词云/管道极简）→ 3D 地球 → 企业+热力 → 电信+金融
2. ⑨ 管道卡：默认显示极简 5 行图标，有「完整架构 →」按钮，按钮打开后能看到原粒子动画
3. 3D 地球高度保持 ~280px，three.js 动画正常、时间轴、播放、下钻全部工作
4. ③ 双业务趋势图表 130px 高度下折线清晰、X 轴标签不重叠
5. 控制台 0 报错（回归测试）
6. 现有部署（uvicorn 跑 `backend/index.html` 作为 `FileResponse`）免重启，刷新即生效
