import os
import json
import asyncio
import random
from datetime import datetime, time, date
import pytz
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)
import anthropic
import gspread
from google.oauth2.service_account import Credentials

# ── Config ─────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
YOUR_CHAT_ID     = int(os.environ["YOUR_CHAT_ID"])
TIMEZONE         = os.environ.get("TIMEZONE", "Europe/Paris")
SPREADSHEET_ID   = os.environ.get("SPREADSHEET_ID", "")  # ID del Google Sheet

# Google Sheets setup
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

def get_sheets_client():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    if not creds_json:
        print("Sheets: GOOGLE_CREDENTIALS_JSON no está configurado")
        return None
    print(f"Sheets: JSON cargado, longitud={len(creds_json)} chars, empieza con: {creds_json[:30]}")
    try:
        creds_data = json.loads(creds_json)
        print(f"Sheets: JSON parseado OK, client_email={creds_data.get('client_email','?')}")
        creds = Credentials.from_service_account_info(creds_data, scopes=SCOPES)
        gc = gspread.authorize(creds)
        print("Sheets: autenticación exitosa ✅")
        return gc
    except json.JSONDecodeError as e:
        print(f"Sheets: JSON inválido — {e}")
        print(f"Sheets: primeros 100 chars: {repr(creds_json[:100])}")
        return None
    except Exception as e:
        print(f"Sheets: error de autenticación — {e}")
        return None

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
DATA_FILE = "data.json"

SYSTEM_PROMPT = """Sos un asistente de salud personal. Tu usuario se llama Mariano.

DATOS PERSONALES:
- Nombre: Mariano
- Edad: 45 años
- Altura: 1.77 m
- Peso inicial: 87 kg → Objetivo: 78 kg
- IMC actual (87kg): 27.8 (sobrepeso leve) → IMC objetivo (78kg): 24.9 (normal)
- Requerimiento calórico estimado (TDEE): ~2400 kcal/día actividad moderada
- Objetivo calórico para bajar: ~2000-2100 kcal/día (déficit 300-400 kcal)
- Proteína objetivo: ~130-140g/día (1.6g x kg peso objetivo)

CONTEXTO MÉDICO (MUY IMPORTANTE):
- Tiene desprendimiento de retina por neovascularización macular, posible PXE (pseudoxantoma elástico)
- Evitar ejercicios de alto impacto, maniobras de Valsalva, levantamiento de pesos >15kg
- No recomendar HIIT, sprints, ni ejercicio que eleve mucho la presión intraocular
- Ejercicios seguros: caminata, trote suave, bicicleta, natación, máquinas con peso moderado, pilates

OBJETIVO:
- Bajar de 87kg a 78kg (déficit calórico ~300-400 kcal/día)
- Dieta mediterránea antiinflamatoria
- Come en la cantina del trabajo los días de semana al mediodía (12:00)
- Cena en familia todas las noches a las 20:00
- Gym los martes y jueves al mediodía (~12:00)
- También puede salir a correr (trote suave)

DIETA ANTIINFLAMATORIA — priorizar:
- Pescado azul (salmón, sardinas, caballa, atún), aceite de oliva extra virgen, nueces
- Verduras de hoja verde, brócoli, espinaca, tomate, pimiento, zanahoria
- Frutos rojos, naranja, manzana · Cúrcuma, jengibre, ajo
- Legumbres, cereales integrales, arroz integral, quínoa
- Evitar: azúcar refinada, harinas blancas, frituras, embutidos, alcohol en exceso

CUANDO TENÉS DATOS DE HUME (composición corporal):
- Si el % de grasa baja pero el peso no → bien, estás perdiendo grasa y ganando músculo
- Si la masa muscular baja → aumentar proteína (objetivo: ~1.6g/kg/día = ~139g/día)
- Si la grasa visceral es alta → priorizar déficit calórico y ejercicio cardiovascular suave
- Usar estos datos para ajustar recomendaciones de forma precisa

ESTILO: español rioplatense, respuestas concretas máximo 250 palabras."""

