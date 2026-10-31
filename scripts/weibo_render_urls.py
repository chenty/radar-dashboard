#!/usr/bin/env python3
"""微博渲染步骤 — 由 Hermes agent 会话（browser_exec 工具）执行，不是 shell 脚本。

用途：在 agent 的浏览器里逐个打开 m.weibo.cn 搜索页，把渲染后的 HTML 拼接
缓存到 ~/.hermes/cache/weibo_reach_last_page.html，供 daily_signals.py 的
fetch_weibo_reach() 读取（无头 cron 无法开浏览器，故采用渲染-缓存两段式）。

在 browser_exec 里运行本文件内容的方式（由 agent cron prompt 指示）：
  每次 cron 预采集时，agent 先用 browser_exec 逐词打开下方 URL 列表，
  把 document.documentElement.outerHTML 拼接写入缓存文件。
"""
import urllib.parse

try:
    from .query_config import load_source_queries
except ImportError:
    from query_config import load_source_queries


def search_urls():
    urls = []
    for q in load_source_queries("weibo-reach"):
        cid = urllib.parse.quote(f"100103type=1&q={q}", safe="")
        urls.append(f"https://m.weibo.cn/search?containerid={cid}")
    return urls

if __name__ == "__main__":
    print("\n".join(search_urls()))
