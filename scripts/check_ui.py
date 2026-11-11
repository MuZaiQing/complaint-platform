"""大屏回归校验：双主题截图 + 控制台报错 + 横向溢出。

用法（服务需已在 8000 端口运行）：
    python scripts/check_ui.py
输出：docs/screenshots/*.png，控制台打印 JSON 报告，有报错时退出码 1。
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000/"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("综合数据驾驶舱", "dashboard"),
    ("金融投诉统计分析", "finance"),
    ("金融文本与 AI 分析", "ai"),
    ("电信投诉分析", "telecom"),
    ("智能预警中心", "alert"),
    ("集群控制台", "cluster"),
    ("数据查询中心", "query"),
]

# 白名单：目前为空。曾有的 tooltip formatter 空值崩溃已在重写 formatter 时加固。
KNOWN = ()


def main() -> int:
    errors, report = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)

        page.goto(BASE, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        for theme in ("dark", "light"):
            if theme == "light":
                page.click(".theme-toggle")
                page.wait_for_timeout(1800)
            for name, slug in PAGES:
                try:
                    page.click(f".nav-item:has-text('{name}')", timeout=8000)
                except Exception as exc:  # 导航项不存在时记录而非中断
                    errors.append(f"nav: {name} -> {exc.__class__.__name__}")
                    continue
                page.wait_for_timeout(2200)
                suffix = "" if theme == "dark" else "_light"
                page.screenshot(path=str(OUT / f"{slug}{suffix}.png"))
                overflow = page.evaluate(
                    """() => {
                      const c = document.querySelector('.content');
                      if (!c) return 0;
                      const cr = c.getBoundingClientRect();
                      let max = 0;
                      c.querySelectorAll('.card, .metric-card, .kpi-card, .grid-12, .grid-2, .grid-3, .grid-4')
                        .forEach(el => {
                          const r = el.getBoundingClientRect();
                          if (r.width > 0) max = Math.max(max, r.right - cr.right);
                        });
                      return Math.round(max);
                    }"""
                )
                report.append({"theme": theme, "page": name, "overflow": overflow})

        browser.close()

    known = [e for e in errors if any(k in e for k in KNOWN)]
    fatal = [e for e in errors if not any(k in e for k in KNOWN)]
    overflows = [r for r in report if r["overflow"] > 0]

    print(json.dumps(
        {
            "fatal_errors": fatal[:20],
            "known_errors": known[:5],
            "overflow_pages": overflows,
            "shots": len(report),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 1 if fatal or overflows else 0


if __name__ == "__main__":
    sys.exit(main())