RUTINAS_GYM = [
    {"nombre": "Rutina A — Tren superior", "ejercicios": [
        ("Bicicleta estática suave", "10 min calentamiento"),
        ("Press de pecho en máquina", "3×12 — peso moderado, exhalar al empujar"),
        ("Remo en polea baja", "3×12 — no retener el aliento"),
        ("Hombros con mancuernas sentado", "3×12 — máx 6-8 kg"),
        ("Curl de bíceps en máquina", "3×15"),
        ("Tríceps en polea", "3×15"),
        ("Plancha frontal", "3×30 seg — respirar normal"),
        ("Caminata + estiramiento", "10 min vuelta calma"),
    ]},
    {"nombre": "Rutina B — Tren inferior", "ejercicios": [
        ("Caminata en cinta 5km/h", "10 min calentamiento"),
        ("Prensa de piernas en máquina", "3×12 — exhalar al empujar"),
        ("Extensión de cuádriceps", "3×15"),
        ("Curl de isquiotibiales", "3×15"),
        ("Abductores en máquina", "3×15"),
        ("Elevación de talones sentado", "3×20"),
        ("Plancha lateral", "3×20 seg c/lado"),
        ("Estiramiento cadena posterior", "8 min"),
    ]},
    {"nombre": "Rutina C — Full body", "ejercicios": [
        ("Bicicleta o caminata suave", "8 min"),
        ("Sentadilla en Smith (peso mínimo)", "3×12 — exhalar al subir"),
        ("Remo con mancuerna apoyado", "3×12 c/lado — máx 10 kg"),
        ("Press inclinado en máquina", "3×12"),
        ("Step aeróbico suave (sin saltos)", "3×1 min"),
        ("Face pull en polea", "3×15"),
        ("Abdominales en máquina", "3×15 — exhalar al contraer"),
        ("Estiramiento completo", "8 min"),
    ]},
]

SUGERENCIAS_DESAYUNO = [
    "🥣 Avena cocida con manzana, canela y nueces — sin azúcar",
    "🥚 2 huevos revueltos + tostada integral + tomate con aceite de oliva",
    "🫙 Yogur natural (sin azúcar) + frutos rojos + semillas de chía",
    "🍌 Smoothie: banana + espinaca + leche + 1 cda mantequilla de almendras",
    "🧇 Tostada integral + palta + huevo pochado + pimienta negra",
]
SUGERENCIAS_ALMUERZO = [
    "🐟 Salmón al horno + ensalada de espinaca + arroz integral",
    "🥗 Ensalada de garbanzos con pimiento, pepino, aceitunas y aceite de oliva",
    "🍗 Pechuga de pollo a la plancha + brócoli al vapor + quínoa",
    "🫘 Lentejas estofadas con verduras + ensalada verde",
    "🐠 Atún al natural + ensalada mixta + tostada integral",
]
SUGERENCIAS_CENA = [
    "🥗 Ensalada de rúcula con sardinas, tomate cherry y aceite de oliva",
    "🍳 Tortilla de espinaca y champiñones (2 huevos) + ensalada",
    "🥣 Sopa de lentejas con cúrcuma y jengibre + tostada integral",
    "🐟 Merluza al horno con ajo, limón y pimiento",
    "🫘 Bowl de garbanzos con espinaca salteada y aceite de oliva",
]

# ── Persistencia ───────────────────────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"peso_history": [], "hume_history": [], "conversation_history": [], "rutina_index": 0}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Google Sheets ──────────────────────────────────────────────────────────────
def write_peso_to_sheets(fecha: str, peso: float, extra: dict = None):
    """Escribe un registro de peso en la hoja 'Registro semanal'."""
    gc = get_sheets_client()
    if not gc or not SPREADSHEET_ID:
        return False
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet("Registro semanal")
        all_vals = ws.col_values(1)  # columna de fechas
        next_row = len([v for v in all_vals if v]) + 1
        if next_row < 5:
            next_row = 5

        row_data = [fecha, "", peso,
                    extra.get("grasa_pct", "") if extra else "",
                    extra.get("masa_muscular", "") if extra else "",
                    extra.get("grasa_visceral", "") if extra else "",
                    extra.get("edad_metabolica", "") if extra else "",
                    "", "", "", ""]
        ws.update(f"A{next_row}:K{next_row}", [row_data])
        return True
    except Exception as e:
        print(f"Sheets write error: {e}")
        return False

