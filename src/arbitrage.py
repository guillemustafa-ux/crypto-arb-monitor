"""Núcleo de arbitraje cambiario argentino.

Frente A — tradicional vs cripto:
    Compara dólar oficial/blue/MEP/CCL contra USDT/ARS, en ambas direcciones:
      · comprar dólar tradicional → vender USDT
      · comprar USDT → vender dólar tradicional

Frente B — solo cripto (USDT/ARS):
    Compara plataformas entre sí: spot↔spot, p2p↔p2p, spot↔p2p y misma marca
    (spot vs su propio P2P). Comprar donde el `totalAsk` es menor y vender donde
    el `totalBid` es mayor.

Convención de precios: todo está en ARS por 1 USD/USDT. Se asume USD≈USDT 1:1.
  bruto = ask / bid  ·  neto = totalAsk / totalBid (ya descuenta comisión de la API)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from . import platforms


# ─────────────────────────────────────────────────────────────────────────────
# Frente A
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class OppA:
    front: str          # siempre "A"
    mode: str           # "trad_to_crypto" | "crypto_to_trad"
    label: str          # ej. "Oficial → USDT (Binance)"
    buy_where: str      # dónde se compra
    sell_where: str     # dónde se vende
    buy_price: float
    sell_price: float
    gross_pct: float
    net_pct: float

    def to_dict(self) -> dict:
        return asdict(self)


def scan_front_a(
    dolar: dict[str, dict],
    crypto: dict[str, dict],
    dollar_types: list[str],
    extra_overrides: dict[str, float] | None = None,
) -> list[OppA]:
    """Para cada tipo de dólar evalúa las dos rutas contra la mejor plataforma
    cripto de esa dirección (mayor totalBid para vender, menor totalAsk para
    comprar)."""
    if not crypto:
        return []

    # Mejor plataforma para vender USDT (mayor totalBid) y para comprar (menor totalAsk).
    best_sell = max(crypto.items(), key=lambda kv: kv[1]["totalBid"])
    best_buy = min(crypto.items(), key=lambda kv: kv[1]["totalAsk"])
    sell_plat, sell_q = best_sell
    buy_plat, buy_q = best_buy

    opps: list[OppA] = []
    for tipo in dollar_types:
        node = dolar.get(tipo)
        if not node:
            continue
        tlabel = node.get("label", tipo.capitalize())

        # Ruta 1: comprar dólar tradicional (ask) → vender USDT (totalBid).
        gross = (sell_q["bid"] - node["ask"]) / node["ask"] * 100
        net = (sell_q["totalBid"] - node["ask"]) / node["ask"] * 100
        net -= platforms.extra_fee_pct(sell_plat, extra_overrides)
        opps.append(OppA(
            front="A", mode="trad_to_crypto",
            label=f"{tlabel} → {platforms.label(sell_plat)}",
            buy_where=tlabel, sell_where=platforms.label(sell_plat),
            buy_price=node["ask"], sell_price=sell_q["totalBid"],
            gross_pct=gross, net_pct=net,
        ))

        # Ruta 2: comprar USDT (totalAsk) → vender dólar tradicional (bid).
        gross = (node["bid"] - buy_q["ask"]) / buy_q["ask"] * 100
        net = (node["bid"] - buy_q["totalAsk"]) / buy_q["totalAsk"] * 100
        net -= platforms.extra_fee_pct(buy_plat, extra_overrides)
        opps.append(OppA(
            front="A", mode="crypto_to_trad",
            label=f"{platforms.label(buy_plat)} → {tlabel}",
            buy_where=platforms.label(buy_plat), sell_where=tlabel,
            buy_price=buy_q["totalAsk"], sell_price=node["bid"],
            gross_pct=gross, net_pct=net,
        ))

    opps.sort(key=lambda o: o.net_pct, reverse=True)
    return opps


# ─────────────────────────────────────────────────────────────────────────────
# Frente B
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class OppB:
    front: str          # siempre "B"
    mode: str           # spot_spot | p2p_p2p | spot_p2p | same_brand
    label: str          # ej. "Binance → El Dorado P2P"
    buy_where: str
    sell_where: str
    buy_type: str       # spot | p2p
    sell_type: str
    buy_price: float
    sell_price: float
    gross_pct: float
    net_pct: float

    def to_dict(self) -> dict:
        return asdict(self)


_MODE_LABELS = {
    "spot_spot": "Spot ↔ Spot",
    "p2p_p2p": "P2P ↔ P2P",
    "spot_p2p": "Spot ↔ P2P",
    "same_brand": "Misma plataforma",
}


def _make_opp_b(mode: str, buy: tuple[str, dict], sell: tuple[str, dict],
                extra_overrides: dict[str, float] | None) -> OppB:
    bp, bq = buy
    sp, sq = sell
    gross = (sq["bid"] - bq["ask"]) / bq["ask"] * 100
    net = (sq["totalBid"] - bq["totalAsk"]) / bq["totalAsk"] * 100
    net -= platforms.extra_fee_pct(bp, extra_overrides)
    net -= platforms.extra_fee_pct(sp, extra_overrides)
    return OppB(
        front="B", mode=mode,
        label=f"{platforms.label(bp)} → {platforms.label(sp)}",
        buy_where=platforms.label(bp), sell_where=platforms.label(sp),
        buy_type=bq["type"], sell_type=sq["type"],
        buy_price=bq["totalAsk"], sell_price=sq["totalBid"],
        gross_pct=gross, net_pct=net,
    )


def scan_front_b(
    crypto: dict[str, dict],
    modes: list[str],
    extra_overrides: dict[str, float] | None = None,
    top_per_mode: int = 10,
) -> list[OppB]:
    """Genera oportunidades cripto↔cripto para las modalidades pedidas.

    Para cada par (comprar, vender) con comprar≠vender calcula el spread; ordena
    por neto y conserva las mejores `top_per_mode` de cada modalidad.
    """
    items = list(crypto.items())
    spots = [(p, q) for p, q in items if q["type"] == "spot"]
    p2ps = [(p, q) for p, q in items if q["type"] == "p2p"]

    out: list[OppB] = []

    def cross(mode: str, buy_set, sell_set, predicate):
        opps = []
        for bp, bq in buy_set:
            for sp, sq in sell_set:
                if bp == sp:
                    continue
                if not predicate(bp, sp):
                    continue
                opps.append(_make_opp_b(mode, (bp, bq), (sp, sq), extra_overrides))
        opps.sort(key=lambda o: o.net_pct, reverse=True)
        out.extend(opps[:top_per_mode])

    if "spot_spot" in modes:
        cross("spot_spot", spots, spots, lambda b, s: True)
    if "p2p_p2p" in modes:
        cross("p2p_p2p", p2ps, p2ps, lambda b, s: True)
    if "spot_p2p" in modes:
        # cruzado en ambas direcciones (comprar spot/vender p2p y viceversa)
        cross("spot_p2p", items, items,
              lambda b, s: platforms.platform_type(b) != platforms.platform_type(s))
    if "same_brand" in modes:
        cross("same_brand", items, items,
              lambda b, s: platforms.brand(b) == platforms.brand(s))

    out.sort(key=lambda o: o.net_pct, reverse=True)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Filtro de oportunidades
# ─────────────────────────────────────────────────────────────────────────────
def find_opportunities(opps: list, threshold_pct: float) -> list:
    """Filtra las oportunidades cuya ganancia neta supera el umbral."""
    return [o for o in opps if o.net_pct >= threshold_pct]
