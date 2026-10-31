#!/usr/bin/env python3
"""微博移动版(m.weibo.cn)定向搜索采集 — 公开页免登录，供 daily_signals.py 的 fetch_weibo_reach() 调用。

用法: weibo_reach_search.py "关键词1" "关键词2" ...
输出: JSON {ok, items: [{id, title, url, author, timestamp}], error?}
依赖: hermes 浏览器工具在 agent 会话内可用；本脚本独立运行时降级为 requests（会 432 失败），
      所以只能由 fetch_weibo_reach 通过 hermes 浏览器路径调用（见 skill 说明）。
"""
import json
import re
import sys
import time
import urllib.parse

try:
    from .query_config import load_source_queries
except ImportError:
    from query_config import load_source_queries



def extract_from_html(html: str) -> list:
    """从搜索页 HTML 抽取微博卡片（容错解析，不依赖浏览器 JS）"""
    items = []
    # 每张卡片: <div class="card-wrap">...<div class="weibo-text">正文</div>
    for m in re.finditer(r'<div class="weibo-text">(.*?)</div>', html, re.S):
        text = re.sub(r"<[^>]+>", "", m.group(1))
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 15:
            continue
        items.append(text[:300])
    return items


def build_url(query: str) -> str:
    q = urllib.parse.quote(query)
    cid = urllib.parse.quote(f'100103type=1&q={query}')
    return f"https://m.weibo.cn/search?containerid={cid}"


if __name__ == "__main__":
    queries = sys.argv[1:] or load_source_queries("weibo-reach")
    # 实际抓取在 hermes 浏览器内完成（见 fetch_weibo_reach）；此 CLI 仅输出计划，供调试
    print(json.dumps({"ok": True, "plan": [build_url(q) for q in queries]}, ensure_ascii=False))
