"""Cliente de la API pública de CriptoYa (api.criptoya.com / criptoya.com/api).

Provee dos lecturas:
  - `fetch_dolar()`   → cotizaciones del dólar tradicional (oficial/blue/MEP/CCL)
  - `fetch_crypto()`  → USDT/ARS por plataforma (spot y P2P), con bruto y neto

Diseñado para que agregar pares o plataformas sea trivial: no hay nada hardcodeado
salvo el aplanado de MEP/CCL (que es anidado por bono en la API).
"""

from __future__ import annotations

import logging

import httpx

from . import platforms

logger = logging.getLogger("arb.criptoya")

_BASE = "https://criptoya.com/api"
_TIMEOUT = 15.0


class CriptoYa:
    def __init__(self, coin: str = "usdt", fiat: str = "ars", volume: float = 1) -> None:
        self.coin = coin
        self.fiat = fiat
        self.volume = volume
        self._client: httpx.AsyncClient | None = None

    async def init(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=_TIMEOUT,
            headers={"User-Agent": "crypto-arb-monitor/1.0"},
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def _get(self, path: str) -> dict | None:
        assert self._client is not None
        try:
            resp = await self._client.get(f"{_BASE}/{path}")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("GET %s falló: %s", path, exc)
            return None

    # ── Dólar tradicional ────────────────────────────────────────────────────
    async def fetch_dolar(
        self, mep_bond: str = "al30", ccl_bond: str = "al30", term: str = "24hs"
    ) -> dict[str, dict]:
        """Normaliza el endpoint /dolar a {tipo: {ask, bid, label}}.

        Para MEP/CCL la API anida por bono (al30/gd30/...) y término (24hs/ci);
        se toma el bono/término configurado y se usa su `price` como ask=bid.
        """
        raw = await self._get("dolar")
        if not raw:
            return {}

        out: dict[str, dict] = {}

        for tipo in ("oficial", "blue"):
            node = raw.get(tipo) or {}
            ask = node.get("ask") or node.get("price")
            bid = node.get("bid") or node.get("price")
            if ask and bid:
                out[tipo] = {"ask": float(ask), "bid": float(bid),
                             "label": tipo.capitalize()}

        for tipo, bond in (("mep", mep_bond), ("ccl", ccl_bond)):
            price = self._bond_price(raw.get(tipo), bond, term)
            if price:
                out[tipo] = {"ask": price, "bid": price,
                             "label": f"{tipo.upper()} ({bond})"}

        # Índice cripto propio de CriptoYa (informativo).
        cripto = (raw.get("cripto") or {}).get("usdt") or {}
        if cripto.get("ask") and cripto.get("bid"):
            out["cripto_usdt"] = {"ask": float(cripto["ask"]), "bid": float(cripto["bid"]),
                                  "label": "Cripto USDT (idx)"}

        return out

    @staticmethod
    def _bond_price(node: dict | None, bond: str, term: str) -> float | None:
        """Extrae price de mep/ccl → {bono}{término}{price}, con fallbacks."""
        if not node:
            return None
        candidates = [bond, "al30", "gd30"]
        for b in candidates:
            bond_node = node.get(b)
            if not isinstance(bond_node, dict):
                continue
            term_node = bond_node.get(term) or bond_node.get("24hs") or bond_node.get("ci")
            if isinstance(term_node, dict) and term_node.get("price"):
                return float(term_node["price"])
        return None

    # ── Cripto USDT/ARS (spot + P2P) ──────────────────────────────────────────
    async def fetch_crypto(self, whitelist: list[str] | None = None) -> dict[str, dict]:
        """Devuelve {plataforma: {ask, bid, totalAsk, totalBid, type, time}}.

        - bruto  = ask / bid
        - neto   = totalAsk / totalBid (ya descuenta la comisión de la plataforma)
        - filtra entradas sin liquidez (ask==0 o bid==0)
        - `type` ∈ {'spot', 'p2p'}
        """
        raw = await self._get(f"{self.coin}/{self.fiat}/{self.volume:g}")
        if not raw:
            return {}

        wl = set(whitelist or [])
        out: dict[str, dict] = {}
        for platform, q in raw.items():
            if not isinstance(q, dict):
                continue
            if wl and platform.lower() not in wl:
                continue
            ask, bid = q.get("ask"), q.get("bid")
            if not ask or not bid or ask <= 0 or bid <= 0:
                continue
            out[platform] = {
                "ask": float(ask),
                "bid": float(bid),
                "totalAsk": float(q.get("totalAsk") or ask),
                "totalBid": float(q.get("totalBid") or bid),
                "type": platforms.platform_type(platform),
                "time": q.get("time"),
            }
        return out
