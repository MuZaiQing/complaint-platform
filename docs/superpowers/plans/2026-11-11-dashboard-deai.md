# 大屏去 AI 味（双主题 · 蓝色玻璃工业风）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 去掉大屏的模板感与霓虹感，落地「深灰蓝玻璃 / 白灰工业」两套克制主题，并补足材质、动效节奏与图表交互。

**Architecture:** 全部改动集中在单文件 `backend/index.html`：CSS 令牌层（`:root` 与 `html[data-theme="light"]`）决定底色/边框/材质，`THEMES` JS 对象决定 ECharts 取色，`body[data-fx]` 控制动效开关。图表交互按页各自挂 `c.on(...)`，不新增依赖。

**Tech Stack:** Vue 3（CDN）、ECharts 5、three.js、CSS 自定义属性、Playwright（校验脚本）。

**Spec:** `docs/superpowers/specs/2026-11-11-dashboard-deai-design.md`

---

## 文件结构

| 文件 | 责任 |
|---|---|
| `backend/index.html` | 唯一前端文件。CSS 令牌 → 材质 → 版式 → 动效 → 图表交互，按任务顺序改 |
| `scripts/check_ui.py` | 新建。Playwright 校验：双主题截图、控制台报错、横向溢出、对比度抽样。 |

改动顺序原则：先删（霓虹）→ 再换（令牌）→ 再排版 → 最后加交互。每步都能单独刷新验证。

---

### Task 0: 建立可重复的校验脚手架

**Files:**
- Create: `scripts/check_ui.py`

- [ ] **Step 1: 写校验脚本**

```python
"""大屏回归校验：双主题截图 + 控制台报错 + 横向溢出。用法：python scripts/check_ui.py"""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000/"
OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
PAGES = ["综合数据驾驶舱", "金融投诉统计分析", "电信投诉分析",
         "金融文本与AI分析", "智能预警中心", "数据查询中心"]


def main():
    errors, report = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(BASE, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        for theme in ("dark", "light"):
            if theme == "light":
                page.click(".theme-toggle")
                page.wait_for_timeout(1800)
            for name in PAGES:
                page.click(f".nav-item:has-text('{name}')")
                page.wait_for_timeout(2200)
                slug = name if theme == "dark" else name + "_light"
                page.screenshot(path=str(OUT / f"{slug}.png"))
                if name == "综合数据驾驶舱":
                    over = page.evaluate("""() => {
                      const c = document.querySelector('.content');
                      return c ? c.scrollWidth - c.clientWidth : 0;
                    }""")
                    report.append({"theme": theme, "overflow": over})

        browser.close()

    print(json.dumps({"errors": errors[:20], "report": report}, ensure_ascii=False, indent=2))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 起服务并跑一次基线**

Run（PowerShell）:
```powershell
& 'D:\ruan_jain_an_zhuang\python-3.13.7\python.exe' -m uvicorn main:app --host 127.0.0.1 --port 8000
```
（在 `d:\fqh\backend` 下、后台运行）
Then:
```powershell
& 'D:\ruan_jain_an_zhuang\python-3.13.7\python.exe' scripts/check_ui.py
```
Expected: 输出 `"errors": []`，`overflow: 0`，`docs/screenshots/` 下生成 12 张图。

- [ ] **Step 3: 提交**

```powershell
git add scripts/check_ui.py
git commit -m "test: 新增大屏双主题回归校验脚本"
```

---

### Task 1: 换掉两套主题令牌，删除高饱和色

**Files:**
- Modify: `backend/index.html`（`:root` 段与 `html[data-theme="light"]` 段）

- [ ] **Step 1: 替换深色令牌**

把 `:root { ... }` 中下列值改掉（其余保留）：

```css
    --bg-0: #1B2129;
    --bg-1: #222A33;
    --bg-2: rgba(41,54,68,.72);
    --bg-3: #2F3A47;
    --border: rgba(126,160,196,.18);
    --fg-0: #C9D6E2;
    --fg-1: #93A4B6;
    --fg-2: #6B7C8F;
    --fg-3: #56646F;
    --cyan: #539BF5;
    --cyan-dim: rgba(83,155,245,.12);
    --blue: #6CB6FF;
    --blue-dim: rgba(108,182,255,.12);
    --green: #57AB5A;
    --green-dim: rgba(87,171,90,.12);
    --red: #E5534B;
    --red-dim: rgba(229,83,75,.12);
    --orange: #C69026;
    --orange-dim: rgba(198,144,38,.12);
    --purple: #986EE2;
    --purple-dim: rgba(152,110,226,.12);
    --on-accent: #1B2129;
    --card-radius: 10px;
    --shadow-glow: 0 1px 2px rgba(0,0,0,.25), 0 8px 24px rgba(0,0,0,.18);
    --shadow-hover: 0 2px 4px rgba(0,0,0,.28), 0 12px 32px rgba(0,0,0,.24);
    --fin-top1: #539BF5; --fin-top23: #6CB6FF; --fin-normal: #3D6A9E;
    --fcc-top1: #C69026; --fcc-top23: #D4A241; --fcc-normal: #6E5420;
    --other-gray: #5B6670;
