# app/workers/db_writer.py
import os
import sys
import asyncio
import logging
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler

from app.core.tsdb import tsdb
from app.stream.state import db_q, Sample

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_DIR = PROJECT_ROOT / ".logs" / "app_events"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("DB_WRITER")
logger.setLevel(logging.INFO)

if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    file_handler = TimedRotatingFileHandler(
        filename=LOG_DIR / "db_writer.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if os.environ.get("ESA_DEV") == "1":
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)


async def run_db_writer():
    logger.info("Starting InfluxDB Writer...")

    while True:
        try:
            sample: Sample = await db_q.get()

            data_map = {
                "DO": sample.do,
                "MLSS": sample.mlss,
                "Temp": sample.temp,
                "pH": sample.ph,
                "AirFlow": sample.air_flow,
                "Power": sample.power,
                "PumpHz": sample.pump_hz,
                "Energy": sample.energy_kwh,
            }

            for tag, val in data_map.items():
                if val is not None:
                    tsdb.write(tag, val)

            db_q.task_done()

        except asyncio.CancelledError:
            logger.info("DB Writer Stopped.")
            break
        except Exception as e:
            logger.error(f"DB Write Error: {e}")
            await asyncio.sleep(1)
