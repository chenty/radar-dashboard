#!/usr/bin/env python3
"""xyfm_transcribe.py — 小宇宙单集 音频下载 + 本地转写
用法:
  # 下载整集音频（仅下载）
  venv/bin/python scripts/xyfm_transcribe.py <episode_url或id> --download-only

  # 下载 + 转写文字稿（默认 small 模型，输出 markdown 到 data/transcripts/）
  venv/bin/python scripts/xyfm_transcribe.py <episode_url或id>

  # 只转写已下载的音频
  venv/bin/python scripts/xyfm_transcribe.py --audio /path/to/file.m4a

  # 快速模式（base 模型，速度约 3 倍，质量略降）
  venv/bin/python scripts/xyfm_transcribe.py <url> --model base

依赖: requests（采集已有）、faster-whisper（venv 内已装）、ffmpeg（系统）
说明:
  - 小宇宙单集页 HTML 内嵌 media.xyzcdn.net 音频直链，免登录
  - 转写走本地 faster-whisper int8（CPU），无 GPU 速度约 10x 实时
  - HF 模型下载需代理: https_proxy=http://127.0.0.1:7897（仅首次）
"""
import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / 'data' / 'transcripts'
AUDIO_DIR = OUT_DIR / 'audio'
UA = {"User-Agent": "Mozilla/5.0"}

EPISODE_RE = re.compile(r'episode/([\w-]+)|^([0-9a-f]{16,24})$')  # URL 或裸 id


def fetch_episode(episode_id: str) -> dict:
    """抓单集页，提取音频直链与元信息。"""
    url = f"https://www.xiaoyuzhoufm.com/episode/{episode_id}"
    r = requests.get(url, headers=UA, timeout=20)
    r.raise_for_status()
    t = r.text

    audio = None
    for pat in (r'https://media\.xyzcdn\.net/[^"\\]+\.m4a',
                r'https://media\.xyzcdn\.net/[^"\\]+\.mp3',
                r'https://media\.xyzcdn\.net/[^"\\]+'):
        m = re.search(pat, t)
        if m:
            audio = m.group(0)
            break
    if not audio:
        raise RuntimeError("页面中未找到音频直链（可能单集不存在或已下架）")

    title_m = re.search(r'<title>([^<]+)</title>', t)
    title = title_m.group(1).strip() if title_m else episode_id
    title = re.sub(r'\s*-\s*小宇宙.*$', '', title)          # 去尾部站点后缀
    title = re.sub(r'\s*\|\s*小宇宙.*$', '', title)          # 去竖线后缀变体
    # 「节目标题 - 播客名」拆分
    if ' - ' in title:
        ep_title, show = title.rsplit(' - ', 1)
    else:
        ep_title, show = title, ''

    return {"id": episode_id, "url": url, "audio": audio,
            "title": ep_title, "show": show}


def download_audio(audio_url: str, dest: Path) -> Path:
    """流式下载整集音频。"""
    if dest.exists() and dest.stat().st_size > 0:
        print(f"[skip] 已存在: {dest}")
        return dest
    print(f"[download] {audio_url}")
    with requests.get(audio_url, headers=UA, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get('Content-Length', 0))
        done = 0
        with open(dest, 'wb') as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done/1048576:.0f}/{total/1048576:.0f} MB", end='', flush=True)
    print()
    return dest


def to_wav(src: Path, dst: Path) -> Path:
    """ffmpeg 转 16k 单声道 wav（whisper 输入格式）。"""
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(dst)],
        check=True, capture_output=True)
    return dst


def transcribe(wav: Path, model_name: str = 'small') -> str:
    """本地 faster-whisper 转写，返回全文。"""
    from faster_whisper import WhisperModel
    print(f"[transcribe] model={model_name} (CPU int8)")
    model = WhisperModel(model_name, device='cpu', compute_type='int8')
    t0 = time.time()
    segs, info = model.transcribe(str(wav), language='zh', vad_filter=True)
    parts = []
    for s in segs:
        parts.append(s.text.strip())
        # 进度提示（按音频位置）
        if info.duration and int(s.end) % 600 < 30:
            print(f"\r  {int(s.end)//60}min", end='', flush=True)
    print(f"\n[done] {info.duration/60:.0f}min 音频，转写耗时 {time.time()-t0:.0f}s")
    return ''.join(parts)


def save_markdown(meta: dict, text: str, model_name: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]', '_', meta['title'])[:60]
    out = OUT_DIR / f"{meta['id'][:12]}_{safe}.md"
    md = (
        f"# {meta['title']}\n\n"
        f"- 播客: {meta['show'] or '未知'}\n"
        f"- 链接: {meta['url']}\n"
        f"- 音频: {meta['audio']}\n"
        f"- 转写: faster-whisper/{model_name} @ {datetime.now():%Y-%m-%d %H:%M}\n\n"
        f"## 全文\n\n{text}\n"
    )
    out.write_text(md, encoding='utf-8')
    print(f"[saved] {out}")
    return out


def main():
    ap = argparse.ArgumentParser(description='小宇宙单集下载+转写')
    ap.add_argument('episode', nargs='?', help='单集 URL 或 episode id')
    ap.add_argument('--audio', help='直接转写本地音频文件（跳过下载）')
    ap.add_argument('--download-only', action='store_true', help='只下载音频不转写')
    ap.add_argument('--model', default='small', choices=['base', 'small', 'medium'],
                    help='whisper 模型（默认 small；base 更快质量略降）')
    args = ap.parse_args()

    if args.audio:
        wav = to_wav(Path(args.audio), Path('/tmp/xy_transcribe.wav'))
        text = transcribe(wav, args.model)
        print('\n=== 文字稿 ===\n')
        print(text)
        return

    if not args.episode:
        ap.error('需要 episode URL/id 或 --audio')

    m = EPISODE_RE.search(args.episode)
    if not m:
        sys.exit(f"无法从输入解析 episode id: {args.episode}")
    ep_id = m.group(1) or m.group(2)

    meta = fetch_episode(ep_id)
    print(f"[episode] {meta['title']}（{meta['show']}）")
    ext = '.m4a' if '.m4a' in meta['audio'] else '.mp3'
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    audio_path = download_audio(meta['audio'], AUDIO_DIR / f"{ep_id[:12]}{ext}")
    meta['local_audio'] = str(audio_path)

    # 元信息落地（含未转写的情况，便于以后补转）
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{ep_id[:12]}_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')

    if args.download_only:
        print(f"[done] 音频已下载: {audio_path}")
        return

    wav = to_wav(audio_path, Path(f'/tmp/xy_{ep_id[:12]}.wav'))
    text = transcribe(wav, args.model)
    save_markdown(meta, text, args.model)
    print('\n=== 文字稿前 500 字 ===\n')
    print(text[:500])


if __name__ == '__main__':
    main()