```

- [ ] **Step 2: 替换浅色令牌**

把 `html[data-theme="light"] { ... }` 整块改为：

```css
  html[data-theme="light"] {
    --bg-0: #F6F8FA;
    --bg-1: #FFFFFF;
    --bg-2: rgba(255,255,255,.78);
    --bg-3: #F0F3F6;
    --border: #D0D7DE;
    --fg-0: #1F2328;
    --fg-1: #59636E;
    --fg-2: #8C959F;
    --fg-3: #AFB8C1;
    --cyan: #0969DA;
    --cyan-dim: rgba(9,105,218,.08);
    --blue: #218BFF;
    --blue-dim: rgba(33,139,255,.10);
    --green: #1A7F37;
    --green-dim: rgba(26,127,55,.08);
    --red: #CF222E;
    --red-dim: rgba(207,34,46,.08);
    --orange: #9A6700;
    --orange-dim: rgba(154,103,0,.08);
    --purple: #8250DF;
    --purple-dim: rgba(130,80,223,.08);
    --on-accent: #FFFFFF;
    --shadow-glow: 0 1px 2px rgba(31,35,40,.06);
    --shadow-hover: 0 4px 12px rgba(31,35,40,.10);
    --fin-top1: #0969DA; --fin-top23: #218BFF; --fin-normal: #9DC3F0;
    --fcc-top1: #9A6700; --fcc-top23: #BF8700; --fcc-normal: #E5C77A;
    --other-gray: #AFB8C1;
  }
```

- [ ] **Step 3: 同步 `THEMES` 两个色板**

`THEMES.dark` 改为：

```js
  dark: {
    fin: { top1:'#539BF5', top23:'#6CB6FF', normal:'#3D6A9E', other:'#5B6670' },
    fcc: { top1:'#C69026', top23:'#D4A241', normal:'#6E5420', other:'#5B6670' },
    line1:'#539BF5', line2:'#C69026',
    yes:'#57AB5A', no:'#E5534B', purple:'#986EE2',
    axis:'#39424D', axisLabel:'#768390', split:'rgba(173,186,199,.10)', legend:'#ADBAC7',
    tooltipBg:'#2D333B', tooltipBorder:'#444C56', tooltipText:'#C9D6E2',
    pieBorder:'#222A33', onAccent:'#1B2129',
    wordPalette:['#539BF5','#6CB6FF','#57AB5A','#986EE2','#C69026','#4FB3A9','#7FC8F8','#B083F0'],
    fccWordPalette:['#C69026','#D4A241','#B07D1E','#8C641A','#A87C2B','#7A5616'],
    wordCat:['#539BF5','#986EE2','#57AB5A','#C69026','#E5534B','#4FB3A9'],
    mapRange:['#222A33','#2F4A66','#539BF5','#986EE2'],
    mapRangeFcc:['#222A33','#4A3A1E','#C69026','#D4A241'],
    mapArea:'#2A323C', mapBorder:'#39424D',
  },
