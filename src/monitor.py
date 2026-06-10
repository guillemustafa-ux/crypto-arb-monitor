"""Loop de monitoreo asyncio: consulta CriptoYa, detecta oportunidades, alerta."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from . import arbitrage, telegram
from .arbitrage import OppA, OppB
from .config import Config
from .criptoya import CriptoYa
from .storage import Storage

logger = logging.getLogger("arb.monitor")


@dataclass
class MonitorState:
    """Estado compartido en memoria entre el loop y el dashboard."""

    config: Config
    storage: Storage
    dolar: dict[str, dict] = field(default_factory=dict)
    crypto: dict[str, dict] = field(default_factory=dict)
    opps_a: list[OppA] = field(default_factory=list)
    opps_b: list[OppB] = field(default_factory=list)
    last_update: float = 0.0
    active_platforms: list[str] = field(default_factory=list)
    last_error: str | None = None


async def run(state: MonitorState) -> None:
    """Loop principal. Corre hasta que se cancela la task."""
    cfg = state.config
    client = CriptoYa(cfg.coin, cfg.fiat, cfg.volume)
    await client.init()
    logger.info("Monitor iniciado | %s/%s | dólares=%s | modos B=%s",
                cfg.coin.upper(), cfg.fiat.upper(), cfg.dollar_types, cfg.b_modes)

    try:
        while True:
            try:
                if not await state.storage.get_paused():
                    await _cycle(state, client)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                state.last_error = str(exc)
                logger.exception("Error en ciclo de monitoreo: %s", exc)
            await asyncio.sleep(cfg.poll_interval)
    finally:
        await client.close()
        logger.info("Monitor detenido, cliente cerrado")


async def _cycle(state: MonitorState, client: CriptoYa) -> None:
    cfg = state.config

    dolar, crypto = await asyncio.gather(
        client.fetch_dolar(cfg.mep_bond, cfg.ccl_bond, cfg.bond_term),
        client.fetch_crypto(cfg.platforms),
    )
    state.dolar = dolar
    state.crypto = crypto
    state.active_platforms = sorted(crypto.keys())

    opps_a = arbitrage.scan_front_a(dolar, crypto, cfg.dollar_types, cfg.extra_fee_overrides)
    opps_b = arbitrage.scan_front_b(crypto, cfg.b_modes, cfg.extra_fee_overrides)
    state.opps_a = opps_a
    state.opps_b = opps_b
    state.last_update = time.time()
    state.last_error = None

    for opp in arbitrage.find_opportunities(opps_a, cfg.min_net_pct_a):
        await _handle_opportunity(state, opp)
    for opp in arbitrage.find_opportunities(opps_b, cfg.min_net_pct_b):
        await _handle_opportunity(state, opp)


async def _handle_opportunity(state: MonitorState, opp) -> None:
    """Persiste y alerta una oportunidad, respetando el cooldown por ruta."""
    cfg = state.config
    now = time.time()
    key = f"{opp.front}_{opp.mode}_{opp.label}"

    last = await state.storage.get_last_alert(key)
    if now - last < cfg.alert_cooldown_min * 60:
        return  # ya alertamos esta ruta hace poco

    await state.storage.record_opportunity(opp)
    await state.storage.set_last_alert(key, now)

    logger.info("Oportunidad [%s/%s] %s | neto %.2f%%",
                opp.front, opp.mode, opp.label, opp.net_pct)

    if cfg.telegram_enabled:
        await telegram.send_opportunity(
            cfg.telegram_bot_token, cfg.telegram_chat_id, opp
        )