def read_last_hume_from_sheets():
    """Lee la última medición completa de Hume desde Sheets."""
    gc = get_sheets_client()
    if not gc or not SPREADSHEET_ID:
        return None
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet("Registro semanal")
        data = ws.get_all_values()
        for row in reversed(data[4:]):  # saltar encabezados
            if row[2] and row[3]:  # peso y % grasa ambos presentes
                return {
                    "fecha": row[0],
                    "peso": row[2],
                    "grasa_pct": row[3],
                    "masa_muscular": row[4],
                    "grasa_visceral": row[5],
                    "edad_metabolica": row[6],
                }
        return None
    except Exception as e:
        print(f"Sheets read error: {e}")
        return None

# ── Claude ─────────────────────────────────────────────────────────────────────
def ask_claude(user_message: str, history: list, hume_context: str = "") -> str:
    system = SYSTEM_PROMPT
    if hume_context:
        system += f"\n\nÚLTIMOS DATOS DE HUME HEALTH (usar para personalizar respuesta):\n{hume_context}"
    messages = history[-10:] + [{"role": "user", "content": user_message}]
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        system=system,
        messages=messages
    )
    return resp.content[0].text

def build_hume_context(data: dict) -> str:
    last = read_last_hume_from_sheets()
    if not last:
        h = data.get("hume_history", [])
        last = h[-1] if h else None
    if not last:
        return ""
    lines = [f"Fecha medición: {last.get('fecha', 'N/D')}",
             f"Peso: {last.get('peso', 'N/D')} kg",
             f"% Grasa corporal: {last.get('grasa_pct', 'N/D')}",
             f"Masa muscular: {last.get('masa_muscular', 'N/D')} kg",
             f"Grasa visceral: {last.get('grasa_visceral', 'N/D')}",
             f"Edad metabólica: {last.get('edad_metabolica', 'N/D')}"]
    return "\n".join(lines)

# ── Teclado ────────────────────────────────────────────────────────────────────
def main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("⚖️ Registrar peso"), KeyboardButton("🥗 Sugerencia comida")],
        [KeyboardButton("💪 Rutina de gym"),  KeyboardButton("🏃 Salir a correr")],
        [KeyboardButton("📊 Mi progreso"),    KeyboardButton("📋 Check-in semanal")],
        [KeyboardButton("🔬 Actualizar Hume")],
    ], resize_keyboard=True)

def formato_rutina(r: dict) -> str:
    lines = [f"💪 *{r['nombre']}*\n"]
    for ej, det in r["ejercicios"]:
        lines.append(f"• {ej}: _{det}_")
    lines.append("\n⚠️ Respirá siempre durante el ejercicio. Sin retener el aliento.")
    return "\n".join(lines)

# ── Comandos ───────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Hola Mariano! 👋 Soy tu asistente de salud.\n\n"
        "Tip: después de medirte con el Hume, tocá *🔬 Actualizar Hume* para que pueda darte recomendaciones precisas.",
        parse_mode="Markdown", reply_markup=main_keyboard()
    )

async def cmd_progreso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    history = data.get("peso_history", [])
    if not history:
        await update.message.reply_text("Todavía no registraste ningún peso. Usá ⚖️ para empezar.", reply_markup=main_keyboard())
        return
    actual = history[-1]["peso"]
    inicio = history[0]["peso"]
    bajado = round(inicio - actual, 1)
    falta  = round(actual - 78.0, 1)
    pct    = round((bajado / max(inicio - 78.0, 0.01)) * 100)

    lines = ["📊 *Tu progreso*\n",
             f"Peso actual: *{actual} kg*",
             f"Objetivo: *78 kg* — te faltan *{falta} kg*",
             f"Bajaste *{bajado} kg* ({pct}% del camino)"]

    if len(history) >= 2:
        diff = round(actual - history[-2]["peso"], 1)
        lines.append(f"Vs semana anterior: {'📉' if diff<0 else '📈'} {diff:+.1f} kg")

    # Agregar datos Hume si hay
    hume = build_hume_context(data)
    if hume:
        lines.append("\n🔬 *Última medición Hume:*")
        for line in hume.split("\n"):
            lines.append(f"  {line}")

    lines.append("\n_Últimas mediciones:_")
    for e in history[-5:]:
        lines.append(f"  {e['fecha']}: {e['peso']} kg")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=main_keyboard())

