# app/workers/db_writer.py
import asyncio
import logging
from app.core.tsdb import tsdb
from app.stream.state import db_q, Sample

logger = logging.getLogger("DB_WRITER")


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
