"""Carga y validación de configuración desde variables de entorno (.env).

El monitor compara dos frentes:
  A) dólar tradicional (oficial/blue/MEP/CCL) vs USDT/ARS
  B) USDT/ARS entre plataformas (spot↔spot, p2p↔p2p, spot↔p2p, misma marca)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

# Modalidades válidas del Frente B.
VALID_B_MODES = {"spot_spot", "p2p_p2p", "spot_p2p", "same_brand"}
# Tipos de dólar tradicional soportados (claves normalizadas por criptoya.py).
VALID_DOLLAR_TYPES = {"oficial", "blue", "mep", "ccl"}


def _split(raw: str) -> list[str]:
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


@dataclass
class Config:
    coin: str
    fiat: str
    volume: float
    dollar_types: list[str]
    platforms: list[str]              # whitelist; vacío = todas las que devuelva la API
    mep_bond: str
    ccl_bond: str
    bond_term: str                    # "24hs" | "ci"
    poll_interval: int
    min_net_pct_a: float
    min_net_pct_b: float
    b_modes: list[str]
    alert_cooldown_min: int
    telegram_bot_token: str
    telegram_chat_id: str
    db_path: str
    port: int
    extra_fee_overrides: dict[str, float] = field(default_factory=dict)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


def _extra_fee_overrides() -> dict[str, float]:
    """Lee EXTRA_FEE_<PLATAFORMA> (en %) para descontar costos no incluidos en
    el totalAsk/totalBid de CriptoYa (ej. transferencia bancaria/CBU)."""
    overrides: dict[str, float] = {}
    prefix = "EXTRA_FEE_"
    for key, raw in os.environ.items():
        if key.startswith(prefix) and raw.strip():
            name = key[len(prefix):].lower()
            try:
                overrides[name] = float(raw)
            except ValueError:
                pass
    return overrides


def load_config() -> Config:
    dollar_types = [t for t in _split(os.getenv("DOLLAR_TYPES", "oficial,blue,mep,ccl"))
                    if t in VALID_DOLLAR_TYPES] or ["oficial", "blue", "mep", "ccl"]

    b_modes = [m for m in _split(os.getenv("B_MODES", "spot_spot,p2p_p2p,spot_p2p,same_brand"))
               if m in VALID_B_MODES] or list(VALID_B_MODES)

    return Config(
        coin=os.getenv("COIN", "usdt").strip().lower(),
        fiat=os.getenv("FIAT", "ars").strip().lower(),
        volume=float(os.getenv("VOLUME", "1")),
        dollar_types=dollar_types,
        platforms=_split(os.getenv("PLATFORMS", "")),
        mep_bond=os.getenv("MEP_BOND", "al30").strip().lower(),
        ccl_bond=os.getenv("CCL_BOND", "al30").strip().lower(),
        bond_term=os.getenv("BOND_TERM", "24hs").strip().lower(),
        poll_interval=int(os.getenv("POLL_INTERVAL", "60")),
        min_net_pct_a=float(os.getenv("MIN_NET_PCT_A", "1.0")),
        min_net_pct_b=float(os.getenv("MIN_NET_PCT_B", "0.5")),
        b_modes=b_modes,
        alert_cooldown_min=int(os.getenv("ALERT_COOLDOWN_MIN", "15")),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        db_path=os.getenv("DB_PATH", "./arb.db").strip(),
        port=int(os.getenv("PORT", "8000")),
        extra_fee_overrides=_extra_fee_overrides(),
    )
