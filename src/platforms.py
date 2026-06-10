"""Metadata de plataformas USDT/ARS y comisiones extra opcionales.

Importante: CriptoYa ya devuelve `totalAsk`/`totalBid` **netos de la comisión de
la plataforma**, así que el grueso del cálculo de comisiones ya viene resuelto.
`EXTRA_FEES_PCT` permite descontar costos que la API NO incluye (ej. costo de
transferencia bancaria/CBU para mover pesos hacia/desde el dólar tradicional).
"""

from __future__ import annotations

# Etiquetas legibles. Si una plataforma no figura, se usa su id capitalizado.
PLATFORM_LABELS: dict[str, str] = {
    "binance": "Binance",
    "binancep2p": "Binance P2P",
    "buenbit": "Buenbit",
    "ripio": "Ripio",
    "ripioexchange": "Ripio Exchange",
    "lemoncash": "Lemon",
    "lemoncashp2p": "Lemon P2P",
    "belo": "Belo",
    "fiwind": "Fiwind",
    "letsbit": "Lets Bit",
    "satoshitango": "SatoshiTango",
    "tiendacrypto": "Tienda Crypto",
    "cocoscrypto": "Cocos Crypto",
    "decrypto": "Decrypto",
    "bitsoalpha": "Bitso",
    "universalcoins": "Universal Coins",
    "saldo": "Saldo",
    "astropay": "Astropay",
    "vitawallet": "Vita Wallet",
    "pluscrypto": "Plus Crypto",
    "cryptomktpro": "CryptoMarket Pro",
    "eluter": "Eluter",
    "bybit": "Bybit",
    "bybitp2p": "Bybit P2P",
    "okexp2p": "OKX P2P",
    "kucoinp2p": "KuCoin P2P",
    "bitgetp2p": "Bitget P2P",
    "bingxp2p": "BingX P2P",
    "huobip2p": "HTX P2P",
    "coinexp2p": "CoinEx P2P",
    "eldoradop2p": "El Dorado P2P",
}

# Comisión extra (en %) por plataforma, NO incluida en totalAsk/totalBid.
# Por defecto 0: la API ya neteó la comisión de trading de la plataforma.
# Overridable vía .env con EXTRA_FEE_<PLATAFORMA>.
EXTRA_FEES_PCT: dict[str, float] = {}


def is_p2p(platform: str) -> bool:
    """Una plataforma es P2P si su id termina en 'p2p'."""
    return platform.lower().endswith("p2p")


def platform_type(platform: str) -> str:
    return "p2p" if is_p2p(platform) else "spot"


def label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform.lower(), platform.capitalize())


def brand(platform: str) -> str:
    """Marca base (sin sufijo p2p) para detectar spot vs p2p de la misma marca."""
    p = platform.lower()
    return p[:-3] if p.endswith("p2p") else p


def extra_fee_pct(platform: str, overrides: dict[str, float] | None = None) -> float:
    if overrides and platform in overrides:
        return overrides[platform]
    return EXTRA_FEES_PCT.get(platform, 0.0)
