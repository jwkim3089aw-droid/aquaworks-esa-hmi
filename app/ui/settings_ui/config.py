# app/ui/settings_ui/config.py

# 🚀 실제 C# 장비 메모리 맵 기반의 HMI 매핑표 밑그림 (UI 렌더링용)
TAG_LIST = [
    # --- 1. 센서 데이터 (읽기 전용) ---
    {"key": "do", "label": "DO (용존산소)", "def_type": "Holding", "def_addr": 0, "def_ua": ""},
    {"key": "ph", "label": "pH (산성도)", "def_type": "Holding", "def_addr": 1, "def_ua": ""},
    {"key": "temp", "label": "TEMP (온도)", "def_type": "Holding", "def_addr": 2, "def_ua": ""},
    {
        "key": "water_flow",
        "label": "WATER FLOW (유량)",
        "def_type": "Holding",
        "def_addr": 3,
        "def_ua": "",
    },
    {"key": "mlss", "label": "MLSS (부유물질)", "def_type": "Holding", "def_addr": 4, "def_ua": ""},
    # 👇 [수정됨] 시뮬레이터에서 피드백 받을 펌프 현재값 (6번 주소) 복구!
    {
        "key": "pump_hz",
        "label": "현재 펌프 주파수 (Hz)",
        "def_type": "Holding",
        "def_addr": 6,
        "def_ua": "",
    },
    # --- 2. 전력 데이터 ---
    {
        "key": "power_curr",
        "label": "현재 소비전력",
        "def_type": "Holding",
        "def_addr": 7,
        "def_ua": "",
    },
    {
        "key": "power_accm",
        "label": "누적 전력량",
        "def_type": "Holding",
        "def_addr": 9,
        "def_ua": "",
    },
    # --- 3. 시스템 제어 (0/1 스위치 영역) ---
    {
        "key": "emg_status",
        "label": "[제어] 비상정지",
        "def_type": "Coil",
        "def_addr": 0,
        "def_ua": "",
    },
    {
        "key": "pump_power",
        "label": "[제어] 펌프 전원",
        "def_type": "Coil",
        "def_addr": 1,
        "def_ua": "",
    },
    {
        "key": "pump_auto",
        "label": "[제어] 펌프 자동모드",
        "def_type": "Coil",
        "def_addr": 2,
        "def_ua": "",
    },
    {
        "key": "valve_power",
        "label": "[제어] 밸브 전원",
        "def_type": "Coil",
        "def_addr": 3,
        "def_ua": "",
    },
    # --- 4. 수동 제어 설정값 (🚀 백엔드 API와 완벽하게 연결되는 키값!) ---
    {
        "key": "set_hz",
        "label": "[설정] 펌프 주파수 (Hz)",
        "def_type": "Holding",
        "def_addr": 29,
        "def_ua": "",
    },
    {
        "key": "valve_pos",
        "label": "[설정] 밸브 개도율 (%)",
        "def_type": "Holding",
        "def_addr": 30,
        "def_ua": "",
    },
    # --- 5. 시스템 상태 ---
    {"key": "device_id", "label": "기기 ID", "def_type": "Holding", "def_addr": 49, "def_ua": ""},
    {
        "key": "exception_code",
        "label": "에러 코드",
        "def_type": "Holding",
        "def_addr": 52,
        "def_ua": "",
    },
]

# UI 드롭다운 선택지 목록
MB_TYPES = ["Coil", "Discrete", "Input", "Holding"]

# 가상 시뮬레이션 모드 ON 시 자동입력(Autofill)될 편의성 데이터
SIM_OPCUA_HOST = "127.0.0.1"
SIM_OPCUA_PORT = 4840
SIM_OPCUA_NS = "http://aquaworks.co.kr/ESA"
