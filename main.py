"""
TradingView → Telegram Alert Bot
Recibe webhooks de TradingView y los formatea y envía a Telegram.
"""

import os
import json
import logging
from flask import Flask, request, jsonify
import requests
from datetime import datetime

# ─── Configuración ────────────────────────────────────────────────────────────
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")   # Canal o chat principal
WEBHOOK_SECRET    = os.environ.get("WEBHOOK_SECRET", "")     # Clave secreta opcional para validar
PRICE_BAND_PCT    = float(os.environ.get("PRICE_BAND_PCT", "1.0"))  # % banda de precios (por defecto 1%)

# Mapeo de familias a emojis
FAMILY_EMOJIS = {
    "crypto":     "🪙",
    "forex":      "💱",
    "acciones":   "📈",
    "stocks":     "📈",
    "indices":    "📊",
    "materias":   "🛢️",
    "commodities": "🛢️",
    "etf":        "🗂️",
}

# ─── Lógica de formato ────────────────────────────────────────────────────────

def get_family_emoji(family: str) -> str:
    return FAMILY_EMOJIS.get(family.lower(), "📁")

def format_price(price: float) -> str:
    """Formatea precio: muestra decimales apropiados según magnitud."""
    if price >= 1000:
        return f"{price:,.2f}"
    elif price >= 1:
        return f"{price:.4f}"
    else:
        return f"{price:.6f}"

def format_alert(data: dict) -> str:
    """
    Convierte el JSON de TradingView en un mensaje Telegram formateado.

    JSON esperado de TradingView:
    {
        "family":    "Crypto",
        "asset":     "BTCUSDT",
        "interval":  "1h",
        "strategy":  "EMA Cross 20/50",
        "action":    "BUY",          // BUY | SELL | LONG | SHORT | CLOSE
        "price":     65000.50,
        "message":   "Cruce alcista detectado, stop en 63000"
    }
    """
    family   = data.get("family",   "General")
    asset    = data.get("asset",    "Desconocido")
    interval = data.get("interval", "N/A")
    strategy = data.get("strategy", "Sin estrategia")
    action   = str(data.get("action", "INFO")).upper()
    message  = data.get("message",  "")
    timestamp = datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")

    # Precio
    try:
        price = float(data.get("price", 0))
    except (ValueError, TypeError):
        price = 0.0

    # Emoji y texto de acción
    if action in ("BUY", "LONG", "COMPRA"):
        action_line = "🟢 *COMPRA / LONG*"
        band_low    = price * (1 - PRICE_BAND_PCT / 100)
        band_high   = price
        band_label  = "Zona de entrada"
        band_line   = f"📊 *{band_label}:* `{format_price(band_low)}` → `{format_price(band_high)}`"
    elif action in ("SELL", "SHORT", "VENTA"):
        action_line = "🔴 *VENTA / SHORT*"
        band_low    = price
        band_high   = price * (1 + PRICE_BAND_PCT / 100)
        band_label  = "Zona de entrada"
        band_line   = f"📊 *{band_label}:* `{format_price(band_low)}` → `{format_price(band_high)}`"
    elif action in ("CLOSE", "CERRAR"):
        action_line = "⬛ *CERRAR POSICIÓN*"
        band_line   = ""
    else:
        action_line = f"ℹ️ *{action}*"
        band_low    = price * (1 - PRICE_BAND_PCT / 100)
        band_high   = price * (1 + PRICE_BAND_PCT / 100)
        band_line   = f"📊 *Rango referencia:* `{format_price(band_low)}` → `{format_price(band_high)}`"

    family_emoji = get_family_emoji(family)

    # Construir mensaje
    lines = [
        f"🔔 *ALERTA TRADING* — {timestamp}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"{family_emoji} *Familia:* `{family}`",
        f"💎 *Activo:*   `{asset}`",
        f"⏱️ *Intervalo:* `{interval}`",
        f"🧠 *Estrategia:* {strategy}",
        "━━━━━━━━━━━━━━━━━━━━",
        action_line,
        f"💰 *Precio señal:* `{format_price(price)}`",
    ]

    if band_line:
        lines.append(band_line)
        lines.append(f"_\\(±{PRICE_BAND_PCT}% del precio señal\\)_")

    if message:
        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━",
            f"📝 {message}",
        ])

    return "\n".join(lines)


# ─── Telegram ─────────────────────────────────────────────────────────────────

def send_telegram_message(text: str, chat_id: str = None, parse_mode: str = "MarkdownV2") -> dict:
    """Envía un mensaje al bot de Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id":    chat_id or TELEGRAM_CHAT_ID,
        "text":       text,
        "parse_mode": parse_mode,
    }
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Bot activo ✅"}), 200


@app.route("/webhook", methods=["POST"])
def webhook():
    # Validación opcional de clave secreta
    if WEBHOOK_SECRET:
        secret = request.headers.get("X-Webhook-Secret", "")
        if secret != WEBHOOK_SECRET:
            logger.warning("Webhook recibido con clave inválida.")
            return jsonify({"error": "Unauthorized"}), 401

    # Parsear JSON
    data = request.get_json(silent=True)
    if not data:
        # TradingView a veces envía texto plano; intentar parsearlo
        try:
            data = json.loads(request.data.decode("utf-8"))
        except Exception:
            return jsonify({"error": "JSON inválido"}), 400

    logger.info(f"Alerta recibida: {json.dumps(data, ensure_ascii=False)}")

    # Destino: puede venir en el payload o usar el default
    chat_id = data.get("chat_id", TELEGRAM_CHAT_ID)

    try:
        text   = format_alert(data)
        result = send_telegram_message(text, chat_id=chat_id)
        return jsonify({"ok": True, "telegram": result}), 200
    except Exception as e:
        logger.error(f"Error enviando a Telegram: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/test", methods=["GET"])
def test_alert():
    """Endpoint de prueba — envía una alerta de ejemplo."""
    sample = {
        "family":   "Crypto",
        "asset":    "BTCUSDT",
        "interval": "4h",
        "strategy": "EMA Cross 20/50",
        "action":   "BUY",
        "price":    65000.50,
        "message":  "Cruce alcista confirmado. Stop loss sugerido: 63.000. TP1: 68.000 | TP2: 72.000",
    }
    text   = format_alert(sample)
    result = send_telegram_message(text)
    return jsonify({"ok": True, "preview": text, "telegram": result}), 200


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
