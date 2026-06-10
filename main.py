"""Entrypoint: arranca el dashboard FastAPI y el loop de monitoreo en el mismo proceso."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from src.config import load_config
from src.dashboard import register_routes
from src.monitor import MonitorState, run as run_monitor
from src.storage import Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("arb")

config = load_config()
storage = Storage(config.db_path)
state = MonitorState(config=config, storage=storage)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await storage.init()
    monitor_task = asyncio.create_task(run_monitor(state))
    logger.info("App lista | dashboard en puerto %s", config.port)
    try:
        yield
    finally:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        await storage.close()


app = FastAPI(title="Crypto Arbitrage Monitor", lifespan=lifespan)
register_routes(app, state)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=config.port, log_level="warning")
