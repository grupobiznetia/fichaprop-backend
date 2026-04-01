#!/usr/bin/env python3
"""
PropRebrander — Extrae una publicación inmobiliaria y genera una página web con tus datos.
Requiere: pip install playwright beautifulsoup4
Luego: playwright install chromium
"""

import asyncio
import base64
import json
import re
import sys
import os
from pathlib import Path
from urllib.parse import urlparse

# ─── TUS DATOS DE CONTACTO ────────────────────────────────────────────────────
MIS_DATOS = {
    "nombre":    "Tu Nombre Completo",
    "empresa":   "Tu Inmobiliaria",
    "telefono":  "+54 9 351 000-0000",
    "whatsapp":  "5493510000000",   # sin +, sin espacios, para el link de WA
    "email":     "tu@email.com",
    "logo_url":  "",                 # URL de tu logo (opcional, dejar vacío si no tenés)
    "instagram": "@tuinmobiliaria",  # opcional
    "color":     "#1a3a5c",          # color principal de tu marca
}
# ──────────────────────────────────────────────────────────────────────────────


async def extraer_propiedad(url: str) -> dict:
    """Extrae toda la info de la publicación usando un navegador real."""
    from playwright.async_api import async_playwright

    print(f"🌐 Abriendo: {url}")
    data = {
        "url_original": url,
        "titulo": "",
        "precio": "",
        "descripcion": "",
        "caracteristicas": [],
        "imagenes": [],          # URLs originales
        "imagenes_b64": [],      # imágenes como base64 para embeber en HTML
        "dominio": urlparse(url).netloc,
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = await ctx.new_page()

        # Interceptar imágenes para guardarlas como base64
        img_responses = {}

        async def capturar_img(response):
            ct = response.headers.get("content-type", "")
            if ct.startswith("image/") and response.status == 200:
                try:
                    body = await response.body()
                    img_responses[response.url] = (ct, body)
                except:
                    pass

        page.on("response", capturar_img)

        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)  # esperar JS dinámico

        dominio = urlparse(url).netloc

        # ── Extraer según el sitio ─────────────────────────────────────────
        if "zonaprop" in dominio:
            data.update(await _extraer_zonaprop(page))
        elif "mercadolibre" in dominio:
            data.update(await _extraer_mercadolibre(page))
        elif "lavoz" in dominio or "clasificados" in dominio:
            data.update(await _extraer_lavoz(page))
        else:
            data.update(await _extraer_generico(page))

        # ── Convertir imágenes a base64 ────────────────────────────────────
        print(f"📸 Encontradas {len(data['imagenes'])} imágenes, descargando...")
        for img_url in data["imagenes"][:25]:  # máximo 25 fotos
            # Buscar en caché de respuestas interceptadas
            b64 = None
            for resp_url, (ct, body) in img_responses.items():
                if img_url in resp_url or resp_url in img_url:
                    b64 = f"data:{ct};base64,{base64.b64encode(body).decode()}"
                    break

            if not b64:
                # Intentar descargar directamente desde el contexto del navegador
                try:
                    resp = await page.request.get(img_url)
                    if resp.status == 200:
                        body = await resp.body()
                        ct = resp.headers.get("content-type", "image/jpeg")
                        b64 = f"data:{ct};base64,{base64.b64encode(body).decode()}"
                except:
                    pass

            if b64:
                data["imagenes_b64"].append(b64)
                print(f"   ✓ foto {len(data['imagenes_b64'])}")
            else:
                # Guardar URL directa como fallback
                data["imagenes_b64"].append(img_url)
                print(f"   ~ fallback URL: {img_url[:60]}...")

        await browser.close()

    return data