async def cmd_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *Check-in semanal*\n\n"
        "Contame cómo fue la semana:\n"
        "• Peso actual\n• Gym / running (veces y km)\n"
        "• Dieta (1-5)\n• Energía y sueño\n\n"
        "Si te mediste con el Hume esta semana, incluí los datos.",
        parse_mode="Markdown"
    )

async def cmd_hume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔬 *Actualizar datos de Hume*\n\n"
        "Mandame los datos de tu última medición. Podés escribirlos así:\n\n"
        "`peso: 86.2\ngrasa: 28.5%\nmúsculo: 58.1 kg\ngrasa visceral: 9\nedad metabólica: 42`\n\n"
        "O simplemente una foto/captura de la app y lo leo yo.",
        parse_mode="Markdown"
    )
    context.user_data["esperando_hume"] = True

# ── Manejador principal ────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    data = load_data()

    # ── Registro de peso ──
    if context.user_data.get("esperando_peso"):
        try:
            peso = float(text.replace(",", "."))
            if 40 < peso < 200:
                tz = pytz.timezone(TIMEZONE)
                fecha = datetime.now(tz).strftime("%d/%m/%Y")
                data["peso_history"].append({"fecha": fecha, "peso": peso})
                save_data(data)
                context.user_data["esperando_peso"] = False
                # Escribir en Sheets
                sheets_ok = write_peso_to_sheets(fecha, peso)
                falta = round(peso - 78.0, 1)
                sheets_msg = " ✅ Guardado en Google Sheets." if sheets_ok else ""
                await update.message.reply_text(
                    f"✅ Peso registrado: *{peso} kg*\nTe faltan *{falta} kg* para llegar a 78.{sheets_msg}",
                    parse_mode="Markdown", reply_markup=main_keyboard()
                )
                return
        except ValueError:
            pass

    # ── Datos de Hume ──
    if context.user_data.get("esperando_hume"):
        context.user_data["esperando_hume"] = False
        # Parsear datos de Hume del texto libre con Claude
        parse_prompt = (
            f"El usuario mandó estos datos de su scanner Hume Health:\n\n{text}\n\n"
            "Extraé los valores numéricos y devolvé SOLO un JSON con estas claves "
            "(usa null si no está): peso, grasa_pct, masa_muscular, grasa_visceral, edad_metabolica. "
            "Solo el JSON, sin texto extra."
        )
        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=200,
                messages=[{"role": "user", "content": parse_prompt}]
            )
            raw = resp.content[0].text.strip()
            hume_data = json.loads(raw)
            tz = pytz.timezone(TIMEZONE)
            hume_data["fecha"] = datetime.now(tz).strftime("%d/%m/%Y")
            data.setdefault("hume_history", []).append(hume_data)
            save_data(data)
            # Escribir en Sheets si hay peso
            if hume_data.get("peso"):
                write_peso_to_sheets(hume_data["fecha"], hume_data["peso"], hume_data)

            # Generar análisis
            ctx = "\n".join(f"{k}: {v}" for k, v in hume_data.items() if v)
            analisis = ask_claude(
                "Analizá estos datos de composición corporal y dame un feedback concreto sobre mi progreso.",
                data.get("conversation_history", []),
                hume_context=ctx
            )
            await update.message.reply_text(
                f"🔬 *Datos Hume guardados*\n\n{analisis}",
                parse_mode="Markdown", reply_markup=main_keyboard()
            )
        except Exception as e:
            await update.message.reply_text(
                "No pude parsear los datos. Intentá con el formato:\n`peso: 86.2 / grasa: 28% / músculo: 58kg`",
                parse_mode="Markdown"
            )
        return

    # ── Botones rápidos ──
    if text == "⚖️ Registrar peso":
        context.user_data["esperando_peso"] = True
        await update.message.reply_text("¿Cuánto pesás hoy? (ej: 86.5)")
        return
    if text == "📊 Mi progreso":
        await cmd_progreso(update, context); return
    if text == "📋 Check-in semanal":
        await cmd_checkin(update, context); return
    if text == "🔬 Actualizar Hume":
        await cmd_hume(update, context); return

    if text == "💪 Rutina de gym":
        idx = data.get("rutina_index", 0)
        rutina = RUTINAS_GYM[idx % len(RUTINAS_GYM)]
        data["rutina_index"] = (idx + 1) % len(RUTINAS_GYM)
        save_data(data)
        await update.message.reply_text(formato_rutina(rutina), parse_mode="Markdown", reply_markup=main_keyboard())
        return

    if text == "🏃 Salir a correr":
        await update.message.reply_text(
            "🏃 *Trote suave — plan de hoy*\n\n"
            "• Calentamiento: 5 min caminata\n"
            "• Trote: 20-30 min a ritmo de conversación\n"
            "• Vuelta calma: 5 min caminata\n"
            "• Estiramiento: 5 min\n\n"
            "⚠️ Sin sprints. Ritmo constante y cómodo.",
            parse_mode="Markdown", reply_markup=main_keyboard()
        )
        return

    if text == "🥗 Sugerencia comida":
        tz = pytz.timezone(TIMEZONE)
        hora = datetime.now(tz).hour
        if hora < 10:
            ops = random.sample(SUGERENCIAS_DESAYUNO, 3); titulo = "🌅 *Desayuno*"
        elif hora < 15:
            ops = random.sample(SUGERENCIAS_ALMUERZO, 3); titulo = "🍽️ *Almuerzo*"
        else:
            ops = random.sample(SUGERENCIAS_CENA, 3); titulo = "🌙 *Cena*"
        await update.message.reply_text(titulo + "\n\n" + "\n\n".join(ops), parse_mode="Markdown", reply_markup=main_keyboard())
        return

    # ── Lenguaje natural → Claude ──
    await update.message.chat.send_action("typing")
    hume_ctx = build_hume_context(data)
    hist = data.get("conversation_history", [])
    response = ask_claude(text, hist, hume_context=hume_ctx)
    hist.append({"role": "user", "content": text})
    hist.append({"role": "assistant", "content": response})
    data["conversation_history"] = hist[-20:]
    save_data(data)
    await update.message.reply_text(response, reply_markup=main_keyboard())