```

`THEMES.light` 改为：

```js
  light: {
    fin: { top1:'#0969DA', top23:'#218BFF', normal:'#9DC3F0', other:'#AFB8C1' },
    fcc: { top1:'#9A6700', top23:'#BF8700', normal:'#E5C77A', other:'#AFB8C1' },
    line1:'#0969DA', line2:'#9A6700',
    yes:'#1A7F37', no:'#CF222E', purple:'#8250DF',
    axis:'#D8DEE4', axisLabel:'#8C959F', split:'rgba(31,35,40,.07)', legend:'#59636E',
    tooltipBg:'#FFFFFF', tooltipBorder:'#D0D7DE', tooltipText:'#1F2328',
    pieBorder:'#FFFFFF', onAccent:'#FFFFFF',
    wordPalette:['#0969DA','#218BFF','#1A7F37','#8250DF','#9A6700','#0A7B83','#54AEFF','#116329'],
    fccWordPalette:['#9A6700','#7D4E00','#BF8700','#654100','#A87C2B','#8C641A'],
    wordCat:['#0969DA','#8250DF','#1A7F37','#9A6700','#CF222E','#0A7B83'],
    mapRange:['#F6F8FA','#BFDBFE','#54AEFF','#0969DA'],
    mapRangeFcc:['#F6F8FA','#F2E2B8','#BF8700','#9A6700'],
    mapArea:'#F0F3F6', mapBorder:'#D8DEE4',
  },
```

- [ ] **Step 4: 校验没有旧色残留**

Run:
```powershell
Select-String -Path backend\index.html -Pattern '#00D8FF|#FF9533|#A78BFA|#0B0E13|#2563EB' -AllMatches
```
Expected: 只剩注释或非颜色用途的匹配；若仍有令牌引用，逐个替换。

- [ ] **Step 5: 跑校验 + 提交**

```powershell
& 'D:\ruan_jain_an_zhuang\python-3.13.7\python.exe' scripts/check_ui.py
git add backend/index.html
git commit -m "feat(theme): 双主题换为深灰蓝玻璃与白灰工业配色"
```

---

### Task 2: 霓虹质感化（保留发光，去塑料感）

**Files:**
- Modify: `backend/index.html`（`:root` 阴影令牌、`.card` 伪元素、图表 series 发光参数）

- [ ] **Step 1: 阴影改为 4 层叠加**

把真机深色 `:root` 里的 `--shadow-glow` / `--shadow-hover` 替换为：

```css
    --shadow-glow:
      inset 0 1px 0 rgba(255,255,255,.07),
      inset 0 -1px 0 rgba(0,0,0,.28),
      0 1px 2px rgba(0,0,0,.28),
      0 10px 28px -12px rgba(0,0,0,.55);
    --shadow-hover:
      inset 0 1px 0 rgba(255,255,255,.10),
      inset 0 -1px 0 rgba(0,0,0,.30),
      0 2px 4px rgba(0,0,0,.30),
      0 16px 36px -14px rgba(0,0,0,.60);
    --shadow-neon: 0 0 0 1px rgba(83,155,245,.22), 0 0 18px -4px rgba(83,155,245,.35);
```

浅色主题保持 `--shadow-glow` 的轻投影，不叠加色光。

- [ ] **Step 2: 渐变描边替代纯色边**

覆盖 `.card` 的 `::after`（若无则新增）：

```css
  .card::after {
    content: ''; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
    padding: 1px;
    background: linear-gradient(180deg, rgba(126,160,196,.34), rgba(126,160,196,.10) 40%, rgba(0,0,0,.20));
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    -webkit-mask-composite: xor; mask-composite: exclude;
  }
  html[data-theme="light"] .card::after {
    background: linear-gradient(180deg, rgba(31,35,40,.10), rgba(31,35,40,.04) 45%, rgba(31,35,40,.08));
  }
