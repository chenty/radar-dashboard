#!/usr/bin/env python3
"""Radar Dashboard — 「女人40岁之后」选题雷达 可视化面板"""

import json
import os
import time
import hashlib
from pathlib import Path
from datetime import datetime, date
from flask import Flask, jsonify, send_from_directory, request

app = Flask(__name__, static_folder='static', template_folder='templates')

BASE_DIR = Path(__file__).resolve().parent
REPORTS_DIR = Path(os.environ.get('REPORTS_DIR', BASE_DIR / 'data' / 'reports'))
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ─── API ────────────────────────────────────────────────────────────────────

@app.route('/api/reports')
def list_reports():
    """返回所有日报的摘要列表（按日期降序）"""
    try:
        files = sorted(REPORTS_DIR.glob('*.json'), reverse=True)
    except FileNotFoundError:
        return jsonify([])

    reports = []
    for f in files:
        try:
            data = json.loads(f.read_text())
            modules = data.get('modules', {}) or {}
            summary = {
                'date': data.get('date', f.stem),
                'moduleCount': sum(1 for m in modules.values() if m and (
                    (isinstance(m, list) and len(m) > 0) or
                    (isinstance(m, dict) and m.get('method'))
                )),
                'modules': {},
                'sources': data.get('sources', {}),
            }
            if modules.get('opportunities'):
                summary['modules']['opportunities'] = [
                    {'title': o.get('title', '')[:60]} for o in modules['opportunities'][:2]
                ]
            if modules.get('moneyCases'):
                summary['modules']['moneyCases'] = [
                    {'title': m.get('title', m.get('what', ''))[:60]} for m in modules['moneyCases'][:1]
                ]
            if modules.get('dailyWisdom') and modules['dailyWisdom'].get('method'):
                summary['modules']['dailyWisdom'] = modules['dailyWisdom']['method'][:80]
            reports.append(summary)
        except (json.JSONDecodeError, KeyError):
            continue
    return jsonify(reports)


@app.route('/api/reports/<date_str>')
def get_report(date_str):
    """返回指定日期的完整日报"""
    for f in REPORTS_DIR.glob(f'{date_str}*.json'):
        try:
            data = json.loads(f.read_text())
            return jsonify(data)
        except json.JSONDecodeError:
            return jsonify({'error': 'corrupted file'}), 500
    return jsonify({'error': 'not found'}), 404


@app.route('/api/topic-config')
def get_topic_config():
    """读取当前主题切口；无效配置返回错误，不影响历史日报。"""
    from scripts.query_config import load_topic_facets
    try:
        data = load_topic_facets()
        return jsonify(data)
    except ValueError:
        return jsonify({'error': '主题切口配置无效'}), 503


@app.route('/api/modules/<module_name>')
def get_module(module_name):
    """跨日期聚合指定模块的全部内容"""
    module_map = {
        'signals': 'dataSignals',
        # 旧定位遗留模块：JSON 里如仍存在可经旧路由访问，面板不再展示
        'opportunities': 'opportunities',
        'money-cases': 'moneyCases',
        'inspirations': 'productInspirations',
        'growth': 'growthTips',
        'tools': 'tools',
        'pitfalls': 'pitfalls',
        'topics': 'publicAccountTopics',
        'quotes': 'quoteBank',
        'angles': 'angleBank',
        'qa': 'readerQA',
        'sidebiz': 'sidebizCases',
        'growthops': 'growthOps',
        'mini-program': 'publicAccountTopics',  # 旧路由别名（兼容已保存的收藏/书签）
        'wisdom': 'dailyWisdom',
    }
    key = module_map.get(module_name)
    if not key:
        return jsonify({'error': 'unknown module'}), 404

    results = []
    try:
        files = sorted(REPORTS_DIR.glob('*.json'), reverse=True)
    except FileNotFoundError:
        return jsonify([])

    for f in files:
        try:
            data = json.loads(f.read_text())
            modules = data.get('modules', {}) or {}
            items = modules.get(key, [])
            if items:
                if isinstance(items, dict):
                    items = [items]
                for item in items:
                    if isinstance(item, dict) and item:
                        results.append({
                            'date': data.get('date', f.stem),
                            **item
                        })
        except (json.JSONDecodeError, KeyError):
            continue
    return jsonify(results)


