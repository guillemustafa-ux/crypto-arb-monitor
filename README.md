# 📡 Monitor de Arbitraje Cambiario Argentino 🇦🇷

Monitor en tiempo real del **arbitraje cambiario** del mercado argentino, con
alertas por Telegram y dashboard web. **Solo monitoreo**: detecta y avisa
oportunidades, **no ejecuta operaciones**.

Usa la API pública de [CriptoYa](https://criptoya.com/api) para cotizaciones del
dólar y de USDT/ARS (spot y P2P).

## ¿Qué compara?

### Frente A — Tradicional vs Cripto
Dólar **oficial / blue / MEP / CCL** contra **USDT/ARS**, en ambas direcciones:
- comprar dólar tradicional → vender USDT
- comprar USDT → vender dólar tradicional

Detecta, por ejemplo, cuándo conviene comprar dólar oficial y venderlo como USDT,
o comprar USDT barato y "salir" por MEP/CCL.

### Frente B — Solo Cripto (USDT/ARS)
Compara cotizaciones de USDT/ARS **entre plataformas** (Binance, Lemon, Belo,
Buenbit, Ripio, Fiwind, SatoshiTango, etc.), tanto exchange/spot como P2P:
- **Spot ↔ Spot** · **P2P ↔ P2P** · **Spot ↔ P2P** · **misma plataforma** (spot vs su propio P2P)

## Comisiones

CriptoYa ya entrega `totalAsk` / `totalBid` **netos de la comisión de trading** de
cada plataforma, así que el spread **neto** ya las contempla. El spread **bruto**
usa `ask` / `bid`. Para costos que la API no incluye (ej. transferencia
bancaria/CBU) se pueden sumar comisiones extra por plataforma vía `EXTRA_FEE_<ID>`
en el `.env`.

## Stack

Python · FastAPI · httpx · SQLite (aiosqlite) · Telegram Bot API · Railway

## Estructura

```
crypto-arb-monitor/
├── main.py                # entrypoint: FastAPI + loop de monitoreo
├── src/
│   ├── config.py          # configuración desde .env
│   ├── criptoya.py        # cliente de la API de CriptoYa
│   ├── platforms.py       # metadata de plataformas + comisiones extra
│   ├── arbitrage.py       # lógica de spreads (Frente A y B)
│   ├── monitor.py         # loop asyncio: consulta, detecta, alerta
│   ├── storage.py         # historial + estado en SQLite
│   ├── telegram.py        # alertas por Telegram
│   └── dashboard.py       # dashboard web + endpoints JSON
├── requirements.txt
├── .env.example
├── railway.json / Procfile
└── README.md
```

## Instalación local

```bash
git clone <repo>
cd crypto-arb-monitor
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # editá los valores
python main.py
```

Abrir **http://localhost:8000**.

## Configuración (`.env`)

| Variable | Descripción | Default |
|---|---|---|
| `COIN` / `FIAT` / `VOLUME` | Par y volumen a consultar | `usdt` / `ars` / `1` |
| `DOLLAR_TYPES` | Dólares del Frente A | `oficial,blue,mep,ccl` |
| `MEP_BOND` / `CCL_BOND` / `BOND_TERM` | Bono/término para MEP y CCL | `al30` / `al30` / `24hs` |
| `B_MODES` | Modalidades del Frente B | las 4 |
| `PLATFORMS` | Whitelist de plataformas (vacío = todas) | _(todas)_ |
| `MIN_NET_PCT_A` / `MIN_NET_PCT_B` | Umbral neto (%) para alertar | `1.0` / `0.5` |
| `POLL_INTERVAL` | Segundos entre consultas | `60` |
| `ALERT_COOLDOWN_MIN` | Anti-spam por ruta (min) | `15` |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Alertas Telegram (opcional) | — |
| `DB_PATH` / `PORT` | SQLite y puerto del dashboard | `./arb.db` / `8000` |
| `EXTRA_FEE_<ID>` | Comisión extra por plataforma (%) | `0` |

### Telegram (opcional)
1. Crear un bot con [@BotFather](https://t.me/BotFather) → copiar el **token**.
2. Enviarle un mensaje al bot, luego abrir
   `https://api.telegram.org/bot<token>/getUpdates` y copiar
   `result[].message.chat.id` → ese es tu **chat_id**.
3. Completar `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` en el `.env`.

## Dashboard

- **Frente A en vivo**: oficial/blue/MEP/CCL vs el mejor USDT/ARS, con spread neto.
- **Mejores spreads** del momento (Frente A y Frente B).
- **USDT/ARS por plataforma** (spot y P2P, bruto y neto).
- **Historial** de oportunidades detectadas.
- Botones **Pausar / Reanudar** (estado persistido en SQLite).

Endpoints JSON: `/api/status`, `/api/dolar`, `/api/crypto`, `/api/frente-a`,
`/api/frente-b`, `/api/opportunities`.

## Deploy en Railway

1. Crear proyecto desde el repo (Railway detecta Python vía Nixpacks; usa
   `Procfile` / `railway.json` → `python main.py`).
2. Cargar las variables del `.env` en **Variables**.
3. Para que el **historial sobreviva** redeploys: agregar un **Volume** montado en
   `/data` y setear `DB_PATH=/data/arb.db`.
4. Railway inyecta `PORT` automáticamente.

## Agregar plataformas o dólares

- **Plataformas**: aparecen solas si CriptoYa las devuelve. Para una etiqueta
  más linda, sumala a `PLATFORM_LABELS` en [`src/platforms.py`](src/platforms.py).
- **Dólares**: sumá la clave a `DOLLAR_TYPES` (debe existir en `/api/dolar`).

## Aviso

Proyecto **educativo / de portfolio**. No es asesoramiento financiero. Verificá
siempre liquidez, límites, tiempos de acreditación y comisiones reales antes de
operar.