```

- [ ] **Step 3: 全卡旋转光带 → 顶边局部流光**

把现有 `.card::before` 的旋转光带（`card-ang-spin`）替换为 BorderBeam：

```css
  .card::before {
    content: ''; position: absolute; top: 0; left: 0; height: 1px; width: 120px;
    background: linear-gradient(90deg, transparent, var(--cyan), transparent);
    opacity: .55; display: block; animation: beam-move 8s linear infinite;
  }
  @keyframes beam-move {
    0% { transform: translateX(-120px); }
    100% { transform: translateX(calc(100% + 120px)); }
  }
```

- [ ] **Step 4: 图表发光降为贴边光**

折线：

```js
// 原来
lineStyle:{ width:2.4, shadowBlur:12, shadowColor: TC().line1 + '66' }
// 改为
lineStyle:{ width:1.8, shadowBlur:6, shadowOffsetY:2, shadowColor: TC().line1 + '55' }
```

柱状：只给 top1 色保留 `shadowBlur: 8`，normal 色删掉发光：

```js
itemStyle:{ color: barGradH(TC().fin.top1), borderRadius:[0,2,2,0],
  shadowBlur: 8, shadowOffsetY: 1, shadowColor: TC().fin.top1 + '40' }
```

- [ ] **Step 5: 材质瑕疵层**

```css
  .card {
    background-image: linear-gradient(135deg, rgba(255,255,255,.030) 0%, transparent 42%);
  }
  html[data-theme="light"] .card {
    background-image: linear-gradient(135deg, rgba(9,105,218,.020) 0%, transparent 45%);
  }
```

- [ ] **Step 6: 校验 + 提交**

```powershell
Select-String -Path backend\index.html -Pattern 'shadowBlur: *(2[1-9]|[3-9]\d)'
& 'D:\ruan_jain_an_zhuang\python-3.13.7\python.exe' scripts/check_ui.py
git add backend/index.html
git commit -m "style(theme): 霓虹改为分层贴边光、渐变描边与顶边流光"
```
Expected: 无 `shadowBlur >= 21` 命中；校验脚本 0 报错。

---

### Task 3: 材质层（噪点 + 表格细线）

**Files:**
- Modify: `backend/index.html`（CSS 全局层）

- [ ] **Step 1: 加全局噪点层**

```css
  body::after {
    content: ''; position: fixed; inset: 0; z-index: 1; pointer-events: none;
    opacity: .030;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='3'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)'/%3E%3C/svg%3E");
  }
  html[data-theme="light"] body::after { opacity: .020; }
```

- [ ] **Step 2: 表格去斑马纹改底线**

```css
  .el-table tr > td { border-bottom-color: var(--border) !important; }
  .el-table__row:nth-child(even) > td { background: transparent !important; }
  .el-table__body tr:hover > td { background: var(--bg-3) !important; }
```

- [ ] **Step 3: 校验 + 提交**

```powershell
& 'D:\ruan_jain_an_zhuang\python-3.13.7\python.exe' scripts/check_ui.py
git add backend/index.html
git commit -m "style(material): 全局噪点层与表格细线化"
```

---

### Task 4: 版式去模板感

**Files:**
- Modify: `backend/index.html`（`.grid-*` 定义、驾驶舱 KPI 模板、`.card-title`）

- [ ] **Step 1: 加 12 列栅格工具类**

```css
  .grid-12 { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 14px; }
  .col-2 { grid-column: span 2; } .col-3 { grid-column: span 3; }
  .col-4 { grid-column: span 4; } .col-6 { grid-column: span 6; }
  .col-8 { grid-column: span 8; } .col-12 { grid-column: span 12; }
  @media (max-width: 1280px) {
    .col-2, .col-3, .col-4 { grid-column: span 6; }
    .col-6, .col-8 { grid-column: span 12; }
  }