@app.route('/api/raw-dates')
def list_raw_dates():
    """返回所有原始信号文件的日期（降序）"""
    raw_dir = REPORTS_DIR.parent / 'raw_signals'
    if not raw_dir.exists():
        return jsonify([])
    dates = sorted([f.stem for f in raw_dir.glob('*.json')], reverse=True)
    return jsonify(dates)


@app.route('/api/sources')
def get_sources_status():
    """信息源管理：返回所有源的接入状态、可用性、最近采集情况"""
    from scripts.source_config import load_signal_sources
    try:
        source_meta = load_signal_sources()
    except ValueError:
        return jsonify({'error': '信号源配置无效'}), 503
    # 读状态文件
    state = {}
    state_file = REPORTS_DIR.parent / 'daily_signals_state.json'
    try:
        state = json.loads(state_file.read_text())
    except Exception:
        pass
    src_state = state.get('sources', {})

    # 读最近一次 raw_signals 统计
    raw_dir = REPORTS_DIR.parent / 'raw_signals'
    latest_raw = {}
    if raw_dir.exists():
        dates = sorted([f.stem for f in raw_dir.glob('*.json')], reverse=True)
        if dates:
            try:
                latest_raw = json.loads((raw_dir / f'{dates[0]}.json').read_text())
            except Exception:
                pass

    now_ts = int(time.time())
    result = []
    for meta in source_meta:
        key = meta['key']
        s = src_state.get(key, {})
        last_seen = s.get('last_seen_ts')
        seen_count = len(s.get('seen_ids', []))

        # 今日/最近条目数
        today_count = len(latest_raw.get('sources', {}).get(key, []))

        # 状态判定
        if not meta['enabled']:
            status = 'disabled'
            status_text = '已停用'
            note = '配置中已停用，不参与新采集'
        elif key == 'reddit':
            # Reddit 需要 OAuth 才能稳定工作
            import os
            if not os.environ.get('REDDIT_CLIENT_ID'):
                status = 'config_required'
                status_text = '需配置 OAuth'
                note = 'IP 被封，注册 Reddit App 后配置 REDDIT_CLIENT_ID 解锁'
            elif last_seen and (now_ts - last_seen) < 3 * 86400:
                status = 'ok'
                status_text = '正常'
                note = ''
            else:
                status = 'error'
                status_text = '异常'
                note = '最近采集失败'
        elif last_seen:
            hours_ago = (now_ts - last_seen) / 3600
            if hours_ago < 72:
                status = 'ok'
                status_text = '正常'
                note = f'{hours_ago:.0f} 小时前采集'
            else:
                status = 'stale'
                status_text = '久未采集'
                note = f'{hours_ago/24:.0f} 天前最后采集'
        else:
            status = 'no_data'
            status_text = '未采集'
            note = '尚未运行或新接入'

        result.append({
            **meta,
            'status': status,
            'status_text': status_text,
            'last_seen': last_seen,
            'last_seen_text': time.strftime('%m-%d %H:%M', time.localtime(last_seen)) if last_seen else '—',
            'seen_count': seen_count,
            'today_count': today_count,
            'note': note,
        })

    # 汇总
    summary = {
        'total': len(result),
        'ok': sum(1 for r in result if r['status'] == 'ok'),
        'warn': sum(1 for r in result if r['status'] in ('config_required', 'error', 'stale', 'no_data')),
        'disabled': sum(1 for r in result if r['status'] == 'disabled'),
        'last_run': state.get('last_run', ''),
        'latest_raw_date': list(latest_raw.keys())[0] if latest_raw else '',
    }
    return jsonify({'summary': summary, 'sources': result})


@app.route('/api/raw/<date_str>')
def get_raw_signals(date_str):
    """返回指定日期的原始信号（按平台分组，含 url）"""
    raw_dir = REPORTS_DIR.parent / 'raw_signals'
    path = raw_dir / f'{date_str}.json'
    if not path.exists():
        return jsonify({'error': 'not found'}), 404
    try:
        return jsonify(json.loads(path.read_text()))
    except json.JSONDecodeError:
        return jsonify({'error': 'corrupted file'}), 500


