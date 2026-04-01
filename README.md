# PropRebrander 🏠

Extrae una publicación inmobiliaria (ZonaProp, MercadoLibre, La Voz, etc.)
y genera una página HTML con **tus datos de contacto**, lista para compartir.

---

## Instalación (una sola vez)

### 1. Instalar Python
Si no tenés Python: https://www.python.org/downloads/

### 2. Instalar dependencias
Abrí una terminal y ejecutá:

```bash
pip install playwright beautifulsoup4
playwright install chromium
```

---

## Configuración

Abrí el archivo `prop_rebrander.py` con cualquier editor de texto
y editá el bloque `MIS_DATOS` al principio:

```python
MIS_DATOS = {
    "nombre":    "Juan Pérez",
    "empresa":   "Pérez Propiedades",
    "telefono":  "+54 9 351 000-0000",
    "whatsapp":  "5493510000000",   # sin +, sin espacios
    "email":     "juan@perezprop.com",
    "logo_url":  "",                # URL de tu logo (opcional)
    "instagram": "@perezpropiedades",
    "color":     "#1a3a5c",         # color de tu marca (hex)
}
```

---

## Uso

```bash
python prop_rebrander.py <URL_DE_LA_PROPIEDAD>
```

### Ejemplos:

```bash
python prop_rebrander.py https://www.zonaprop.com.ar/propiedades/clasificado/veclapin-exc.-dpto-2-dorm-c-amplio-balcon-edif.-categoria.-57947196.html

python prop_rebrander.py https://casa.mercadolibre.com.ar/MLA-3109675966-duplex-en-una-planta-en-oportunidad-la-calandria-_JM

python prop_rebrander.py https://clasificados.lavoz.com.ar/avisos/inmuebles/casa/5464724/venta-duplex-categoria-prados-de-manantiales-2-dorm-a-estrenar
```

---

## Resultado

Se genera un archivo `propiedad_zonaprop_com_ar.html` (o similar) que:

- ✅ Tiene **todas las fotos embebidas** (funciona sin internet)
- ✅ Muestra **tu nombre, empresa, teléfono y color de marca**
- ✅ Botón de **WhatsApp** directo con mensaje pre-cargado
- ✅ Galería con lightbox, diseño mobile-friendly
- ✅ **Sin datos de la inmobiliaria original**

---

## Compartir la página

Para que otros puedan ver la página por un link, subila gratis a:

- **Netlify Drop**: arrastrá el .html en https://app.netlify.com/drop → te da un link público
- **GitHub Pages**: creá un repo y activá Pages
- **Google Drive**: subí el .html y compartí con "cualquier persona con el link"

---

## Solución de problemas

**Error "playwright not found"**: corré `pip install playwright && playwright install chromium`

**La página se genera pero sin fotos**: el sitio puede bloquear la descarga de imágenes.
En ese caso el HTML usa las URLs directas — abrilo con internet activo.

**Sin título ni descripción**: algunos sitios cargan todo por JavaScript. Probá aumentar
el `wait_for_timeout` de 3000 a 6000 en el script.