```

- [ ] **Step 2: 驾驶舱 KPI 改混排**

把 `<!-- 6 指标卡：扇形卡堆 -->` 整块替换为：

```html
        <div class="grid-12 mb-16" v-if="overview">
          <div class="metric-card col-4 accent-cyan">
            <div class="label">{{ dashboardCards[0].label }}</div>
            <div class="value"><span v-countup="dashboardCards[0].value"></span><span class="suffix">{{ dashboardCards[0].suffix }}</span></div>
            <div class="delta" :class="dashboardCards[0].deltaClass">{{ dashboardCards[0].delta }}</div>
          </div>
          <div class="metric-card col-2" v-for="c in dashboardCards.slice(1)" :key="c.label"
               :class="'accent-' + (c.accent || 'cyan')">
            <div class="label">{{ c.label }}</div>
            <div class="value"><span v-countup="c.value"></span><span class="suffix">{{ c.suffix }}</span></div>
            <div class="delta" :class="c.deltaClass">{{ c.delta }}</div>
          </div>
        </div>
```

- [ ] **Step 3: 卡片标题去竖条改序号**

```css
  .card-title::before {
    content: attr(data-idx); width: auto; height: auto;
    background: none; color: var(--fg-2);
    font: 500 11px/1 'JetBrains Mono', monospace; letter-spacing: .5px;
  }
```
给驾驶舱各 `card-title` 依次加 `data-idx="01"`、`"02"`……，并在标题末尾补一句结论：
```html
<div class="card-title" data-idx="03">双业务月度投诉趋势
  <span class="hint-tag">电信 2025-09 起反超金融</span></div>
```

- [ ] **Step 4: 校验 + 提交**

```powershell
& 'D:\ruan_jain_an_zhuang\python-3.13.7\python.exe' scripts/check_ui.py
git add backend/index.html
git commit -m "style(layout): 驾驶舱改 12 列主编式栅格与序号标题"
```
Expected: 截图里 KPI 为「1 大 + 5 小」，无横向溢出。

---

### Task 5: 动效节奏 + 特效开关

**Files:**
- Modify: `backend/index.html`（CSS 动画、`v-countup` 指令、`main` 挂载处）

- [ ] **Step 1: 错峰入场**

```css
  .page-enter > * { animation: fadeUp .42s cubic-bezier(.16,1,.3,1) both; }
  .page-enter > *:nth-child(1) { animation-delay: 0ms; }
  .page-enter > *:nth-child(2) { animation-delay: 60ms; }
  .page-enter > *:nth-child(3) { animation-delay: 120ms; }
  .page-enter > *:nth-child(4) { animation-delay: 180ms; }
  .page-enter > *:nth-child(5) { animation-delay: 240ms; }
