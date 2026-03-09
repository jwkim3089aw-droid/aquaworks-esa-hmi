# app/core/device_config.py
import json
from pathlib import Path
from typing import List, Dict, Any

# 프로젝트 최상단에 생성될 JSON 파일 이름도 직관적으로 변경!
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "device_config.json"


def load_device_configs() -> List[Dict[str, Any]]:
    """JSON 파일에서 전체 기기 설정을 읽어옵니다."""
    if not CONFIG_PATH.exists():
        return []
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"🚨 설정 파일 읽기 실패: {e}")
        return []


def save_device_configs(configs: List[Dict[str, Any]]) -> bool:
    """전체 기기 설정을 JSON 파일에 저장합니다."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(configs, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"🚨 설정 파일 저장 실패: {e}")
        return False


def get_device_config(device_id: int) -> Dict[str, Any]:
    """특정 ID의 기기 설정만 쏙 뽑아옵니다."""
    configs = load_device_configs()
    for c in configs:
        if c.get("id") == device_id:
            return c
    return {}