async def _extraer_zonaprop(page) -> dict:
    from bs4 import BeautifulSoup
    content = await page.content()
    soup = BeautifulSoup(content, "html.parser")

    titulo = ""
    precio = ""
    descripcion = ""
    caracteristicas = []
    imagenes = []

    # Título
    for sel in ["h1", "[data-qa='posting-title']", ".title-type-sup"]:
        el = soup.select_one(sel)
        if el and el.text.strip():
            titulo = el.text.strip(); break

    # Precio
    for sel in ["[data-qa='price-operation']", ".price-operation", "span.first-price"]:
        el = soup.select_one(sel)
        if el and el.text.strip():
            precio = el.text.strip(); break

    # Descripción
    for sel in ["[data-qa='posting-description']", ".description-content", "#longDescription"]:
        el = soup.select_one(sel)
        if el and el.text.strip():
            descripcion = el.text.strip(); break

    # Características
    for el in soup.select("[data-qa='posting-key-attribute'], .icon-feature, li.attribute"):
        t = el.text.strip()
        if t and len(t) < 80:
            caracteristicas.append(t)

    # Imágenes — buscar en JSON embebido
    scripts = soup.find_all("script")
    for s in scripts:
        txt = s.string or ""
        urls = re.findall(r'https?://[^"\']+static[^"\']+\.(?:jpg|jpeg|png|webp)', txt)
        for u in urls:
            clean = re.sub(r'-\d+x\d+', '-full', u).split('?')[0]
            if clean not in imagenes:
                imagenes.append(clean)

    # Fallback: imágenes del DOM
    if not imagenes:
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if "static" in src and src.startswith("http") and src not in imagenes:
                imagenes.append(src)

    return {"titulo": titulo, "precio": precio, "descripcion": descripcion,
            "caracteristicas": list(dict.fromkeys(caracteristicas))[:15],
            "imagenes": imagenes[:25]}


async def _extraer_mercadolibre(page) -> dict:
    from bs4 import BeautifulSoup
    content = await page.content()
    soup = BeautifulSoup(content, "html.parser")

    titulo = ""
    precio = ""
    descripcion = ""
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
        if t and len(t) < 100: caracteristicas.append(t)

    # Imágenes desde __PRELOADED_STATE__
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


async def _extraer_lavoz(page) -> dict:
    from bs4 import BeautifulSoup
    content = await page.content()
    soup = BeautifulSoup(content, "html.parser")

    titulo = ""
    precio = ""
    descripcion = ""
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
        if t and len(t) < 80: caracteristicas.append(t)

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if src.startswith("http") and any(x in src for x in [".jpg",".jpeg",".png",".webp"]):
            if not any(x in src.lower() for x in ["logo","icon","banner"]):
                imagenes.append(src)

    return {"titulo": titulo, "precio": precio, "descripcion": descripcion,
            "caracteristicas": list(dict.fromkeys(caracteristicas))[:15],
            "imagenes": list(dict.fromkeys(imagenes))[:25]}


async def _extraer_generico(page) -> dict:
    from bs4 import BeautifulSoup
    content = await page.content()
    soup = BeautifulSoup(content, "html.parser")

    titulo = (soup.find("h1") or soup.find("title") or type("", (), {"text": ""})()).text.strip()
    precio = ""
    descripcion = ""
    caracteristicas = []
    imagenes = []

    for el in soup.select("p, li"):
        t = el.text.strip()
        if 20 < len(t) < 500:
            descripcion = t; break

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if src.startswith("http") and re.search(r'\.(jpg|jpeg|png|webp)', src, re.I):
            if not any(x in src.lower() for x in ["logo","icon","avatar"]):
                imagenes.append(src)

    return {"titulo": titulo, "precio": precio, "descripcion": descripcion,
            "caracteristicas": caracteristicas, "imagenes": imagenes[:25]}


