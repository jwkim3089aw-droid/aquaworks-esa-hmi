# app/core/tsdb.py
import os
import logging
from typing import Any, Optional, Union, List

# Pylance 에러 수정을 위해 정확한 경로로 변경
from influxdb_client.client.influxdb_client import InfluxDBClient
from influxdb_client.client.write.point import Point
from influxdb_client.client.write_api import ASYNCHRONOUS, WriteApi
from influxdb_client.client.query_api import QueryApi
from dotenv import load_dotenv

logger = logging.getLogger("app.core.tsdb")
load_dotenv()


class TimeSeriesDB:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TimeSeriesDB, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self.url = os.getenv("INFLUXDB_URL", "http://localhost:8086")
        self.token = os.getenv("INFLUXDB_TOKEN", "")
        self.org = os.getenv("INFLUXDB_ORG", "esa_org")
        self.bucket = os.getenv("INFLUXDB_BUCKET", "sensor_data")
        self.client: Optional[InfluxDBClient] = None
        self.write_api: Optional[WriteApi] = None
        self.query_api: Optional[QueryApi] = None
        self._initialized = True

    def connect(self):
        if self.client:
            return
        try:
            self.client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
            self.write_api = self.client.write_api(write_options=ASYNCHRONOUS)
            self.query_api = self.client.query_api()
            logger.info(f"Connected to InfluxDB at {self.url}")
        except Exception as e:
            logger.error(f"Failed to connect to InfluxDB: {e}")

    def write(self, tag_key: str, value: Any, measurement: str = "sensors"):
        if not self.write_api:
            self.connect()
        if self.write_api is None:
            return
        try:
            p = Point(measurement).tag("tag_name", tag_key).field("value", float(value))
            self.write_api.write(bucket=self.bucket, org=self.org, record=p)
        except Exception as e:
            logger.error(f"Error writing to InfluxDB ({tag_key}): {e}")

    def query_raw(self, query_str: str) -> Any:
        """Pylance 타입 에러를 피하기 위해 Any로 리턴"""
        if not self.query_api:
            self.connect()
        if self.query_api is None:
            return None
        try:
            # 리스트 또는 데이터프레임이 반환됨
            return self.query_api.query_data_frame(query=query_str, org=self.org)
        except Exception as e:
            logger.error(f"InfluxDB Query Error: {e}")
            return None

    def close(self):
        if self.write_api:
            self.write_api.close()
        if self.client:
            self.client.close()


tsdb = TimeSeriesDB()
