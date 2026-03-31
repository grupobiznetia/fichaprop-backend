-- ============================================================
-- PropRebrander — Tablas Supabase
-- Ejecutar en: Supabase Dashboard → SQL Editor → New query
-- ============================================================

-- Tabla de agentes inmobiliarios
CREATE TABLE agentes (
  id          TEXT PRIMARY KEY,
  nombre      TEXT NOT NULL,
  empresa     TEXT NOT NULL,
  telefono    TEXT NOT NULL,
  whatsapp    TEXT NOT NULL,   -- solo números, para links de WA
  email       TEXT NOT NULL,
  color       TEXT DEFAULT '#1a3a5c',
  logo_url    TEXT DEFAULT '',
  instagram   TEXT DEFAULT '',
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Tabla de páginas generadas
CREATE TABLE paginas (
  id           TEXT PRIMARY KEY,        -- slug de 8 caracteres, ej: "a1b2c3d4"
  agente_id    TEXT REFERENCES agentes(id) ON DELETE CASCADE,
  url_original TEXT NOT NULL,
  titulo       TEXT DEFAULT '',
  precio       TEXT DEFAULT '',
  html         TEXT NOT NULL,           -- HTML completo con fotos en base64
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Índice para buscar páginas por agente
CREATE INDEX idx_paginas_agente ON paginas(agente_id);

-- Índice para buscar agentes por whatsapp (usado en webhook)
CREATE INDEX idx_agentes_whatsapp ON agentes(whatsapp);

-- ⚠️  Row Level Security: desactivado para el backend (usa service_role key)
-- Si querés que los agentes accedan a sus propios datos desde el frontend,
-- habilitá RLS y creá políticas. Por ahora, el backend es el único que escribe.
