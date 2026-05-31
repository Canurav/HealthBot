import os
import json
import asyncio
from datetime import datetime, time
import pytz
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, JobQueue
)
import anthropic

# ── Configuración ──────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
YOUR_CHAT_ID = int(os.environ["YOUR_CHAT_ID"])
TIMEZONE = os.environ.get("TIMEZONE", "Europe/Paris")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

DATA_FILE = "data.json"

SYSTEM_PROMPT = """Sos un asistente de salud personal. Tu usuario se llama Mariano.

CONTEXTO MÉDICO (MUY IMPORTANTE):
- Tiene desprendimiento de retina por neovascularización macular, posible PXE (pseudoxantoma elástico)
- Evitar ejercicios de alto impacto, maniobras de Valsalva, levantamiento de pesos muy pesados (>15kg)
- No recomendar ejercicio de alta intensidad que eleve mucho la presión ocular
- Siempre sugerir ejercicios de bajo-moderado impacto

OBJETIVO:
- Bajar de 87kg a 78kg
- Dieta mediterránea antiinflamatoria
- Come en la cantina del trabajo los días de semana al mediodía
- Cena en familia todas las noches
- Gym aproximadamente 2 veces por semana
- También puede salir a correr

DIETA ANTIINFLAMATORIA - priorizar:
- Pescado azul (salmón, sardinas, caballa), aceite de oliva, nueces
- Verduras de hoja verde, brócoli, espinaca
- Frutos rojos, cúrcuma, jengibre, té verde
- Legumbres, cereales integrales
- Evitar: azúcar refinada, harinas blancas, frituras, alcohol en exceso, carnes procesadas

ESTILO DE RESPUESTA:
- Respuestas concisas y prácticas
- En español rioplatense (vos, etc.)
- Si habla de síntomas oculares nuevos, recordarle que consulte al oftalmólogo
- Para preguntas sobre ejercicio, siempre considerar la restricción ocular
- Máximo 3-4 opciones cuando sugieras comidas o ejercicios"""


# ── Persistencia de datos ──────────────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"peso_history": [], "conversation_history": [], "last_check_in": None}


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Llamada a Claude ───────────────────────────────────────────────────────────
def ask_claude(user_message: str, history: list) -> str:
    messages = history[-10:] + [{"role": "user", "content": user_message}]
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=messages
    )
    return response.content[0].text


# ── Teclado rápido ─────────────────────────────────────────────────────────────
def main_keyboard():
    keyboard = [
        [KeyboardButton("⚖️ Registrar peso"), KeyboardButton("🥗 ¿Qué como hoy?")],
        [KeyboardButton("💪 Rutina de gym"), KeyboardButton("🏃 Salir a correr")],
        [KeyboardButton("📊 Mi progreso"), KeyboardButton("📋 Check-in semanal")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ── Comandos ───────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Hola Mariano! 👋 Soy tu asistente de salud.\n\n"
        "Podés escribirme lo que quieras o usar los botones rápidos.",
        reply_markup=main_keyboard()
    )


async def cmd_peso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¿Cuánto pesás hoy? (escribí solo el número, ej: 86.5)"
    )
    context.user_data["esperando_peso"] = True


async def cmd_progreso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    history = data.get("peso_history", [])
    if not history:
        await update.message.reply_text("Todavía no registraste ningún peso. Usá ⚖️ Registrar peso para empezar.")
        return

    ultimo = history[-1]
    inicio = history[0]["peso"]
    actual = ultimo["peso"]
    bajado = inicio - actual
    falta = actual - 78.0

    lines = [f"📊 *Tu progreso*\n"]
    lines.append(f"Peso actual: *{actual} kg*")
    lines.append(f"Bajaste: *{bajado:.1f} kg* desde que empezaste ({inicio} kg)")
    lines.append(f"Te faltan: *{falta:.1f} kg* para llegar a 78 kg")

    if len(history) >= 2:
        anterior = history[-2]["peso"]
        diff = actual - anterior
        emoji = "📉" if diff < 0 else "📈" if diff > 0 else "➡️"
        lines.append(f"Vs. medición anterior: {emoji} {diff:+.1f} kg")

    lines.append(f"\n_Últimas mediciones:_")
    for entry in history[-5:]:
        lines.append(f"  {entry['fecha']}: {entry['peso']} kg")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *Check-in semanal*\n\n"
        "Contame cómo fue la semana. Podés incluir:\n"
        "• Peso actual\n"
        "• Cuántas veces fuiste al gym / corriste\n"
        "• Cómo estuvo la dieta (del 1 al 5)\n"
        "• Cómo te sentiste (energía, sueño, etc.)\n\n"
        "Escribilo en lenguaje natural, yo lo analizo.",
        parse_mode="Markdown"
    )


