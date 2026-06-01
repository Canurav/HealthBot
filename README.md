# 🤖 Health Bot — Asistente personal de salud en Telegram

Bot de Telegram con IA (Claude) para seguimiento de peso, composición corporal, dieta mediterránea antiinflamatoria y rutinas de gym adaptadas a restricción ocular.

---

## ¿Qué hace?

- **Recordatorios automáticos** de desayuno, almuerzo, gym y cena con sugerencias personalizadas
- **Registro de peso** con historial y progreso hacia el objetivo
- **Integración con Hume Health** — guardá tus métricas de composición corporal (% grasa, masa muscular, grasa visceral, edad metabólica)
- **Sync con Google Sheets** — cada medición se escribe automáticamente en la planilla
- **Rutinas de gym** de bajo impacto (adaptadas a restricción ocular por PXE)
- **Chat libre con Claude** — hacé preguntas sobre nutrición, ejercicio o progreso y recibe respuestas personalizadas basadas en tus datos reales

---

## Horarios de recordatorios

| Horario | Recordatorio |
|---|---|
| Lunes 8:00 | Check-in de peso semanal |
| Todos los días 8:00 | Sugerencia de desayuno |
| Lun–Vie 11:30 | Sugerencia de almuerzo (cantina) |
| Mar y Jue 11:30 | Rutina de gym del día |
| Todos los días 19:30 | Sugerencia de cena |

---

## Botones del bot

| Botón | Acción |
|---|---|
| ⚖️ Registrar peso | Ingresá tu peso del día |
| 🥗 Sugerencia comida | 3 opciones según la hora (desayuno / almuerzo / cena) |
| 💪 Rutina de gym | Rota entre 3 rutinas de bajo impacto |
| 🏃 Salir a correr | Plan de trote suave |
| 📊 Mi progreso | Resumen de peso + datos Hume |
| 📋 Check-in semanal | Análisis completo de la semana |
| 🔬 Actualizar Hume | Ingresá datos del Hume Health scanner |

---

## Stack

- **Python 3.12**
- **python-telegram-bot** — framework del bot
- **Anthropic Claude Haiku** — respuestas de IA
- **gspread + google-auth** — integración con Google Sheets
- **Railway** — hosting del bot (worker process)

---

## Instalación

### 1. Cloná el repositorio

```bash
git clone https://github.com/tu-usuario/health-bot.git
cd health-bot
```

### 2. Instalá dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurá las variables de entorno

Copiá el archivo de ejemplo:

```bash
cp .env.example .env
```

Completá los valores en `.env`:

```
TELEGRAM_TOKEN=tu_token_de_botfather
ANTHROPIC_API_KEY=tu_api_key_de_anthropic
YOUR_CHAT_ID=tu_chat_id_de_telegram
TIMEZONE=Europe/Paris
SPREADSHEET_ID=id_de_tu_google_sheet
GOOGLE_CREDENTIALS_JSON={"type":"service_account",...}
```

### 4. Corré el bot

```bash
python bot.py
```

---

## Deploy en Railway

1. Conectá tu repositorio de GitHub en Railway
2. Configurá las variables de entorno en **Settings → Variables**
3. Asegurate de que el proceso sea `worker` (no `web`) en **Settings → Service**
4. Railway hace redeploy automático con cada push a `main`

> ⚠️ Asegurate de que solo haya **una instancia activa** del bot en Railway. Dos instancias simultáneas causan un error `Conflict` de Telegram.

---

## Configurar Google Sheets

### Crear Service Account

1. Entrá a [console.cloud.google.com](https://console.cloud.google.com)
2. Creá un proyecto nuevo (ej: `HealthBot`)
3. Activá **Google Sheets API** y **Google Drive API**
4. Andá a **IAM → Service Accounts → Create**
5. Nombre: `healthbot` → rol: **Editor**
6. Pestaña **Keys → Add Key → JSON** → descargá el archivo

### Convertir el JSON a una sola línea (para Railway)

```bash
cat archivo.json | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)))"
```

Copiá el output y pegalo como valor de `GOOGLE_CREDENTIALS_JSON` en Railway.

### Compartir el Sheet

- Abrí tu Google Sheet
- Compartir → pegá el email de la service account (`healthbot@...gserviceaccount.com`)
- Permiso: **Editor**

---

## Integración con Hume Health

El bot acepta datos del scanner Hume en cualquier formato. Ejemplos:

```
peso: 86.2 / grasa: 28.5% / músculo: 58.1 kg / visceral: 9
```
```
86.2kg, 28% grasa, masa muscular 58kg, edad metabólica 42
```

Claude parsea los valores automáticamente y los guarda en Google Sheets.

---

## Contexto médico incorporado

El bot tiene incorporado el siguiente contexto para todas las recomendaciones:

- Restricción ocular por **PXE y neovascularización macular** — sin ejercicio de alto impacto, sin maniobra de Valsalva, sin pesos >15kg
- Objetivo: **87kg → 78kg** con déficit calórico moderado (~300-400 kcal/día)
- **Dieta mediterránea antiinflamatoria** — pescado azul, aceite de oliva, legumbres, cereales integrales, frutos rojos
- Almuerzo en cantina laboral (lun-vie) · Cena en familia (todas las noches)
- Gym **martes y jueves** · Running ocasional (trote suave)

---

## Variables de entorno

| Variable | Descripción | Requerida |
|---|---|---|
| `TELEGRAM_TOKEN` | Token de BotFather | ✅ |
| `ANTHROPIC_API_KEY` | API key de Anthropic | ✅ |
| `YOUR_CHAT_ID` | Tu chat ID de Telegram | ✅ |
| `TIMEZONE` | Zona horaria (default: `Europe/Paris`) | ✅ |
| `SPREADSHEET_ID` | ID del Google Sheet | Opcional |
| `GOOGLE_CREDENTIALS_JSON` | JSON de la service account (una línea) | Opcional |

Sin `SPREADSHEET_ID` y `GOOGLE_CREDENTIALS_JSON` el bot funciona igual pero no sincroniza con Sheets.