@app.route('/api/stats')
def get_stats():
    """聚合统计"""
    total_reports = 0
    module_counts = {}
    source_totals = {}
    monthly = {}

    try:
        files = sorted(REPORTS_DIR.glob('*.json'))
    except FileNotFoundError:
        return jsonify({'totalReports': 0, 'modules': {}, 'sources': {}, 'monthly': {}})

    for f in files:
        try:
            data = json.loads(f.read_text())
            total_reports += 1
            modules = data.get('modules', {}) or {}
            for mod_name, mod_data in modules.items():
                if mod_data and (
                    (isinstance(mod_data, list) and len(mod_data) > 0) or
                    (isinstance(mod_data, dict) and mod_data.get('method'))
                ):
                    module_counts[mod_name] = module_counts.get(mod_name, 0) + 1

            sources = data.get('sources', {}) or {}
            for k, v in sources.items():
                source_totals[k] = source_totals.get(k, 0) + (v if isinstance(v, (int, float)) else 0)

            dt = data.get('date', '')
            if dt:
                month = dt[:7]
                monthly[month] = monthly.get(month, 0) + 1
        except:
            continue

    return jsonify({
        'totalReports': total_reports,
        'modules': module_counts,
        'sources': source_totals,
        'monthly': dict(sorted(monthly.items())),
    })


@app.route('/api/trends')
def get_trends():
    key_freq = {}
    try:
        files = sorted(REPORTS_DIR.glob('*.json'), reverse=True)
    except FileNotFoundError:
        return jsonify([])

    for f in files:
        try:
            data = json.loads(f.read_text())
            for tag in (data.get('tags', []) or []):
                tag = tag.lstrip('#')
                if tag not in key_freq:
                    key_freq[tag] = []
                key_freq[tag].append(data.get('date', f.stem))
        except:
            continue
    sorted_tags = sorted(key_freq.items(), key=lambda x: -len(x[1]))
    return jsonify([
        {'tag': tag, 'count': len(dates), 'dates': dates}
        for tag, dates in sorted_tags[:30]
    ])


# ─── Frontend ───────────────────────────────────────────────────────────────

@app.route('/')
def index():
    resp = send_from_directory('templates', 'index.html')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)




# ─── 选题状态流（信号→选题→文章）────────────────────────────
TOPICS_STATUS_FILE = BASE_DIR / 'data' / 'topic_status.json'
FACETS = ["自我成长", "健康与身体", "财务与搞钱", "关系与家庭", "心态与情绪", "生活方式"]
TOPIC_STAGES = ["idea", "picked", "drafting", "published"]


def _load_topic_status():
    if not TOPICS_STATUS_FILE.exists():
        return {}
    try:
        data = json.loads(TOPICS_STATUS_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_topic_status(data):
    TOPICS_STATUS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


@app.route('/api/topics/status', methods=['GET'])
def get_topic_statuses():
    return jsonify(_load_topic_status())


@app.route('/api/topics/status', methods=['POST'])
def set_topic_status():
    """body: {key: '<date>::<hash>', stage: 'idea|picked|drafting|published', facet: '...'}"""
    payload = request.get_json(silent=True) or {}
    key = (payload.get('key') or '').strip()
    if not key:
        return jsonify({'error': 'key required'}), 400
    data = _load_topic_status()
    entry = data.get(key, {})
    if 'stage' in payload:
        stage = payload['stage']
        if stage not in TOPIC_STAGES:
            return jsonify({'error': 'bad stage'}), 400
        entry['stage'] = stage
        entry['updated_at'] = time.strftime('%Y-%m-%d %H:%M')
    if 'facet' in payload:
        if payload['facet'] and payload['facet'] not in FACETS:
            return jsonify({'error': 'bad facet'}), 400
        entry['facet'] = payload['facet'] or None
    data[key] = entry
    _save_topic_status(data)
    return jsonify({'ok': True, 'key': key, **entry})




# ─── 选题复盘库（文章发布数据 → 反推选题表现）──────────────
REVIEWS_FILE = BASE_DIR / 'data' / 'topic_reviews.json'


def _load_reviews():
    if not REVIEWS_FILE.exists():
        return []
    try:
        data = json.loads(REVIEWS_FILE.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


@app.route('/api/topic-reviews', methods=['GET'])
def list_topic_reviews():
    return jsonify(_load_reviews())


@app.route('/api/topic-reviews', methods=['POST'])
def add_topic_review():
    """body: {title, published_date, facet, source, views, likes, reads, followers, notes}"""
    payload = request.get_json(silent=True) or {}
    title = (payload.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'title required'}), 400
    reviews = _load_reviews()
    # 同标题覆盖更新（复盘一次成稿）
    entry = {
        'id': hashlib.md5(title.encode()).hexdigest()[:10],
        'title': title,
        'published_date': payload.get('published_date', time.strftime('%Y-%m-%d')),
        'facet': payload.get('facet', ''),
        'source': payload.get('source', ''),
        'views': int(payload.get('views') or 0),
        'likes': int(payload.get('likes') or 0),
        'reads': int(payload.get('reads') or 0),
        'followers': int(payload.get('followers') or 0),
        'notes': payload.get('notes', ''),
        'updated_at': time.strftime('%Y-%m-%d %H:%M'),
    }
    reviews = [r for r in reviews if r.get('title') != title]
    reviews.append(entry)
    reviews.sort(key=lambda x: x.get('published_date', ''), reverse=True)
    REVIEWS_FILE.write_text(json.dumps(reviews, ensure_ascii=False, indent=2))
    return jsonify({'ok': True, **entry})


@app.route('/api/topic-reviews/<review_id>', methods=['DELETE'])
def delete_topic_review(review_id):
    reviews = _load_reviews()
    reviews = [r for r in reviews if r.get('id') != review_id]
    REVIEWS_FILE.write_text(json.dumps(reviews, ensure_ascii=False, indent=2))
    return jsonify({'ok': True})


# ═══ 收藏功能 ══════════════════════════════════════════════════════════════
FAVORITES_FILE = REPORTS_DIR.parent / 'favorites.json'


def _load_favorites():
    if not FAVORITES_FILE.exists():
        return []
    try:
        data = json.loads(FAVORITES_FILE.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_favorites(items):
    FAVORITES_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2))