# ── Manejador de mensajes de texto ────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    data = load_data()

    # Registrar peso numérico
    if context.user_data.get("esperando_peso") or text.replace(".", "").replace(",", "").isdigit():
        try:
            peso = float(text.replace(",", "."))
            if 40 < peso < 200:
                entry = {
                    "fecha": datetime.now(pytz.timezone(TIMEZONE)).strftime("%d/%m/%Y"),
                    "peso": peso
                }
                data["peso_history"].append(entry)
                save_data(data)
                context.user_data["esperando_peso"] = False

                falta = peso - 78.0
                msg = f"✅ Peso registrado: *{peso} kg*\nTe faltan *{falta:.1f} kg* para tu objetivo."
                await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())
                return
        except ValueError:
            pass

    # Botones rápidos → convertir a mensaje natural
    quick_map = {
        "⚖️ Registrar peso": "Quiero registrar mi peso de hoy",
        "🥗 ¿Qué como hoy?": "¿Qué me recomendás comer hoy? Desayuno, almuerzo en cantina y cena. Dieta mediterránea antiinflamatoria.",
        "💪 Rutina de gym": "Dame una rutina de gym para hoy, considerando mi restricción ocular.",
        "🏃 Salir a correr": "Voy a salir a correr, ¿qué me recomendás en cuanto a distancia, ritmo y calentamiento?",
        "📊 Mi progreso": None,
        "📋 Check-in semanal": None,
    }

    if text == "⚖️ Registrar peso":
        context.user_data["esperando_peso"] = True
        await update.message.reply_text("¿Cuánto pesás hoy? (ej: 86.5)")
        return
    if text == "📊 Mi progreso":
        await cmd_progreso(update, context)
        return
    if text == "📋 Check-in semanal":
        await cmd_checkin(update, context)
        return

    prompt = quick_map.get(text, text)

    # Llamada a Claude
    await update.message.chat.send_action("typing")
    history = data.get("conversation_history", [])
    response = ask_claude(prompt, history)

    # Guardar en historial (máximo 20 turnos)
    history.append({"role": "user", "content": prompt})
    history.append({"role": "assistant", "content": response})
    data["conversation_history"] = history[-20:]
    save_data(data)

    await update.message.reply_text(response, reply_markup=main_keyboard())


# ── Recordatorios automáticos ─────────────────────────────────────────────────
async def recordatorio_peso_lunes(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=YOUR_CHAT_ID,
        text="⚖️ *Check-in del lunes*\n\n¿Cuánto pesás hoy? Pesate en ayunas y registrá tu peso.",
        parse_mode="Markdown"
    )


async def recordatorio_desayuno(context: ContextTypes.DEFAULT_TYPE):
    tz = pytz.timezone(TIMEZONE)
    hoy = datetime.now(tz)
    dia = hoy.weekday()  # 0=lunes, 6=domingo
    es_finde = dia >= 5

    if es_finde:
        msg = "🌅 *Buenos días*\nEs fin de semana — buena oportunidad para un desayuno mediterráneo completo: huevos + tostada integral + aceite de oliva + fruta."
    else:
        msg = "🌅 *Buenos días*\nRecordá empezar bien: yogur natural + frutos rojos + nueces, o avena con canela y manzana. Evitá el azúcar refinada."
    await context.bot.send_message(chat_id=YOUR_CHAT_ID, text=msg, parse_mode="Markdown")


async def recordatorio_almuerzo(context: ContextTypes.DEFAULT_TYPE):
    tz = pytz.timezone(TIMEZONE)
    hoy = datetime.now(tz)
    dia = hoy.weekday()
    if dia < 5:  # solo días de semana
        await context.bot.send_message(
            chat_id=YOUR_CHAT_ID,
            text="🍽️ *Almuerzo en la cantina*\nOpciones antiinflamatorias: pescado > pollo > legumbres. Priorizá verduras, evitá frituras y harinas blancas. Agua o té verde.",
            parse_mode="Markdown"
        )


async def recordatorio_cena(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=YOUR_CHAT_ID,
        text="🌙 *Hora de cenar*\nRecordá: proteína magra o legumbres, verduras, aceite de oliva. Cena liviana si ya almorzaste abundante.",
        parse_mode="Markdown"
    )


async def recordatorio_gym(context: ContextTypes.DEFAULT_TYPE):
    tz = pytz.timezone(TIMEZONE)
    dia = tz.localize(datetime.now()).weekday()
    # Sugerir gym martes y jueves
    if dia in [1, 3]:
        await context.bot.send_message(
            chat_id=YOUR_CHAT_ID,
            text="💪 *¿Vas al gym hoy?*\nSi podés, es un buen día. Recordá ejercicios de bajo impacto y sin maniobras de Valsalva. Escribime 'Rutina de gym' y te armo una.",
            parse_mode="Markdown"
        )


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("peso", cmd_peso))
    app.add_handler(CommandHandler("progreso", cmd_progreso))
    app.add_handler(CommandHandler("checkin", cmd_checkin))

    # Mensajes de texto
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Programar recordatorios
    tz = pytz.timezone(TIMEZONE)
    jq = app.job_queue

    # Lunes 8:00 → check-in de peso
    jq.run_daily(recordatorio_peso_lunes, time=time(8, 0, tzinfo=tz), days=(0,))

    # Todos los días 8:00 → desayuno
    jq.run_daily(recordatorio_desayuno, time=time(8, 0, tzinfo=tz))

    # Días de semana 12:30 → almuerzo
    jq.run_daily(recordatorio_almuerzo, time=time(12, 30, tzinfo=tz), days=(0, 1, 2, 3, 4))

    # Todos los días 20:00 → cena
    jq.run_daily(recordatorio_cena, time=time(20, 0, tzinfo=tz))

    # Martes y jueves 17:30 → gym
    jq.run_daily(recordatorio_gym, time=time(17, 30, tzinfo=tz), days=(1, 3))

    print("Bot iniciado ✅")
    app.run_polling()


if __name__ == "__main__":
    main()