def generar_html(data: dict, datos_agente: dict) -> str:
    """Genera el HTML completo de la propiedad con los datos del agente."""

    color = datos_agente["color"]
    color_light = color + "22"

    # Galería de imágenes
    fotos = data["imagenes_b64"] or data["imagenes"]
    foto_cards = ""
    for i, foto in enumerate(fotos):
        foto_cards += f'<div class="thumb" onclick="openLB({i})"><img src="{foto}" alt="Foto {i+1}" loading="{"eager" if i < 4 else "lazy"}"></div>\n'

    imgs_json = json.dumps(fotos)

    # Características
    caract_html = ""
    for c in data["caracteristicas"]:
        caract_html += f'<div class="tag">✓ {c}</div>\n'

    logo_html = ""
    if datos_agente.get("logo_url"):
        logo_html = f'<img src="{datos_agente["logo_url"]}" alt="Logo" style="height:50px;margin-bottom:8px">'

    ig_html = ""
    if datos_agente.get("instagram"):
        ig_html = f'<div style="margin-top:6px;font-size:.85rem;opacity:.8">{datos_agente["instagram"]}</div>'

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta property="og:title" content="{data['titulo']}">
<meta property="og:description" content="{data['descripcion'][:150]}">
<title>{data['titulo']} — {datos_agente['empresa']}</title>
<style>
:root {{
  --brand: {color};
  --brand-light: {color_light};
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: system-ui, -apple-system, sans-serif; background: #f8f8f6; color: #1a1a1a; }}

/* NAV */
nav {{
  background: var(--brand);
  padding: 14px 32px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 2px 12px rgba(0,0,0,.2);
}}
.nav-brand {{ color: white; font-size: 1.1rem; font-weight: 700; letter-spacing: -0.3px; }}
.nav-cta {{
  background: white;
  color: var(--brand);
  padding: 8px 20px;
  border-radius: 24px;
  text-decoration: none;
  font-weight: 700;
  font-size: .88rem;
  white-space: nowrap;
}}

/* HERO */
.hero {{
  position: relative;
  background: #222;
  height: 480px;
  overflow: hidden;
}}
.hero img {{
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: .9;
}}
.hero-overlay {{
  position: absolute;
  inset: 0;
  background: linear-gradient(to top, rgba(0,0,0,.65) 40%, transparent);
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  padding: 32px;
}}
.hero-precio {{
  color: #fff;
  font-size: 2rem;
  font-weight: 800;
  margin-bottom: 8px;
}}
.hero-titulo {{
  color: rgba(255,255,255,.92);
  font-size: 1.1rem;
  max-width: 700px;
  line-height: 1.4;
}}

/* GALERÍA */
.galeria-wrap {{
  background: #111;
  padding: 12px;
}}
.galeria {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 6px;
  max-width: 1100px;
  margin: 0 auto;
}}
.thumb {{
  aspect-ratio: 4/3;
  overflow: hidden;
  cursor: pointer;
  border-radius: 4px;
  background: #333;
}}
.thumb img {{
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform .2s;
  display: block;
}}
.thumb:hover img {{ transform: scale(1.05); }}

/* CONTENIDO */
.contenido {{
  max-width: 1100px;
  margin: 0 auto;
  padding: 32px 20px;
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 28px;
}}
@media (max-width: 768px) {{
  .contenido {{ grid-template-columns: 1fr; }}
  .hero {{ height: 300px; }}
  .galeria {{ grid-template-columns: repeat(3, 1fr); }}
}}

.seccion-titulo {{
  font-size: .7rem;
  font-weight: 700;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: #888;
  margin-bottom: 12px;
}}
.descripcion {{
  font-size: .97rem;
  line-height: 1.75;
  color: #333;
  white-space: pre-wrap;
}}
.tags {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 24px;
}}
.tag {{
  background: var(--brand-light);
  color: var(--brand);
  padding: 6px 14px;
  border-radius: 20px;
  font-size: .82rem;
  font-weight: 500;
  border: 1px solid var(--brand);
}}

