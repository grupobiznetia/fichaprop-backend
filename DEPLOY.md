# 🚀 PropRebrander — Guía de Deploy Paso a Paso

## Resumen de lo que vas a hacer
1. Crear la base de datos en **Supabase** (5 min)
2. Subir el backend a **Railway** (10 min)
3. Subir el frontend a **Vercel** (5 min)
4. Conectar todo (5 min)

---

## PASO 1 — Supabase (base de datos)

### 1.1 Crear cuenta y proyecto
1. Entrá a https://supabase.com y hacé clic en **Start your project**
2. Registrate con GitHub o email
3. Clic en **New project**
4. Completá:
   - **Name:** `proprebrander`
   - **Database Password:** inventá una contraseña fuerte (guardala en un bloc de notas)
   - **Region:** South America (São Paulo) — la más cercana
5. Clic en **Create new project** — tarda ~2 minutos

### 1.2 Crear las tablas
1. En el menú izquierdo, clic en **SQL Editor**
2. Clic en **New query**
3. Copiá TODO el contenido del archivo `supabase_schema.sql` y pegalo en el editor
4. Clic en **Run** (o Ctrl+Enter)
5. Deberías ver "Success. No rows returned" — eso significa que funcionó ✅

### 1.3 Obtener las claves
1. En el menú izquierdo, clic en **Project Settings** (ícono de engranaje)
2. Clic en **API**
3. Copiá y guardá en un bloc de notas:
   - **Project URL** → la vas a llamar `SUPABASE_URL`
   - **service_role** key (la segunda, que dice "secret") → la vas a llamar `SUPABASE_SERVICE_KEY`
   ⚠️ No compartas la service_role key con nadie

---

## PASO 2 — Railway (backend con Playwright)

### 2.1 Crear cuenta
1. Entrá a https://railway.app
2. Clic en **Login** → **Login with GitHub**
3. Si no tenés GitHub, creá una cuenta en https://github.com (es gratis)

### 2.2 Subir el código
Tenés dos opciones:

#### Opción A: Sin conocimientos de Git (más fácil)
1. Instalá Git desde https://git-scm.com/downloads
2. Creá una cuenta en https://github.com
3. Creá un nuevo repositorio en GitHub:
   - Clic en **+** → **New repository**
   - Nombre: `proprebrander-backend`
   - Clic en **Create repository**
4. En tu computadora, abrí una terminal (o PowerShell en Windows) en la carpeta `proprebrander-backend`
5. Ejecutá estos comandos uno por uno:
   ```
   git init
   git add .
   git commit -m "PropRebrander backend inicial"
   git branch -M main
   git remote add origin https://github.com/TU-USUARIO/proprebrander-backend.git
   git push -u origin main
   ```
   (Reemplazá `TU-USUARIO` con tu usuario de GitHub)

#### Opción B: Desde Railway directamente
1. En Railway, clic en **New Project**
2. Clic en **Deploy from GitHub repo**
3. Seleccioná tu repo `proprebrander-backend`

### 2.3 Configurar variables de entorno en Railway
1. En tu proyecto de Railway, clic en el servicio creado
2. Clic en la pestaña **Variables**
3. Clic en **New Variable** y agregá estas tres:

   | Variable | Valor |
   |----------|-------|
   | `SUPABASE_URL` | La URL de tu proyecto Supabase (del paso 1.3) |
   | `SUPABASE_SERVICE_KEY` | La service_role key de Supabase (del paso 1.3) |
   | `BASE_URL` | Lo completás después con la URL de Railway |

4. Railway va a hacer un redeploy automático

### 2.4 Obtener la URL de Railway
1. Clic en la pestaña **Settings** de tu servicio
2. En la sección **Networking**, clic en **Generate Domain**
3. Copiá la URL generada (ej: `proprebrander-backend-production.up.railway.app`)
4. Volvé a **Variables** y actualizá `BASE_URL` con esa URL (con `https://` adelante)

### 2.5 Verificar que funciona
Abrí en tu navegador: `https://TU-URL.railway.app/`

Deberías ver:
```json
{"status": "ok", "app": "PropRebrander API"}
```

---

## PASO 3 — Vercel (frontend)

### 3.1 Preparar el frontend
1. Abrí el archivo `frontend/index.html`
2. Buscá esta línea (cerca del principio del `<script>`):
   ```javascript
   const API_URL = "https://TU-BACKEND.railway.app";
   ```
3. Reemplazá `TU-BACKEND.railway.app` con la URL que obtuviste en el paso 2.4
4. Guardá el archivo

### 3.2 Subir a Vercel
1. Entrá a https://vercel.com
2. Clic en **Sign Up** → **Continue with GitHub**
3. Clic en **New Project**
4. Clic en **Import Git Repository** y seleccioná tu repo
   - Si el frontend está en una subcarpeta, en **Root Directory** poné `frontend`
5. Clic en **Deploy**
6. En 1–2 minutos, Vercel te da una URL pública (ej: `proprebrander.vercel.app`)

---

## PASO 4 — Conectar todo y probar

### 4.1 Prueba de principio a fin
1. Abrí tu URL de Vercel
2. Completá tu perfil de agente y clic en **Continuar**
3. Pegá un link de ZonaProp, MercadoLibre o La Voz
4. Clic en **Generar mi página**
5. Esperá 20–40 segundos (Playwright está abriendo el sitio como un navegador real)
6. ¡Copiá tu link y compartilo!

### 4.2 Configurar WhatsApp (opcional, Twilio)
1. Entrá a https://www.twilio.com/try-twilio
2. Creá una cuenta gratuita
3. En el dashboard, buscá **Messaging → Try it out → Send a WhatsApp message**
4. Seguí las instrucciones del Sandbox de WhatsApp
5. En la configuración del Sandbox, en **"When a message comes in"**, poné:
   ```
   https://TU-URL.railway.app/whatsapp
   ```
   Método: **HTTP POST**

---

## ❓ Problemas comunes

### "Error de CORS" en el frontend
Abrí `main.py` y en la línea:
```python
allow_origins=["*"]
```
Reemplazá `"*"` por `["https://tu-app.vercel.app"]` (tu URL exacta de Vercel).
Luego hacé push al repo y Railway redeploya solo.

### El scraping tarda mucho o falla
- ZonaProp y MercadoLibre cambian sus selectores frecuentemente
- Revisá los logs en Railway (pestaña **Logs** del servicio)
- El timeout es de 30 segundos; si la propiedad tiene muchas fotos, puede tardar más

### Railway dice "Build failed"
- Revisá que todos los archivos estén subidos: `main.py`, `requirements.txt`, `Dockerfile`
- Mirá los logs del build en Railway para ver el error específico

---

## 📁 Archivos de este proyecto

```
proprebrander-backend/
├── main.py              ← API FastAPI (backend completo)
├── requirements.txt     ← Dependencias Python
├── Dockerfile           ← Para Railway con Playwright
├── supabase_schema.sql  ← Tablas de base de datos
└── frontend/
    └── index.html       ← App web (subir a Vercel)
```
