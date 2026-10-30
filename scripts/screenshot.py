#!/usr/bin/env python3
"""对 radar-dashboard 公众号选题页截图（供 README 使用，双主题各一张）
用法: venv/bin/python scripts/screenshot.py docs/screenshot-topics-dark.png dark
"""
import asyncio, glob, os, sys
from playwright.async_api import async_playwright

OUT = sys.argv[1] if len(sys.argv) > 1 else "docs/screenshot-topics-dark.png"
theme = sys.argv[2] if len(sys.argv) > 2 else "dark"

URL = f"http://127.0.0.1:5080/?theme={theme}#/topics"
VIEWPORT_W, VIEWPORT_H = 1280, 900

# Linux 下 playwright 自带 chromium 缓存（macOS 路径保留兼容）
home = os.path.expanduser("~")
candidates = sorted(glob.glob(f"{home}/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")) + \
    sorted(glob.glob(
        f"{home}/Library/Caches/ms-playwright/chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"))
headless_candidates = sorted(glob.glob(
    f"{home}/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux*/chrome-headless-shell"))
executable = candidates[-1] if candidates else (headless_candidates[-1] if headless_candidates else None)


async def main():
    async with async_playwright() as p:
        kw = {"executable_path": executable} if executable else {}
        if executable:
            kw["args"] = ["--no-sandbox"]
        browser = await p.chromium.launch(**kw)
        page = await browser.new_page(viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
                                      device_scale_factor=2)
        await page.goto(URL, wait_until="networkidle")
        await page.wait_for_timeout(1500)
        # 等选题卡片渲染完成
        await page.wait_for_selector(".topic-card", timeout=10000)
        await page.wait_for_timeout(800)
        await page.screenshot(path=OUT, full_page=False)
        await browser.close()
        print(f"OK: {OUT}")


asyncio.run(main())