/* SIDEBAR */
.sidebar {{}}
.card-agente {{
  background: white;
  border-radius: 14px;
  padding: 24px;
  box-shadow: 0 2px 20px rgba(0,0,0,.08);
  position: sticky;
  top: 72px;
}}
.agente-header {{
  text-align: center;
  padding-bottom: 18px;
  border-bottom: 1px solid #eee;
  margin-bottom: 18px;
}}
.agente-empresa {{
  font-size: 1.05rem;
  font-weight: 800;
  color: var(--brand);
  margin-bottom: 4px;
}}
.agente-nombre {{
  font-size: .9rem;
  color: #555;
}}
.btn-contacto {{
  display: block;
  width: 100%;
  padding: 13px;
  border-radius: 10px;
  text-decoration: none;
  text-align: center;
  font-weight: 700;
  font-size: .95rem;
  margin-bottom: 10px;
  transition: opacity .15s;
}}
.btn-contacto:hover {{ opacity: .85; }}
.btn-wa {{ background: #25d366; color: white; }}
.btn-tel {{ background: var(--brand); color: white; }}
.btn-mail {{ background: #f5f5f5; color: #333; border: 1px solid #ddd; }}
.info-row {{
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: .83rem;
  color: #555;
  margin-top: 8px;
}}

/* LIGHTBOX */
#lb {{
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.96);
  z-index: 999;
  align-items: center;
  justify-content: center;
}}
#lb.on {{ display: flex; }}
#lb-img {{
  max-width: 92vw;
  max-height: 88vh;
  object-fit: contain;
  border-radius: 4px;
}}
.lb-x {{ position: absolute; top: 16px; right: 20px; color: #fff; font-size: 2rem; cursor: pointer; opacity: .7; line-height: 1; }}
.lb-x:hover {{ opacity: 1; }}
.lb-arr {{
  position: absolute;
  top: 50%; transform: translateY(-50%);
  background: rgba(255,255,255,.12);
  color: white; border: none;
  font-size: 2.2rem;
  width: 52px; height: 52px;
  border-radius: 50%;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}}
.lb-arr:hover {{ background: rgba(255,255,255,.25); }}
.lb-prev {{ left: 14px; }}
.lb-next {{ right: 14px; }}
.lb-count {{ position: absolute; bottom: 16px; color: rgba(255,255,255,.5); font-size: .85rem; }}

footer {{
  text-align: center;
  padding: 24px;
  font-size: .78rem;
  color: #aaa;
  border-top: 1px solid #eee;
  margin-top: 40px;
}}
</style>
</head>
<body>

<nav>
  <div class="nav-brand">{datos_agente['empresa']}</div>
  <a class="nav-cta" href="https://wa.me/{datos_agente['whatsapp']}?text=Hola,%20vi%20esta%20propiedad%20y%20me%20interesa" target="_blank">
    💬 Consultar
  </a>
</nav>

<div class="hero">
  {'<img src="' + fotos[0] + '" alt="Portada">' if fotos else '<div style="height:100%;background:#333"></div>'}
  <div class="hero-overlay">
    <div class="hero-precio">{data['precio']}</div>
    <div class="hero-titulo">{data['titulo']}</div>
  </div>
</div>

<div class="galeria-wrap">
  <div class="galeria">
    {foto_cards}
  </div>
</div>

<div class="contenido">
  <div class="main">
    {'<div class="seccion-titulo">Descripción</div><div class="descripcion">' + data['descripcion'] + '</div>' if data['descripcion'] else ''}
    {'<div class="tags">' + caract_html + '</div>' if caract_html else ''}
  </div>

  <aside class="sidebar">
    <div class="card-agente">
      <div class="agente-header">
        {logo_html}
        <div class="agente-empresa">{datos_agente['empresa']}</div>
        <div class="agente-nombre">{datos_agente['nombre']}</div>
        {ig_html}
      </div>

      <a class="btn-contacto btn-wa"
         href="https://wa.me/{datos_agente['whatsapp']}?text=Hola%21+Vi+la+propiedad+%22{data['titulo'][:50].replace(' ', '+')}%22+y+me+interesa+m%C3%A1s+informaci%C3%B3n."
         target="_blank">
        📱 WhatsApp
      </a>
      <a class="btn-contacto btn-tel" href="tel:{datos_agente['telefono'].replace(' ','')}">
        📞 {datos_agente['telefono']}
      </a>
      <a class="btn-contacto btn-mail" href="mailto:{datos_agente['email']}?subject=Consulta propiedad&body=Hola, me interesa la propiedad {data['titulo'][:50]}">
        ✉️ {datos_agente['email']}
      </a>

      <div style="margin-top:16px;font-size:.75rem;color:#aaa;text-align:center;line-height:1.5">
        Respondemos en menos de 1 hora
      </div>
    </div>
  </aside>
</div>

<!-- Lightbox -->
<div id="lb">
  <span class="lb-x" onclick="closeLB()">✕</span>
  <button class="lb-arr lb-prev" onclick="nav(-1)">‹</button>
  <img id="lb-img" src="" alt="">
  <button class="lb-arr lb-next" onclick="nav(1)">›</button>
  <div class="lb-count" id="lb-count"></div>
</div>

<footer>
  {datos_agente['empresa']} · {datos_agente['telefono']} · {datos_agente['email']}
</footer>

<script>
const imgs = {imgs_json};
let idx = 0;
function openLB(i) {{
  idx = i;
  document.getElementById('lb-img').src = imgs[i];
  document.getElementById('lb-count').textContent = (i+1) + ' / ' + imgs.length;
  document.getElementById('lb').classList.add('on');
  document.body.style.overflow = 'hidden';
}}
function closeLB() {{
  document.getElementById('lb').classList.remove('on');
  document.body.style.overflow = '';
}}
function nav(d) {{
  idx = (idx + d + imgs.length) % imgs.length;
  document.getElementById('lb-img').src = imgs[idx];
  document.getElementById('lb-count').textContent = (idx+1) + ' / ' + imgs.length;
}}
document.getElementById('lb').addEventListener('click', e => {{
  if (e.target === document.getElementById('lb')) closeLB();
}});
document.addEventListener('keydown', e => {{
  if (!document.getElementById('lb').classList.contains('on')) return;
  if (e.key === 'ArrowRight') nav(1);
  if (e.key === 'ArrowLeft') nav(-1);
  if (e.key === 'Escape') closeLB();
}});
</script>

</body>
</html>"""


async def main():
    if len(sys.argv) < 2:
        print("Uso: python prop_rebrander.py <URL_DE_LA_PROPIEDAD>")
        print("\nEjemplo:")
        print("  python prop_rebrander.py https://www.zonaprop.com.ar/propiedades/...")
        sys.exit(1)

    url = sys.argv[1]

    print("\n🏠 PropRebrander")
    print("=" * 50)
    print(f"URL: {url}")
    print(f"Agente: {MIS_DATOS['nombre']} — {MIS_DATOS['empresa']}")
    print("=" * 50)

    # Extraer datos
    data = await extraer_propiedad(url)

    print(f"\n📋 Título: {data['titulo'] or '(no encontrado)'}")
    print(f"💰 Precio: {data['precio'] or '(no encontrado)'}")
    print(f"🖼  Fotos:  {len(data['imagenes_b64'])} descargadas de {len(data['imagenes'])} encontradas")

    # Generar HTML
    html = generar_html(data, MIS_DATOS)

    # Guardar
    dominio = urlparse(url).netloc.replace("www.", "").replace(".", "_")
    nombre = f"propiedad_{dominio}.html"
    Path(nombre).write_text(html, encoding="utf-8")

    print(f"\n✅ Página generada: {nombre}")
    print(f"   Tamaño: {len(html) // 1024} KB")
    print(f"\n👉 Abrí el archivo en tu navegador para verla.")
    print("   Las imágenes están embebidas — funciona sin internet.\n")

    # Opcional: abrir automáticamente
    import webbrowser
    webbrowser.open(str(Path(nombre).resolve()))


if __name__ == "__main__":
    asyncio.run(main())
