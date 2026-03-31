"""
PropRebrander — Backend FastAPI
Deploy en Railway. Endpoints:
  POST /scrape          → extrae datos de una URL de propiedad
  POST /agentes         → crea o actualiza perfil de agente
  GET  /agentes/{id}    → devuelve perfil de agente
  POST /paginas         → genera y guarda una página pública
  GET  /p/{slug}        → sirve la página pública generada
"""

import asyncio
import base64
import json
import os
import re
import uuid
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from supabase import create_client, Client

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]   # service_role key (backend only)
sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="PropRebrander API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # en producción, reemplazá por tu dominio de Vercel
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Modelos ───────────────────────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    url: str
    agente_id: str | None = None   # si se pasa, genera la página automáticamente

class AgenteCreate(BaseModel):
    nombre: str
    empresa: str
    telefono: str
    whatsapp: str       # solo números, ej: 5493510000000
    email: str
    color: str = "#1a3a5c"
    logo_url: str = ""
    instagram: str = ""

class PaginaCreate(BaseModel):
    agente_id: str
    url_original: str


# ── Helpers de scraping (tomados de prop_rebrander.py) ────────────────────────

async def extraer_propiedad(url: str) -> dict:
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup

    data = {
        "url_original": url,
        "titulo": "", "precio": "", "descripcion": "",
        "caracteristicas": [], "imagenes": [], "imagenes_b64": [],
        "dominio": urlparse(url).netloc,
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = await ctx.new_page()

        img_responses: dict = {}

        async def capturar_img(response):
            ct = response.headers.get("content-type", "")
            if ct.startswith("image/") and response.status == 200:
                try:
                    body = await response.body()
                    img_responses[response.url] = (ct, body)
                except Exception:
                    pass

        page.on("response", capturar_img)
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        dominio = urlparse(url).netloc
        content = await page.content()
        soup = BeautifulSoup(content, "html.parser")

        if "zonaprop" in dominio:
            data.update(_extraer_zonaprop(soup))
        elif "mercadolibre" in dominio:
            data.update(_extraer_mercadolibre(soup))
        elif "lavoz" in dominio or "clasificados" in dominio:
            data.update(_extraer_lavoz(soup))
        else:
            data.update(_extraer_generico(soup))

        # Convertir imágenes a base64
        for img_url in data["imagenes"][:20]:
            b64 = None
            for resp_url, (ct, body) in img_responses.items():
                if img_url in resp_url or resp_url in img_url:
                    b64 = f"data:{ct};base64,{base64.b64encode(body).decode()}"
                    break
            if not b64:
                try:
                    resp = await page.request.get(img_url)
                    if resp.status == 200:
                        body = await resp.body()
                        ct = resp.headers.get("content-type", "image/jpeg")
                        b64 = f"data:{ct};base64,{base64.b64encode(body).decode()}"
                except Exception:
                    pass
            data["imagenes_b64"].append(b64 if b64 else img_url)

        await browser.close()

    return data


def _extraer_zonaprop(soup) -> dict:
    titulo = precio = descripcion = ""
    caracteristicas = []
    imagenes = []

    for sel in ["h1", "[data-qa='posting-title']", ".title-type-sup"]:
        el = soup.select_one(sel)
        if el and el.text.strip():
            titulo = el.text.strip(); break

    for sel in ["[data-qa='price-operation']", ".price-operation", "span.first-price"]:
        el = soup.select_one(sel)
        if el and el.text.strip():
            precio = el.text.strip(); break

    for sel in ["[data-qa='posting-description']", ".description-content", "#longDescription"]:
        el = soup.select_one(sel)
        if el and el.text.strip():
            descripcion = el.text.strip(); break

    for el in soup.select("[data-qa='posting-key-attribute'], .icon-feature, li.attribute"):
        t = el.text.strip()
        if t and len(t) < 80:
            caracteristicas.append(t)

    for s in soup.find_all("script"):
        txt = s.string or ""
        urls = re.findall(r'https?://[^"\']+static[^"\']+\.(?:jpg|jpeg|png|webp)', txt)
        for u in urls:
            clean = re.sub(r'-\d+x\d+', '-full', u).split('?')[0]
            if clean not in imagenes:
                imagenes.append(clean)

    if not imagenes:
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if "static" in src and src.startswith("http") and src not in imagenes:
                imagenes.append(src)

    return {"titulo": titulo, "precio": precio, "descripcion": descripcion,
            "caracteristicas": list(dict.fromkeys(caracteristicas))[:15],
            "imagenes": imagenes[:25]}


def _extraer_mercadolibre(soup) -> dict:
    titulo = precio = descripcion = ""
    caracteristicas = []
    imagenes = []

    el = soup.select_one("h1.ui-pdp-title, h1")
    if el: titulo = el.text.strip()

    el = soup.select_one(".andes-money-amount__fraction, .price-tag-fraction")
    if el: precio = "$" + el.text.strip()

    el = soup.select_one(".ui-pdp-description__content, p.ui-pdp-description__content")
    if el: descripcion = el.text.strip()

    for el in soup.select(".ui-pdp-specs__table tr, .andes-table__row"):
        t = el.text.strip().replace("\n", ": ")
        if t and len(t) < 100:
            caracteristicas.append(t)

    for s in soup.find_all("script"):
        txt = s.string or ""
        if "secure_url" in txt:
            urls = re.findall(r'"secure_url"\s*:\s*"([^"]+)"', txt)
            for u in urls:
                clean = re.sub(r'-[A-Z]\.jpg', '-O.jpg', u)
                if clean not in imagenes and "mlstatic" in clean:
                    imagenes.append(clean)

    return {"titulo": titulo, "precio": precio, "descripcion": descripcion,
            "caracteristicas": caracteristicas[:15], "imagenes": imagenes[:25]}


def _extraer_lavoz(soup) -> dict:
    titulo = precio = descripcion = ""
    caracteristicas = []
    imagenes = []

    el = soup.select_one("h1, .aviso-title, .titulo")
    if el: titulo = el.text.strip()

    el = soup.select_one(".precio, .price, [class*='price']")
    if el: precio = el.text.strip()

    el = soup.select_one(".descripcion, .description, [class*='desc']")
    if el: descripcion = el.text.strip()

    for el in soup.select("li, .caracteristica, [class*='feature']"):
        t = el.text.strip()
        if t and len(t) < 80:
            caracteristicas.append(t)

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if src.startswith("http") and any(x in src for x in [".jpg", ".jpeg", ".png", ".webp"]):
            if not any(x in src.lower() for x in ["logo", "icon", "banner"]):
                imagenes.append(src)

    return {"titulo": titulo, "precio": precio, "descripcion": descripcion,
            "caracteristicas": list(dict.fromkeys(caracteristicas))[:15],
            "imagenes": list(dict.fromkeys(imagenes))[:25]}


def _extraer_generico(soup) -> dict:
    titulo = (soup.find("h1") or soup.find("title") or type("", (), {"text": ""})()).text.strip()
    descripcion = ""
    imagenes = []

    for el in soup.select("p, li"):
        t = el.text.strip()
        if 20 < len(t) < 500:
            descripcion = t; break

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if src.startswith("http") and re.search(r'\.(jpg|jpeg|png|webp)', src, re.I):
            if not any(x in src.lower() for x in ["logo", "icon", "avatar"]):
                imagenes.append(src)

    return {"titulo": titulo, "precio": "", "descripcion": descripcion,
            "caracteristicas": [], "imagenes": imagenes[:25]}


# ── Generador HTML ─────────────────────────────────────────────────────────────

def generar_html(data: dict, agente: dict) -> str:
    color = agente.get("color", "#1a3a5c")
    color_light = color + "22"
    fotos = data.get("imagenes_b64") or data.get("imagenes", [])

    foto_cards = ""
    for i, foto in enumerate(fotos):
        foto_cards += (
            f'<div class="thumb" onclick="openLB({i})">'
            f'<img src="{foto}" alt="Foto {i+1}" loading="{"eager" if i < 4 else "lazy"}">'
            f'</div>\n'
        )

    imgs_json = json.dumps(fotos)
    caract_html = "".join(f'<div class="tag">✓ {c}</div>\n' for c in data.get("caracteristicas", []))

    logo_html = (
        f'<img src="{agente["logo_url"]}" alt="Logo" style="height:50px;margin-bottom:8px">'
        if agente.get("logo_url") else ""
    )
    ig_html = (
        f'<div style="margin-top:6px;font-size:.85rem;opacity:.8">{agente["instagram"]}</div>'
        if agente.get("instagram") else ""
    )

    titulo_safe = (data.get("titulo") or "").replace('"', "&quot;")
    desc_safe   = (data.get("descripcion") or "")[:150].replace('"', "&quot;")
    wa_msg = f"Hola%21+Vi+la+propiedad+%22{titulo_safe[:50].replace(' ', '+')}%22+y+me+interesa."

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta property="og:title" content="{titulo_safe}">
<meta property="og:description" content="{desc_safe}">
<title>{titulo_safe} — {agente['empresa']}</title>
<style>
:root {{--brand:{color};--brand-light:{color_light};}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:system-ui,-apple-system,sans-serif;background:#f8f8f6;color:#1a1a1a;}}
nav{{background:var(--brand);padding:14px 32px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100;box-shadow:0 2px 12px rgba(0,0,0,.2);}}
.nav-brand{{color:white;font-size:1.1rem;font-weight:700;}}
.nav-cta{{background:white;color:var(--brand);padding:8px 20px;border-radius:24px;text-decoration:none;font-weight:700;font-size:.88rem;}}
.hero{{position:relative;background:#222;height:480px;overflow:hidden;}}
.hero img{{width:100%;height:100%;object-fit:cover;opacity:.9;}}
.hero-overlay{{position:absolute;inset:0;background:linear-gradient(to top,rgba(0,0,0,.65) 40%,transparent);display:flex;flex-direction:column;justify-content:flex-end;padding:32px;}}
.hero-precio{{color:#fff;font-size:2rem;font-weight:800;margin-bottom:8px;}}
.hero-titulo{{color:rgba(255,255,255,.92);font-size:1.1rem;max-width:700px;line-height:1.4;}}
.galeria-wrap{{background:#111;padding:12px;}}
.galeria{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:6px;max-width:1100px;margin:0 auto;}}
.thumb{{aspect-ratio:4/3;overflow:hidden;cursor:pointer;border-radius:4px;background:#333;}}
.thumb img{{width:100%;height:100%;object-fit:cover;transition:transform .2s;display:block;}}
.thumb:hover img{{transform:scale(1.05);}}
.contenido{{max-width:1100px;margin:0 auto;padding:32px 20px;display:grid;grid-template-columns:1fr 340px;gap:28px;}}
@media(max-width:768px){{.contenido{{grid-template-columns:1fr;}}.hero{{height:300px;}}.galeria{{grid-template-columns:repeat(3,1fr);}}}}
.seccion-titulo{{font-size:.7rem;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#888;margin-bottom:12px;}}
.descripcion{{font-size:.97rem;line-height:1.75;color:#333;white-space:pre-wrap;}}
.tags{{display:flex;flex-wrap:wrap;gap:8px;margin-top:24px;}}
.tag{{background:var(--brand-light);color:var(--brand);padding:6px 14px;border-radius:20px;font-size:.82rem;font-weight:500;border:1px solid var(--brand);}}
.card-agente{{background:white;border-radius:14px;padding:24px;box-shadow:0 2px 20px rgba(0,0,0,.08);position:sticky;top:72px;}}
.agente-header{{text-align:center;padding-bottom:18px;border-bottom:1px solid #eee;margin-bottom:18px;}}
.agente-empresa{{font-size:1.05rem;font-weight:800;color:var(--brand);margin-bottom:4px;}}
.agente-nombre{{font-size:.9rem;color:#555;}}
.btn-contacto{{display:block;width:100%;padding:13px;border-radius:10px;text-decoration:none;text-align:center;font-weight:700;font-size:.95rem;margin-bottom:10px;transition:opacity .15s;}}
.btn-contacto:hover{{opacity:.85;}}
.btn-wa{{background:#25d366;color:white;}}
.btn-tel{{background:var(--brand);color:white;}}
.btn-mail{{background:#f5f5f5;color:#333;border:1px solid #ddd;}}
#lb{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.96);z-index:999;align-items:center;justify-content:center;}}
#lb.on{{display:flex;}}
#lb-img{{max-width:92vw;max-height:88vh;object-fit:contain;border-radius:4px;}}
.lb-x{{position:absolute;top:16px;right:20px;color:#fff;font-size:2rem;cursor:pointer;opacity:.7;line-height:1;}}
.lb-arr{{position:absolute;top:50%;transform:translateY(-50%);background:rgba(255,255,255,.12);color:white;border:none;font-size:2.2rem;width:52px;height:52px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;}}
.lb-prev{{left:14px;}}.lb-next{{right:14px;}}
.lb-count{{position:absolute;bottom:16px;color:rgba(255,255,255,.5);font-size:.85rem;}}
footer{{text-align:center;padding:24px;font-size:.78rem;color:#aaa;border-top:1px solid #eee;margin-top:40px;}}
</style>
</head>
<body>

<nav>
  <div class="nav-brand">{agente['empresa']}</div>
  <a class="nav-cta" href="https://wa.me/{agente['whatsapp']}?text={wa_msg}" target="_blank">💬 Consultar</a>
</nav>

<div class="hero">
  {'<img src="' + fotos[0] + '" alt="Portada">' if fotos else '<div style="height:100%;background:#333"></div>'}
  <div class="hero-overlay">
    <div class="hero-precio">{data.get('precio','')}</div>
    <div class="hero-titulo">{data.get('titulo','')}</div>
  </div>
</div>

<div class="galeria-wrap"><div class="galeria">{foto_cards}</div></div>

<div class="contenido">
  <div class="main">
    {'<div class="seccion-titulo">Descripción</div><div class="descripcion">' + data.get("descripcion","") + '</div>' if data.get("descripcion") else ''}
    {'<div class="tags">' + caract_html + '</div>' if caract_html else ''}
  </div>
  <aside class="sidebar">
    <div class="card-agente">
      <div class="agente-header">
        {logo_html}
        <div class="agente-empresa">{agente['empresa']}</div>
        <div class="agente-nombre">{agente['nombre']}</div>
        {ig_html}
      </div>
      <a class="btn-contacto btn-wa" href="https://wa.me/{agente['whatsapp']}?text={wa_msg}" target="_blank">📱 WhatsApp</a>
      <a class="btn-contacto btn-tel" href="tel:{agente['telefono'].replace(' ','')}">📞 {agente['telefono']}</a>
      <a class="btn-contacto btn-mail" href="mailto:{agente['email']}?subject=Consulta propiedad">✉️ {agente['email']}</a>
      <div style="margin-top:16px;font-size:.75rem;color:#aaa;text-align:center;line-height:1.5">Respondemos en menos de 1 hora</div>
    </div>
  </aside>
</div>

<div id="lb">
  <span class="lb-x" onclick="closeLB()">✕</span>
  <button class="lb-arr lb-prev" onclick="nav(-1)">‹</button>
  <img id="lb-img" src="" alt="">
  <button class="lb-arr lb-next" onclick="nav(1)">›</button>
  <div class="lb-count" id="lb-count"></div>
</div>

<footer>{agente['empresa']} · {agente['telefono']} · {agente['email']}</footer>

<script>
const imgs={imgs_json};let idx=0;
function openLB(i){{idx=i;document.getElementById('lb-img').src=imgs[i];document.getElementById('lb-count').textContent=(i+1)+' / '+imgs.length;document.getElementById('lb').classList.add('on');document.body.style.overflow='hidden';}}
function closeLB(){{document.getElementById('lb').classList.remove('on');document.body.style.overflow='';}}
function nav(d){{idx=(idx+d+imgs.length)%imgs.length;document.getElementById('lb-img').src=imgs[idx];document.getElementById('lb-count').textContent=(idx+1)+' / '+imgs.length;}}
document.getElementById('lb').addEventListener('click',e=>{{if(e.target===document.getElementById('lb'))closeLB();}});
document.addEventListener('keydown',e=>{{if(!document.getElementById('lb').classList.contains('on'))return;if(e.key==='ArrowRight')nav(1);if(e.key==='ArrowLeft')nav(-1);if(e.key==='Escape')closeLB();}});
</script>
</body></html>"""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {"status": "ok", "app": "PropRebrander API"}


@app.post("/agentes")
async def crear_agente(body: AgenteCreate):
    """Crea un nuevo perfil de agente y devuelve su ID."""
    row = body.model_dump()
    row["id"] = str(uuid.uuid4())
    result = sb.table("agentes").insert(row).execute()
    return {"id": row["id"], "agente": result.data[0]}


@app.get("/agentes/{agente_id}")
async def obtener_agente(agente_id: str):
    result = sb.table("agentes").select("*").eq("id", agente_id).execute()
    if not result.data:
        raise HTTPException(404, "Agente no encontrado")
    return result.data[0]


@app.post("/scrape")
async def scrape_url(body: ScrapeRequest):
    """
    Extrae una URL de propiedad. 
    Si se pasa agente_id, también genera y guarda la página pública.
    """
    try:
        data = await extraer_propiedad(body.url)
    except Exception as e:
        raise HTTPException(500, f"Error de scraping: {str(e)}")

    if not body.agente_id:
        # Solo devolver datos, sin guardar
        return {
            "titulo": data["titulo"],
            "precio": data["precio"],
            "descripcion": data["descripcion"][:300],
            "caracteristicas": data["caracteristicas"],
            "n_fotos": len(data["imagenes_b64"]),
        }

    # Obtener agente
    ag_result = sb.table("agentes").select("*").eq("id", body.agente_id).execute()
    if not ag_result.data:
        raise HTTPException(404, "Agente no encontrado")
    agente = ag_result.data[0]

    # Generar HTML
    html = generar_html(data, agente)
    slug = str(uuid.uuid4())[:8]

    # Guardar en Supabase
    pagina_row = {
        "id": slug,
        "agente_id": body.agente_id,
        "url_original": body.url,
        "titulo": data["titulo"],
        "precio": data["precio"],
        "html": html,
    }
    sb.table("paginas").insert(pagina_row).execute()

    base_url = os.environ.get("BASE_URL", "https://tu-app.railway.app")
    return {
        "slug": slug,
        "url_publica": f"{base_url}/p/{slug}",
        "titulo": data["titulo"],
        "precio": data["precio"],
        "n_fotos": len(data["imagenes_b64"]),
    }


@app.post("/paginas")
async def generar_pagina(body: PaginaCreate):
    """Wrapper explícito: recibe agente_id + url_original, devuelve URL pública."""
    return await scrape_url(ScrapeRequest(url=body.url_original, agente_id=body.agente_id))


@app.get("/p/{slug}", response_class=HTMLResponse)
async def ver_pagina(slug: str):
    """Sirve la página pública generada."""
    result = sb.table("paginas").select("html").eq("id", slug).execute()
    if not result.data:
        raise HTTPException(404, "Página no encontrada")
    return HTMLResponse(content=result.data[0]["html"])


# ── Webhook WhatsApp (Twilio) ──────────────────────────────────────────────────
from fastapi import Request
from fastapi.responses import PlainTextResponse

@app.post("/whatsapp", response_class=PlainTextResponse)
async def whatsapp_webhook(request: Request):
    """
    Twilio envía un POST con Body= (mensaje del usuario) y From= (número).
    Si el mensaje contiene una URL de propiedad y el número está registrado como agente,
    genera la página y responde con el link.
    """
    form = await request.form()
    mensaje = str(form.get("Body", "")).strip()
    numero  = str(form.get("From", "")).replace("whatsapp:", "").replace("+", "")

    # Buscar agente por número de WhatsApp
    ag_result = sb.table("agentes").select("*").eq("whatsapp", numero).execute()

    urls = re.findall(r'https?://\S+', mensaje)
    if not urls:
        return "Para generar una página, mandame el link de la propiedad 🏠"

    if not ag_result.data:
        return (
            "Tu número no está registrado. "
            "Entrá a la web app para crear tu perfil primero."
        )

    agente_id = ag_result.data[0]["id"]
    url = urls[0]

    try:
        resultado = await scrape_url(ScrapeRequest(url=url, agente_id=agente_id))
        return (
            f"✅ ¡Listo! Tu página está en:\n"
            f"{resultado['url_publica']}\n\n"
            f"🏠 {resultado['titulo']}\n"
            f"💰 {resultado['precio']}"
        )
    except Exception as e:
        return f"❌ No pude procesar esa URL. Error: {str(e)}"
