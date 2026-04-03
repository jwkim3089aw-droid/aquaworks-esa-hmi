# app/core/device_config.py
import json
import logging
from typing import List, Dict, Any

# 🚀 중앙 통제식 경로 설정 불러오기
from app.core.config import get_settings

logger = logging.getLogger("DEVICE_CONFIG")

settings = get_settings()

# 기존 최상단 루트 폴더에서 .data/ 폴더 하위로 안전하게 격리!
CONFIG_PATH = settings.DATA_DIR / "device_config.json"


def load_device_configs() -> List[Dict[str, Any]]:
    """JSON 파일에서 전체 기기 설정을 읽어옵니다."""
    if not CONFIG_PATH.exists():
        return []
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"🚨 설정 파일 읽기 실패: {e}")
        return []


def save_device_configs(configs: List[Dict[str, Any]]) -> bool:
    """전체 기기 설정을 JSON 파일에 저장합니다."""
    try:
        # 혹시 모를 상황을 대비해 부모 디렉토리(.data)가 있는지 한 번 더 확인 (멱등성 보장)
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(configs, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"🚨 설정 파일 저장 실패: {e}")
        return False


def get_device_config(device_id: int) -> Dict[str, Any]:
    """특정 ID의 기기 설정만 쏙 뽑아옵니다."""
    configs = load_device_configs()
    for c in configs:
        if c.get("id") == device_id:
            return c
    return {}
