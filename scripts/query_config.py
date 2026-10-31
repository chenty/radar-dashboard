"""定向搜索默认词配置（不包含热榜或 Tavily 的独立配置）。"""
import json
import os
from pathlib import Path


def load_source_queries(source):
    if not os.environ.get('RADAR_SEARCH_CONFIG'):
        language = os.environ.get('RADAR_QUERY_LANGUAGE', 'zh')
        return [q for _, q in topic_queries(language)]
    path = Path(os.environ['RADAR_SEARCH_CONFIG'])
    try:
        config = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError('无法读取搜索词配置') from exc
    if not isinstance(config, dict):
        raise ValueError('搜索词配置必须是 JSON 对象')
    queries = config.get(source)
    if not isinstance(queries, list) or not queries or len(queries) > 20:
        raise ValueError(f'{source} 搜索词必须是包含 1–20 项的数组')
    if any(not isinstance(q, str) or not q.strip() or len(q.strip()) > 400 for q in queries):
        raise ValueError(f'{source} 搜索词必须是非空字符串，长度不超过 400')
    return [q.strip() for q in queries]


def load_topic_facets():
    path = Path(os.environ.get('RADAR_TOPIC_CONFIG', Path(__file__).resolve().parent.parent / 'config' / 'topic_facets.json'))
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError('无法读取主题切口配置') from exc
    if not isinstance(data, dict) or not isinstance(data.get('facets'), list) or not data['facets']:
        raise ValueError('主题切口配置必须包含非空 facets 数组')
    seen = set()
    for entry in data['facets']:
        if not isinstance(entry, dict):
            raise ValueError('每个主题切口必须是对象')
        name = entry.get('name')
        if not isinstance(name, str) or not name.strip() or len(name) > 100 or name in seen:
            raise ValueError('主题切口名称必须非空、唯一且不超过100字')
        seen.add(name)
        keywords = entry.get('keywords')
        if not isinstance(keywords, dict):
            raise ValueError('主题切口缺少 keywords')
        for language in ('zh', 'en'):
            words = keywords.get(language)
            if not isinstance(words, list) or not words or any(not isinstance(w, str) or not w.strip() or len(w) > 400 for w in words):
                raise ValueError(f'{name} 的 {language} 关键词必须为非空字符串数组')
    return data


def topic_queries(language='zh'):
    if language not in ('zh', 'en'):
        raise ValueError('关键词语言只支持 zh 或 en')
    data = load_topic_facets()
    return [(f['name'], f['keywords'][language][0].strip()) for f in data['facets']]