# ── Handler de fotos (Hume screenshot) ────────────────────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action("typing")

    # Descargar la foto en máxima resolución
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()
    import base64
    image_b64 = base64.b64encode(file_bytes).decode("utf-8")

    # Mandar a Claude Vision para extraer datos
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        }
                    },
                    {
                        "type": "text",
                        "text": (
                            "Esta es una captura de la app Hume Health / FitTrack. "
                            "Extraé todos los valores numéricos de composición corporal que veas. "
                            "Devolvé SOLO un JSON con estas claves (null si no está): "
                            "peso, grasa_pct, masa_muscular, grasa_visceral, edad_metabolica, imc. "
                            "Solo el JSON, sin texto extra ni backticks."
                        )
                    }
                ]
            }]
        )
        raw = resp.content[0].text.strip().strip("```json").strip("```").strip()
        hume_data = json.loads(raw)

        tz = pytz.timezone(TIMEZONE)
        hume_data["fecha"] = datetime.now(tz).strftime("%d/%m/%Y")

        # Limpiar nulls
        hume_data = {k: v for k, v in hume_data.items() if v is not None}

        # Guardar localmente
        data = load_data()
        data.setdefault("hume_history", []).append(hume_data)
        save_data(data)

        # Escribir en Sheets
        peso = hume_data.get("peso")
        sheets_ok = False
        if peso:
            sheets_ok = write_peso_to_sheets(hume_data["fecha"], float(str(peso).replace(",",".")), hume_data)

        # Generar análisis con Claude
        ctx = "\n".join(f"{k}: {v}" for k, v in hume_data.items())
        analisis = ask_claude(
            "Analizá estos datos de composición corporal y dame feedback concreto sobre mi progreso y qué ajustar.",
            data.get("conversation_history", []),
            hume_context=ctx
        )

        sheets_msg = " ✅ Guardado en Sheets." if sheets_ok else ""
        await update.message.reply_text(
            f"🔬 *Datos extraídos de la imagen:*

"
            + "\n".join(f"• {k}: {v}" for k, v in hume_data.items() if k != "fecha")
            + f"\n\n{analisis}{sheets_msg}",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )

    except (json.JSONDecodeError, KeyError) as e:
        await update.message.reply_text(
            "No pude leer los datos de la imagen. "
            "Intentá con buena iluminación o escribí los valores manualmente con 🔬",
            reply_markup=main_keyboard()
        )
    except Exception as e:
        print(f"Photo handler error: {e}")
        await update.message.reply_text(
            "Hubo un error procesando la imagen. Intentá de nuevo.",
            reply_markup=main_keyboard()
        )