```
删除原 `.page-enter` 整体淡入动画，避免叠加。

- [ ] **Step 2: 数字滚动改 easeOutExpo**

找到 `v-countup` 指令实现，把线性插值改为：

```js
    const easeOutExpo = (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t));
    const t0 = performance.now();
    const tick = (now) => {
      const p = Math.min(1, (now - t0) / 1200);
      el.textContent = fmtNum(start + (end - start) * easeOutExpo(p));
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
```

- [ ] **Step 3: 卡片 hover 提亮 + 鼠标柔光**

```css
  .card, .metric-card { transition: background-color .2s var(--ease-out), border-color .2s var(--ease-out); }
  .card:hover, .metric-card:hover { border-color: color-mix(in srgb, var(--cyan) 35%, var(--border)); }
  .card:has(.chart):hover { border-color: var(--border); }

  /* 深色：跟随鼠标的 60px 柔光，透明度 6% */
  html:not([data-theme="light"]) .card::before {
    content: ''; position: absolute; inset: 0; pointer-events: none; display: block;
    background: radial-gradient(60px circle at var(--mx, 50%) var(--my, 50%),
      rgba(83,155,245,.06), transparent 70%);
    opacity: 0; transition: opacity .2s var(--ease-out);
  }
  html:not([data-theme="light"]) .card:hover::before { opacity: 1; }
  body[data-fx="off"] .card::before { display: none; }
```
```js
    // 全局委托：记录鼠标在卡片内的相对坐标
    document.addEventListener('pointermove', (e) => {
      const card = e.target.closest && e.target.closest('.card');
      if (!card) return;
      const r = card.getBoundingClientRect();
      card.style.setProperty('--mx', (e.clientX - r.left) + 'px');
      card.style.setProperty('--my', (e.clientY - r.top) + 'px');
    }, { passive: true });
```

- [ ] **Step 4: 加特效开关（含软渲染自动关闭）**

```js
    // 软渲染或低端设备自动关特效
    const gl = document.createElement('canvas').getContext('webgl');
    const dbg = gl && gl.getExtension('WEBGL_debug_renderer_info');
    const renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : '';
    const soft = /SwiftShader|llvmpipe|Software/i.test(renderer || '');
    document.body.dataset.fx = (soft || localStorage.getItem('fx') === 'off') ? 'off' : 'on';
```
```css
  body[data-fx="off"] .page-enter > *,
  body[data-fx="off"] body::after { animation: none !important; }
  body[data-fx="off"]::after { display: none; }
```
顶栏加按钮：
```html
<button class="auto-btn" @click="toggleFx" :title="'关闭/开启动效'">{{ fxOn ? 'FX ON' : 'FX OFF' }}</button>
```
```js
    const fxOn = ref(document.body.dataset.fx !== 'off');
    const toggleFx = () => {
      fxOn.value = !fxOn.value;
      document.body.dataset.fx = fxOn.value ? 'on' : 'off';
      localStorage.setItem('fx', fxOn.value ? 'on' : 'off');
    };
```
`setup()` 的 `return` 里补 `fxOn, toggleFx`。

- [ ] **Step 5: 校验 + 提交**

```powershell
& 'D:\ruan_jain_an_zhuang\python-3.13.7\python.exe' scripts/check_ui.py
git add backend/index.html
git commit -m "feat(motion): 错峰入场、easeOutExpo 数字滚动与特效开关"
```

---

### Task 6: 图表交互与形态差异化

**Files:**
- Modify: `backend/index.html`（各 `render*` 图表函数）

- [ ] **Step 1: 驾驶舱趋势图加 brush 缩放**

在 `renderDashboard()` 的 `refDashTrend` 配置中加：

```js
          toolbox: { show: false },
          dataZoom: [{ type: 'inside', throttle: 60 }, { type: 'slider', height: 12, bottom: 2,
            borderColor: TC().axis, fillerColor: TC().cyanDim, handleSize: 0,
            textStyle: { color: TC().axisLabel, fontSize: 9 } }],
          brush: { xAxisIndex: 0, brushMode: 'lineX', throttleType: 'debounce', throttleDelay: 200 },
```
并在图卡下方加提示：`<div class="chart-note">拖拽底部滑块或框选区间缩放 · 点击月份下钻</div>`

- [ ] **Step 2: 金融帕累托点击下钻联动**

在 `renderPareto` 的 `onClick` 回调里，除现有回调外追加滚动定位：

```js
      c.on('click', p => {
        const x = data[p.dataIndex];
        if (!x || x.isOther) return;
        if (onClick) onClick(x);
        const target = document.querySelector('[data-chart-key="refEnterpriseList"]');
        if (target) target.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
```

- [ ] **Step 3: 电信堆叠面积 + 图例隔离**

`telecom` 页议题趋势改为堆叠面积：

```js
        series: issueSeries.map((s, i) => ({
          name: s.name, type: 'line', stack: 'issue', smooth: true, showSymbol: false,
          lineStyle: { width: 1.2 }, areaStyle: { opacity: .35 },
          emphasis: { focus: 'series' }, data: s.data,
        })),
        legend: { selectedMode: true, textStyle: { color: TC().legend, fontSize: 10 } },
```

- [ ] **Step 4: AI 页改混淆矩阵热力**

把 AI 预测结果的「按类别准确率」柱状图替换为矩阵热力（行=真实，列=预测）：

```js
        series: [{
          type: 'heatmap', data: cells, // cells: [[row, col, value]]
          label: { show: true, color: TC().tooltipText, fontSize: 9,
            formatter: p => p.value[2] > 0 ? p.value[2] : '' },
          itemStyle: { borderColor: TC().pieBorder, borderWidth: 2 },
          emphasis: { itemStyle: { borderWidth: 2 } },
        }],
        visualMap: { min: 0, max: maxCell, show: false,
          inRange: { color: [TC().pieBorder, TC().fin.top23, TC().fin.top1] } },
        xAxis: { type: 'category', data: labels, splitArea: { show: false },
          axisLabel: { color: TC().axisLabel, fontSize: 9, rotate: 30 } },
        yAxis: { type: 'category', data: labels, splitArea: { show: false },
          axisLabel: { color: TC().axisLabel, fontSize: 9 } },
        tooltip: { formatter: p => `${labels[p.value[0]]} → ${labels[p.value[1]]}：<b>${p.value[2]}</b> 条` },
```

- [ ] **Step 5: 预警页改镜像柱**

```js
        series: [
          { name: '红色预警', type: 'bar', stack: 'alert', data: redSeries.map(v => -v),
            itemStyle: { color: TC().no, borderRadius: [0,0,2,2] }, barWidth: 22 },
          { name: '黄色预警', type: 'bar', stack: 'alert', data: yellowSeries,
            itemStyle: { color: TC().fcc.top23, borderRadius: [2,2,0,0] }, barWidth: 22 },
        ],
        xAxis: { type: 'category', data: months, axisLabel: { color: TC().axisLabel,
          formatter: (v, i) => months[i] } },
```
（负值靠 `axisLabel.formatter` 取绝对值，避免出现 −3 这类刻度）

- [ ] **Step 6: 校验 + 提交**

```powershell
& 'D:\ruan_jain_an_zhuang\python-3.13.7\python.exe' scripts/check_ui.py
git add backend/index.html
git commit -m "feat(chart): 趋势 brush 缩放、帕累托下钻、堆叠议题与镜像预警柱"
```

---

### Task 7: 全量回归

- [ ] **Step 1: 跑校验脚本两次（深/浅各一轮）**

```powershell
& 'D:\ruan_jain_an_zhuang\python-3.13.7\python.exe' scripts/check_ui.py
```
Expected: `errors: []`，`overflow: 0`，`docs/screenshots/` 12 张图齐备。

- [ ] **Step 2: 人工看 4 张关键图**

`docs/screenshots/综合数据驾驶舱.png`、`综合数据驾驶舱_light.png`、`智能预警中心.png`、`金融投诉统计分析.png`
检查：发光为分层贴边光而非单层泛光、KPI 混排成立、图表交互控件可见、文字对比度足够。

- [ ] **Step 3: 残留检查**

```powershell
Select-String -Path backend\index.html -Pattern 'shadowBlur: *(2[1-9]|[3-9]\d)|#00D8FF|#FF9533'
```
Expected: 无输出（发光半径均 ≤ 20，旧高饱和色已清除）。

- [ ] **Step 4: 提交收尾**

```powershell
git add backend/index.html scripts/check_ui.py docs/screenshots
git commit -m "chore: 大屏去 AI 味改造回归截图"
```
