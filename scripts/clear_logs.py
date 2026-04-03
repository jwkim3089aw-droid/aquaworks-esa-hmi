# scripts/clear_logs.py
import shutil
from pathlib import Path


def clear_logs():
    # 1. 경로 설정: 현재 스크립트(scripts)의 부모 폴더(code) 내의 logs 폴더를 동적으로 탐색
    script_dir = Path(__file__).resolve().parent
    code_dir = script_dir.parent
    log_dir = code_dir / "logs"

    print(f"Log directory cleanup started: {log_dir}")

    # 2. 삭제 및 재생성 로직
    try:
        if log_dir.exists() and log_dir.is_dir():
            # 폴더와 내부의 모든 파일을 재귀적으로 삭제
            shutil.rmtree(log_dir)

            # 빈 폴더 다시 생성
            log_dir.mkdir(parents=True, exist_ok=True)
            print("All log data has been successfully deleted.")
        else:
            # logs 폴더가 아예 없는 경우 새롭게 생성
            log_dir.mkdir(parents=True, exist_ok=True)
            print("Log directory did not exist. Created a new empty log directory.")

    except PermissionError:
        print(
            "Error: Permission denied. Some log files might be currently in use by another process."
        )
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    clear_logs()