# ── Recordatorios ──────────────────────────────────────────────────────────────
async def recordatorio_peso_lunes(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=YOUR_CHAT_ID,
        text="⚖️ *Lunes — pesate en ayunas*\nRegistrá tu peso tocando ⚖️ en el menú.\nSi te mediste con el Hume, actualizá esos datos también 🔬",
        parse_mode="Markdown")

async def recordatorio_desayuno(context: ContextTypes.DEFAULT_TYPE):
    tz = pytz.timezone(TIMEZONE)
    es_finde = datetime.now(tz).weekday() >= 5
    ops = random.sample(SUGERENCIAS_DESAYUNO, 2)
    intro = "🌅 *Buenos días Mariano*" + (" — fin de semana, desayuná bien:" if es_finde else ":")
    await context.bot.send_message(chat_id=YOUR_CHAT_ID,
        text=intro + "\n\n" + "\n\n".join(ops), parse_mode="Markdown")

async def recordatorio_almuerzo(context: ContextTypes.DEFAULT_TYPE):
    tz = pytz.timezone(TIMEZONE)
    if datetime.now(tz).weekday() >= 5:
        return
    ops = random.sample(SUGERENCIAS_ALMUERZO, 2)
    msg = "🍽️ *Almuerzo — opciones para hoy:*\n\n" + "\n\n".join(ops)
    msg += "\n\n_Si la cantina no tiene esto: proteína magra + verduras + sin frituras._"
    await context.bot.send_message(chat_id=YOUR_CHAT_ID, text=msg, parse_mode="Markdown")

async def recordatorio_gym(context: ContextTypes.DEFAULT_TYPE):
    tz = pytz.timezone(TIMEZONE)
    if datetime.now(tz).weekday() not in [1, 3]:
        return
    data = load_data()
    idx = data.get("rutina_index", 0)
    rutina = RUTINAS_GYM[idx % len(RUTINAS_GYM)]
    data["rutina_index"] = (idx + 1) % len(RUTINAS_GYM)
    save_data(data)
    await context.bot.send_message(chat_id=YOUR_CHAT_ID,
        text="💪 *Hoy es día de gym — acá tu rutina:*\n\n" + formato_rutina(rutina),
        parse_mode="Markdown")

async def recordatorio_cena(context: ContextTypes.DEFAULT_TYPE):
    ops = random.sample(SUGERENCIAS_CENA, 2)
    msg = "🌙 *Cena — sugerencias para esta noche:*\n\n" + "\n\n".join(ops)
    msg += "\n\n_Liviano si almorzaste bien._"
    await context.bot.send_message(chat_id=YOUR_CHAT_ID, text=msg, parse_mode="Markdown")

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    import httpx

    # Cerrar sesión anterior en Telegram antes de arrancar
    try:
        import urllib.request, urllib.parse
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook"
        data = urllib.parse.urlencode({"drop_pending_updates": "true"}).encode()
        urllib.request.urlopen(url, data=data, timeout=10)
        import time as time_module
        time_module.sleep(2)
    except Exception as e:
        print(f"deleteWebhook warning: {e}")

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("progreso", cmd_progreso))
    app.add_handler(CommandHandler("checkin", cmd_checkin))
    app.add_handler(CommandHandler("hume", cmd_hume))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    tz = pytz.timezone(TIMEZONE)
    jq = app.job_queue
    jq.run_daily(recordatorio_peso_lunes, time=time(8,  0, tzinfo=tz), days=(0,))
    jq.run_daily(recordatorio_desayuno,   time=time(8,  0, tzinfo=tz))
    jq.run_daily(recordatorio_almuerzo,   time=time(11, 30, tzinfo=tz), days=(0,1,2,3,4))
    jq.run_daily(recordatorio_gym,        time=time(11, 30, tzinfo=tz), days=(1,3))
    jq.run_daily(recordatorio_cena,       time=time(19, 30, tzinfo=tz))

    print("Bot iniciado ✅")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "photo"],
    )

if __name__ == "__main__":
    main()
