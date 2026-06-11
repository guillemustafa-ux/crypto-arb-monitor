"""Dashboard web FastAPI con estilo dark/verde + endpoints JSON y pausa/reanuda."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from . import platforms
from .monitor import MonitorState

# Zona horaria Argentina (UTC-3) para mostrar fechas.
_AR_TZ = timezone(timedelta(hours=-3))


def _fmt_price(n: float) -> str:
    return f"{n:,.2f}"


def _fmt_dt(ts: float) -> str:
    return datetime.fromtimestamp(ts, _AR_TZ).strftime("%d/%m %H:%M:%S")


def register_routes(app: FastAPI, state: MonitorState) -> None:
    cfg = state.config

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        paused = await state.storage.get_paused()
        today_start = datetime.now(_AR_TZ).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        opps_today = await state.storage.count_opportunities_since(today_start)
        history = await state.storage.recent_opportunities(limit=60)
        return HTMLResponse(_render(state, paused, opps_today, history))

    @app.get("/api/status")
    async def api_status() -> JSONResponse:
        paused = await state.storage.get_paused()
        return JSONResponse({
            "paused": paused,
            "platforms": state.active_platforms,
            "dollar_types": cfg.dollar_types,
            "b_modes": cfg.b_modes,
            "poll_interval": cfg.poll_interval,
            "min_net_pct_a": cfg.min_net_pct_a,
            "min_net_pct_b": cfg.min_net_pct_b,
            "telegram_enabled": cfg.telegram_enabled,
            "last_update": state.last_update,
            "last_error": state.last_error,
        })

    @app.get("/api/dolar")
    async def api_dolar() -> JSONResponse:
        return JSONResponse({"last_update": state.last_update, "dolar": state.dolar})

    @app.get("/api/crypto")
    async def api_crypto() -> JSONResponse:
        return JSONResponse({"last_update": state.last_update, "crypto": state.crypto})

    @app.get("/api/frente-a")
    async def api_frente_a() -> JSONResponse:
        return JSONResponse({"last_update": state.last_update,
                             "opportunities": [o.to_dict() for o in state.opps_a]})

    @app.get("/api/frente-b")
    async def api_frente_b() -> JSONResponse:
        return JSONResponse({"last_update": state.last_update,
                             "opportunities": [o.to_dict() for o in state.opps_b]})

    @app.get("/api/opportunities")
    async def api_opportunities() -> JSONResponse:
        history = await state.storage.recent_opportunities(limit=100)
        return JSONResponse({"opportunities": history})

    @app.post("/pause")
    async def pause() -> JSONResponse:
        await state.storage.set_paused(True)
        return JSONResponse({"ok": True, "paused": True})

    @app.post("/resume")
    async def resume() -> JSONResponse:
        await state.storage.set_paused(False)
        return JSONResponse({"ok": True, "paused": False})


# ── Render de filas ──────────────────────────────────────────────────────────

def _cls(pct: float, threshold: float) -> str:
    if pct >= threshold:
        return "pos"
    if pct < 0:
        return "neg"
    return "neutral"


def _best_crypto(crypto: dict) -> tuple[dict | None, dict | None]:
    """Mejor para comprar (menor totalAsk) y para vender (mayor totalBid)."""
    if not crypto:
        return None, None
    buy = min(crypto.items(), key=lambda kv: kv[1]["totalAsk"])
    sell = max(crypto.items(), key=lambda kv: kv[1]["totalBid"])
    return ({"plat": buy[0], **buy[1]}, {"plat": sell[0], **sell[1]})


def _frente_a_table(state: MonitorState) -> str:
    """Tabla en vivo: cada dólar tradicional vs el mejor USDT/ARS."""
    dolar, crypto = state.dolar, state.crypto
    if not dolar or not crypto:
        return ('<tr><td colspan="6" style="text-align:center;color:#666">'
                'Esperando primer ciclo de datos…</td></tr>')
    best_buy, best_sell = _best_crypto(crypto)
    th = state.config.min_net_pct_a
    rows = []
    for tipo in state.config.dollar_types:
        node = dolar.get(tipo)
        if not node:
            continue
        # Mejor de las dos rutas para este dólar.
        sell_net = (best_sell["totalBid"] - node["ask"]) / node["ask"] * 100
        buy_net = (node["bid"] - best_buy["totalAsk"]) / best_buy["totalAsk"] * 100
        if sell_net >= buy_net:
            route = f'Comprar {node["label"]} → vender {platforms.label(best_sell["plat"])}'
            net = sell_net
        else:
            route = f'Comprar {platforms.label(best_buy["plat"])} → vender {node["label"]}'
            net = buy_net
        rows.append(f"""
      <tr>
        <td><b>{node['label']}</b></td>
        <td>${_fmt_price(node['ask'])}</td>
        <td>${_fmt_price(node['bid'])}</td>
        <td style="color:#888">{route}</td>
        <td class="{_cls(net, th)}"><b>{net:+.2f}%</b></td>
      </tr>""")
    return "".join(rows)


def _crypto_table(state: MonitorState) -> str:
    crypto = state.crypto
    if not crypto:
        return ('<tr><td colspan="5" style="text-align:center;color:#666">'
                'Esperando datos de plataformas…</td></tr>')
    rows = []
    for plat, q in sorted(crypto.items(), key=lambda kv: kv[1]["totalAsk"]):
        badge = "p2p" if q["type"] == "p2p" else "spot"
        badge_cls = "tag-p2p" if q["type"] == "p2p" else "tag-spot"
        rows.append(f"""
      <tr>
        <td><b>{platforms.label(plat)}</b> <span class="badge {badge_cls}">{badge}</span></td>
        <td>${_fmt_price(q['ask'])}</td>
        <td>${_fmt_price(q['bid'])}</td>
        <td style="color:#888">${_fmt_price(q['totalAsk'])}</td>
        <td style="color:#888">${_fmt_price(q['totalBid'])}</td>
      </tr>""")
    return "".join(rows)


def _opp_rows(opps: list, threshold: float, limit: int = 8) -> str:
    # Solo se muestran oportunidades cuya ganancia neta supera el umbral.
    shown = [o for o in opps if o.net_pct >= threshold]
    if not shown:
        return ('<tr><td colspan="3" style="text-align:center;color:#666">'
                f'Sin oportunidades ≥ {threshold:.2f}% en este momento</td></tr>')
    rows = []
    for o in shown[:limit]:
        rows.append(f"""
      <tr>
        <td>{o.label}</td>
        <td class="{_cls(o.gross_pct, 0)}">{o.gross_pct:+.2f}%</td>
        <td class="{_cls(o.net_pct, threshold)}"><b>{o.net_pct:+.2f}%</b></td>
      </tr>""")
    return "".join(rows)


def _history_rows(history: list[dict]) -> str:
    if not history:
        return ('<tr><td colspan="5" style="text-align:center;color:#666">'
                'Sin oportunidades registradas todavía</td></tr>')
    rows = []
    for o in history:
        front = f'<span class="badge tag-{"a" if o["front"]=="A" else "b"}">Frente {o["front"]}</span>'
        rows.append(f"""
      <tr>
        <td>{_fmt_dt(o['ts'])}</td>
        <td>{front}</td>
        <td>{o['label']}</td>
        <td class="neutral">{o['gross_pct']:+.2f}%</td>
        <td class="pos"><b>{o['net_pct']:+.2f}%</b></td>
      </tr>""")
    return "".join(rows)


# ── Render principal ─────────────────────────────────────────────────────────

def _render(state: MonitorState, paused: bool, opps_today: int, history: list[dict]) -> str:
    cfg = state.config
    status_dot = "🔴" if paused else "🟢"
    status_txt = "PAUSADO" if paused else "ACTIVO"
    best_a = max((o.net_pct for o in state.opps_a), default=0.0)
    best_b = max((o.net_pct for o in state.opps_b), default=0.0)
    updated = _fmt_dt(state.last_update) if state.last_update else "—"
    tg = "✅" if cfg.telegram_enabled else "⚪"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Monitor de Arbitraje Cambiario AR</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0a0a0f;color:#e0e0e0;font-family:'Segoe UI',sans-serif;padding:20px}}
  h1{{font-size:22px;margin-bottom:4px}}
  .sub{{color:#888;font-size:13px;margin-bottom:20px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:24px}}
  .card{{background:#13131a;border:1px solid #222;border-radius:10px;padding:16px}}
  .card .label{{font-size:11px;color:#888;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}}
  .card .val{{font-size:22px;font-weight:700}}
  .pos{{color:#00d88a}}
  .neg{{color:#ff4d4d}}
  .neutral{{color:#aaa}}
  table{{width:100%;border-collapse:collapse;margin-top:8px;font-size:13px}}
  th{{text-align:left;color:#888;font-weight:500;padding:8px 6px;border-bottom:1px solid #222}}
  td{{padding:7px 6px;border-bottom:1px solid #1a1a24}}
  tr:hover td{{background:#15151f}}
  .cols{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
  @media(max-width:820px){{.cols{{grid-template-columns:1fr}}}}
  .section{{background:#13131a;border:1px solid #222;border-radius:10px;padding:16px;margin-bottom:20px}}
  .section h2{{font-size:14px;color:#aaa;margin-bottom:12px;text-transform:uppercase;letter-spacing:1px}}
  .btns{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}}
  button{{padding:9px 18px;border:none;border-radius:8px;cursor:pointer;font-size:13px;font-weight:600}}
  .btn-pause{{background:#f59e0b;color:#000}}
  .btn-resume{{background:#10b981;color:#000}}
  button:hover{{opacity:.85}}
  .tag{{display:inline-block;background:#1a1a24;border:1px solid #222;border-radius:6px;padding:2px 8px;margin:2px;font-size:12px;color:#a78bfa}}
  .badge{{display:inline-block;border-radius:5px;padding:1px 6px;font-size:10px;font-weight:600;text-transform:uppercase;vertical-align:middle}}
  .tag-spot{{background:#0d2a3a;color:#38bdf8}}
  .tag-p2p{{background:#2a1a3a;color:#c084fc}}
  .tag-a{{background:#0d3a2a;color:#34d399}}
  .tag-b{{background:#3a2a0d;color:#fbbf24}}
</style>
</head>
<body>

<h1>📡 Monitor de Arbitraje Cambiario 🇦🇷</h1>
<div class="sub">
  {status_dot} {status_txt} &nbsp;|&nbsp; Solo monitoreo (no ejecuta operaciones)
  &nbsp;|&nbsp; Umbrales: A {cfg.min_net_pct_a:.2f}% · B {cfg.min_net_pct_b:.2f}%
  &nbsp;|&nbsp; Telegram: {tg}
  &nbsp;|&nbsp; Actualizado: {updated} (AR)
</div>

<div class="btns">
  <button class="btn-pause" onclick="postAction('/pause')">⏸ Pausar</button>
  <button class="btn-resume" onclick="postAction('/resume')">▶️ Reanudar</button>
</div>

<div class="grid">
  <div class="card"><div class="label">Estado</div><div class="val">{status_dot} {status_txt}</div></div>
  <div class="card"><div class="label">Plataformas USDT/ARS</div><div class="val">{len(state.active_platforms)}</div></div>
  <div class="card"><div class="label">Oportunidades Hoy</div><div class="val pos">{opps_today}</div></div>
  <div class="card"><div class="label">Mejor Spread Frente A</div><div class="val {_cls(best_a, cfg.min_net_pct_a)}">{best_a:+.2f}%</div></div>
  <div class="card"><div class="label">Mejor Spread Frente B</div><div class="val {_cls(best_b, cfg.min_net_pct_b)}">{best_b:+.2f}%</div></div>
</div>

<div class="section">
  <h2>💵 Frente A — Tradicional vs Cripto (en vivo)</h2>
  <table>
    <tr><th>Dólar</th><th>Compra (ask)</th><th>Venta (bid)</th><th>Mejor ruta vs USDT</th><th>Spread neto</th></tr>
    {_frente_a_table(state)}
  </table>
</div>

<div class="cols">
  <div class="section">
    <h2>🏆 Mejores spreads — Frente A</h2>
    <table>
      <tr><th>Ruta</th><th>Bruto</th><th>Neto</th></tr>
      {_opp_rows(state.opps_a, cfg.min_net_pct_a)}
    </table>
  </div>
  <div class="section">
    <h2>🏆 Mejores spreads — Frente B</h2>
    <table>
      <tr><th>Ruta</th><th>Bruto</th><th>Neto</th></tr>
      {_opp_rows(state.opps_b, cfg.min_net_pct_b)}
    </table>
  </div>
</div>

<div class="section">
  <h2>🪙 USDT/ARS por plataforma (spot y P2P)</h2>
  <table>
    <tr><th>Plataforma</th><th>Ask (bruto)</th><th>Bid (bruto)</th><th>Total Ask (neto)</th><th>Total Bid (neto)</th></tr>
    {_crypto_table(state)}
  </table>
</div>

<div class="section">
  <h2>📜 Historial de Oportunidades</h2>
  <table>
    <tr><th>Fecha (AR)</th><th>Frente</th><th>Ruta</th><th>Bruto</th><th>Neto</th></tr>
    {_history_rows(history)}
  </table>
</div>

<div class="section">
  <h2>🌐 Configuración</h2>
  <p style="color:#aaa;font-size:13px;margin-bottom:8px">Dólares:</p>
  <div>{"".join(f'<span class="tag">{t}</span>' for t in cfg.dollar_types)}</div>
  <p style="color:#aaa;font-size:13px;margin:12px 0 8px">Modos Frente B:</p>
  <div>{"".join(f'<span class="tag">{m}</span>' for m in cfg.b_modes)}</div>
  <p style="color:#aaa;font-size:13px;margin:12px 0 8px">Plataformas activas:</p>
  <div>{"".join(f'<span class="tag">{platforms.label(p)}</span>' for p in state.active_platforms) or '<span style="color:#666">esperando…</span>'}</div>
</div>

<script>
async function postAction(path) {{
  await fetch(path, {{ method: 'POST' }});
  location.reload();
}}
setInterval(() => location.reload(), 20000);
</script>
</body>
</html>"""
