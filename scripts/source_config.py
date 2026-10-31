"""信号源目录与启用状态；仅包含元数据，采集实现由代码白名单决定。"""
import json
import os
import re
from pathlib import Path


def load_signal_sources():
    path = Path(os.environ.get('RADAR_SOURCES_CONFIG', Path(__file__).resolve().parent.parent / 'config' / 'signal_sources.json'))
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError('无法读取信号源配置') from exc
    if not isinstance(data, dict) or not isinstance(data.get('sources'), list):
        raise ValueError('信号源配置必须包含 sources 数组')
    seen = set()
    for source in data['sources']:
        if not isinstance(source, dict):
            raise ValueError('信号源必须是对象')
        key, name, enabled = source.get('key'), source.get('name'), source.get('enabled')
        if not isinstance(key, str) or not key.strip() or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', key) or key in seen:
            raise ValueError('信号源 key 必须非空且唯一')
        if not isinstance(name, str) or not name.strip() or not isinstance(enabled, bool):
            raise ValueError(f'{key} 必须提供非空名称和布尔型 enabled')
        if any(not isinstance(source.get(field, ''), str) for field in ('emoji', 'category', 'type', 'desc')):
            raise ValueError(f'{key} 的描述字段必须是字符串')
        seen.add(key)
    return data['sources']