def _fav_id(payload):
    """生成收藏唯一 id：type + url/title 的 hash"""
    key = f"{payload.get('type', '')}|{payload.get('url', '')}|{payload.get('title', '')}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


@app.route('/api/favorites', methods=['GET'])
def list_favorites():
    """获取所有收藏（倒序）"""
    favs = _load_favorites()
    favs.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return jsonify(favs)


@app.route('/api/favorites', methods=['POST'])
def add_favorite():
    """添加收藏。body: {type, title, url, source, date, desc, raw, ...}"""
    payload = request.get_json(silent=True) or {}
    title = (payload.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'title required'}), 400

    fav_id = payload.get('id') or _fav_id(payload)
    favs = _load_favorites()

    # 去重：同 id 不重复添加
    if any(f.get('id') == fav_id for f in favs):
        return jsonify({'ok': True, 'id': fav_id, 'duplicate': True})

    item = {
        'id': fav_id,
        'type': payload.get('type', 'signal'),        # signal / report_item / topics（旧收藏数据可能存为 'miniapp'）
        'title': title,
        'title_cn': payload.get('title_cn', ''),
        'name_cn': payload.get('name_cn', ''),
        'desc_cn': payload.get('desc_cn', ''),
        'url': payload.get('url', ''),
        'source': payload.get('source', ''),          # 平台 key（如 github-zh / appstore-cn）
        'source_label': payload.get('source_label', ''),
        'date': payload.get('date', ''),
        'module': payload.get('module', ''),          # 日报模块 key（如 opportunities）
        'desc': payload.get('desc', ''),
        'raw': payload.get('raw', {}),                # 完整原始数据，收藏后可原样还原
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    favs.append(item)
    _save_favorites(favs)
    return jsonify({'ok': True, 'id': fav_id})


@app.route('/api/favorites/<fav_id>', methods=['DELETE'])
def delete_favorite(fav_id):
    """删除收藏"""
    favs = _load_favorites()
    new_favs = [f for f in favs if f.get('id') != fav_id]
    if len(new_favs) == len(favs):
        return jsonify({'error': 'not found'}), 404
    _save_favorites(new_favs)
    return jsonify({'ok': True})


@app.route('/api/favorites/check/<fav_id>', methods=['GET'])
def check_favorite(fav_id):
    """检查是否已收藏"""
    favs = _load_favorites()
    return jsonify({'exists': any(f.get('id') == fav_id for f in favs)})


if __name__ == '__main__':
    import sys
    reports = len(list(REPORTS_DIR.glob('*.json')))
    print(f"🚀 Radar Dashboard")
    print(f"   Reports: {reports} files")
    print(f"   URL: http://127.0.0.1:5080")
    if '--prod' in sys.argv:
        from waitress import serve
        serve(app, host='127.0.0.1', port=5080)
    else:
        app.run(host='127.0.0.1', port=5080, debug=False)
