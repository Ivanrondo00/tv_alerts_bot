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
TELEGRAM_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET    = os.environ.get("WEBHOOK_SECRET", "")
PRICE_BAND_PCT    = float(os.environ.get("PRICE_BAND_PCT", "1.0"))

FAMILY_EMOJIS = {
    "crypto":      "🪙",
    "forex":       "💱",
    "acciones":    "📈",
    "stocks":      "📈",
    "indices":     "📊",
    "materias":    "🛢️",
    "commodities": "🛢️",
    "etf":         "🗂️",
}

def get_family_emoji(family: str) -> str:
    return FAMILY_EMOJIS.get(family.lower(), "📁")

def format_price(price: float) -> str:
    if price >= 1000:
        return f"{price:,.2f}"
    elif price >= 1:
        return f"{price:.4f}"
    else:
        return f"{price:.6f}"

def format_alert(data: dict) -> str:
    family   = data.get("family",   "General")
    asset    = data.get("asset",    "Desconocido")
    interval = data.get("interval", "N/A")
    strategy = data.get("strategy", "Sin estrategia")
    action   = str(data.get("action", "INFO")).upper()
    message  = data.get("message",  "")
    timestamp = datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")

    try:
        price = float(data.get("price", 0))
    except (ValueError, TypeError):
        price = 0.0

    if action in ("BUY", "LONG", "COMPRA"):
        action_line = "🟢 COMPRA / LONG"
        band_low    = price * (1 - PRICE_BAND_PCT / 100)
        band_line   = f"📊 Zona de entrada: {format_price(band_low)} → {format_price(price)}"
    elif action in ("SELL", "SHORT", "VENTA"):
        action_line = "🔴 VENTA / SHORT"
        band_high   = price * (1 + PRICE_BAND_PCT / 100)
        band_line   = f"📊 Zona de entrada: {format_price(price)} → {format_price(band_high)}"
    elif action in ("CLOSE", "CERRAR"):
        action_line = "⬛ CERRAR POSICION"
        band_line   = ""
    else:
        action_line = f"ℹ️ {action}"
        band_low    = price * (1 - PRICE_BAND_PCT / 100)
        band_high   = price * (1 + PRICE_BAND_PCT / 100)
        band_line   = f"📊 Rango: {format_price(band_low)} → {format_price(band_high)}"

    family_emoji = get_family_emoji(family)

    lines = [
        f"🔔 ALERTA TRADING — {timestamp}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"{family_emoji} Familia:   {family}",
        f"💎 Activo:    {asset}",
        f"⏱ Intervalo: {interval}",
        f"🧠 Estrategia: {strategy}",
        "━━━━━━━━━━━━━━━━━━━━",
        action_line,
        f"💰 Precio señal: {format_price(price)}",
    ]

    if band_line:
        lines.append(band_line)
        lines.append(f"(+/- {PRICE_BAND_PCT}% del precio señal)")

    if message:
        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━",
            f"📝 {message}",
        ])

    return "\n".join(lines)


def send_telegram_message(text: str, chat_id: str = None) -> dict:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id or TELEGRAM_CHAT_ID,
        "text":    text,
    }
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Bot activo"}), 200


@app.route("/webhook", methods=["POST"])
def webhook():
    if WEBHOOK_SECRET:
        secret = request.headers.get("X-Webhook-Secret", "")
        if secret != WEBHOOK_SECRET:
            return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True)
    if not data:
        try:
            data = json.loads(request.data.decode("utf-8"))
        except Exception:
            return jsonify({"error": "JSON invalido"}), 400

    logger.info(f"Alerta recibida: {json.dumps(data, ensure_ascii=False)}")
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
    sample = {
        "family":   "Crypto",
        "asset":    "BTCUSDT",
        "interval": "4h",
        "strategy": "EMA Cross 20/50",
        "action":   "BUY",
        "price":    65000.50,
        "message":  "Cruce alcista confirmado. TP1: 68000 | TP2: 72000 | SL: 63000",
    }
    try:
        text   = format_alert(sample)
        result = send_telegram_message(text)
        return jsonify({"ok": True, "telegram": result}), 200
    except Exception as e:
        logger.error(f"Error en test: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
