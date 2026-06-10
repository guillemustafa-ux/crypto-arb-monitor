"""Alertas por Telegram Bot API."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("arb.telegram")

_FRONT_TITLE = {
    "A": "Tradicional ↔ Cripto",
    "B": "Cripto ↔ Cripto",
}
_MODE_TXT = {
    "trad_to_crypto": "comprar dólar → vender USDT",
    "crypto_to_trad": "comprar USDT → vender dólar",
    "spot_spot": "Spot ↔ Spot",
    "p2p_p2p": "P2P ↔ P2P",
    "spot_p2p": "Spot ↔ P2P",
    "same_brand": "misma plataforma",
}


def _fmt(n: float) -> str:
    return f"{n:,.2f}"


def build_message(opp) -> str:
    front = _FRONT_TITLE.get(opp.front, opp.front)
    mode = _MODE_TXT.get(opp.mode, opp.mode)
    return (
        f"🟢 <b>Oportunidad de arbitraje — Frente {opp.front}</b>\n"
        f"<i>{front} · {mode}</i>\n"
        f"\n"
        f"🟩 <b>Comprar</b> en <b>{opp.buy_where}</b> a ${_fmt(opp.buy_price)}\n"
        f"🟥 <b>Vender</b> en <b>{opp.sell_where}</b> a ${_fmt(opp.sell_price)}\n"
        f"\n"
        f"📊 Spread bruto: <b>{opp.gross_pct:+.2f}%</b>\n"
        f"💰 Spread neto: <b>{opp.net_pct:+.2f}%</b> (descontando comisiones)\n"
        f"\n"
        f"<i>⚠️ Solo monitoreo — verificá liquidez, límites y tiempos de "
        f"acreditación antes de operar.</i>"
    )


async def send_opportunity(token: str, chat_id: str, opp) -> bool:
    """Envía la alerta. Devuelve True si Telegram respondió ok."""
    return await _send(token, chat_id, build_message(opp))


async def send_test(token: str, chat_id: str) -> bool:
    return await _send(
        token, chat_id,
        "✅ <b>Arb Monitor (Argentina)</b> conectado correctamente a Telegram.",
    )


async def _send(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            if not data.get("ok"):
                logger.warning("Telegram respondió error: %s", data)
            return bool(data.get("ok"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error enviando a Telegram: %s", exc)
        return False
