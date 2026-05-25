"""
TradingView → Telegram Alert Bot
"""

import os
import json
import logging
from flask import Flask, request, jsonify
import requests
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET   = os.environ.get("WEBHOOK_SECRET", "")
PRICE_BAND_PCT   = float(os.environ.get("PRICE_BAND_PCT", "1.0"))

def format_price(price: float) -> str:
    if price >= 1000:
        return f"{price:,.2f}"
    elif price >= 1:
        return f"{price:.4f}"
    else:
        return f"{price:.6f}"

def format_alert(data: dict) -> str:
    asset    = data.get("asset",    "Desconocido")
    interval = data.get("interval", "N/A")
    strategy = data.get("strategy", "Sin estrategia")
    action   = str(data.get("action", "INFO")).upper().strip()
    message  = data.get("message",  "")
    timestamp = datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")

    try:
        price = float(data.get("price", 0))
    except (ValueError, TypeError):
        price = 0.0

    band_low  = price * (1 - PRICE_BAND_PCT / 100)
    band_high = price * (1 + PRICE_BAND_PCT / 100)

    if action == "ABRIR LARGO":
        emoji      = "🟢"
        accion_txt = "ABRIR LARGO"
        banda_txt  = f"📊 Zona de entrada: {format_price(band_low)} — {format_price(price)}"
        banda_nota = f"(precio señal o hasta {PRICE_BAND_PCT}% por debajo)"
    elif action == "CERRAR LARGO":
        emoji      = "🔵"
        accion_txt = "CERRAR LARGO"
        banda_txt  = f"📊 Zona de cierre: {format_price(price)} — {format_price(band_high)}"
        banda_nota = f"(precio señal o hasta {PRICE_BAND_PCT}% por encima)"
    elif action == "ABRIR CORTO":
        emoji      = "🔴"
        accion_txt = "ABRIR CORTO"
        banda_txt  = f"📊 Zona de entrada: {format_price(price)} — {format_price(band_high)}"
        banda_nota = f"(precio señal o hasta {PRICE_BAND_PCT}% por encima)"
    elif action == "CERRAR CORTO":
        emoji      = "⚪"
        accion_txt = "CERRAR CORTO"
        banda_txt  = f"📊 Zona de cierre: {format_price(band_low)} — {format_price(price)}"
        banda_nota = f"(precio señal o hasta {PRICE_BAND_PCT}% por debajo)"
    else:
        emoji      = "ℹ️"
        accion_txt = action
        banda_txt  = f"📊 Rango ref.: {format_price(band_low)} — {format_price(band_high)}"
        banda_nota = ""

    lines = [
        f"{emoji} {accion_txt}",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"💎 Activo:     {asset}",
        f"⏱ Intervalo:  {interval}",
        f"🧠 Estrategia: {strategy}",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"💰 Precio señal: {format_price(price)}",
        banda_txt,
        banda_nota,
        f"🕐 {timestamp}",
    ]

    if message:
        lines.insert(-1, f"📝 {message}")

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
    return jsonify({"status": "ok"}), 200


@app.route("/webhook", methods=["POST"])
def webhook():
    if WEBHOOK_SECRET:
        if request.headers.get("X-Webhook-Secret", "") != WEBHOOK_SECRET:
            return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True)
    if not data:
        try:
            data = json.loads(request.data.decode("utf-8"))
        except Exception:
            return jsonify({"error": "JSON invalido"}), 400

    logger.info(f"Alerta: {json.dumps(data, ensure_ascii=False)}")
    chat_id = data.get("chat_id", TELEGRAM_CHAT_ID)

    try:
        text   = format_alert(data)
        result = send_telegram_message(text, chat_id=chat_id)
        return jsonify({"ok": True, "telegram": result}), 200
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


# ── Endpoints de test individuales ────────────────────────────────────────────

def _test(action: str):
    sample = {
        "asset":    "BTCUSDT",
        "interval": "4h",
        "strategy": "Breakout Compresion v1",
        "action":   action,
        "price":    65000.50,
    }
    try:
        text   = format_alert(sample)
        result = send_telegram_message(text)
        return jsonify({"ok": True, "preview": text}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/test/al", methods=["GET"])
def test_al():
    return _test("ABRIR LARGO")

@app.route("/test/cl", methods=["GET"])
def test_cl():
    return _test("CERRAR LARGO")

@app.route("/test/ac", methods=["GET"])
def test_ac():
    return _test("ABRIR CORTO")

@app.route("/test/cc", methods=["GET"])
def test_cc():
    return _test("CERRAR CORTO")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
