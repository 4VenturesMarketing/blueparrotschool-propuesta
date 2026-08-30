# Blue Parrot School · Propuesta marketing 2026–27

Materiales del diagnóstico YoY (24–25 vs 25–26), estimador Google Ads, simulador de plan paid y análisis internos.

## Enlaces

| Qué | URL |
|-----|-----|
| **Propuesta (canónica)** | https://4ventures.es/propuestas/blueparrotschool/ |
| **Hub análisis internos** | https://4ventures.es/propuestas/blueparrotschool/interno/ |
| **Repo GitHub** (`marketing@4ventures.es`) | https://github.com/4VenturesMarketing/blueparrotschool-propuesta |

## Qué hay aquí

| Recurso | Descripción |
|---------|-------------|
| `index.html` | Entrada / hub |
| `propuesta-marketing-bps.html` | Propuesta completa (diagnóstico + simulador + roadmap) |
| `estimador-google-ads-bps.html` | Estimador Impression Share |
| `propuesta-cliente-bps.html` | Versión cliente resumida |
| `interno/` | Informes internos (redes, orgánico/UX/GSC, paid WC) — noindex |
| `dashboard/data/` | JSON agregados (sin PII): Meta, Google Ads, GA4, GSC, WC geo/demo, CrUX, bundles |
| `dashboard/db/bps.db` | Warehouse SQLite + `DATA_DICTIONARY.md` |
| `scripts/` | Rebuild DB / propuesta / interno / refresh Google |

### Capítulos de la propuesta

1. **I · De dónde venimos** — KPIs YoY, canales, Meta vs Google, producto, geo, demos  
2. **II · Objetivos 26/27** — simulador (ppto, IS%, mix 75/25, CRs, ROAS plan)  
3. **III · Cómo llegamos** — hoja de ruta Q1–Q4 (Jun–Jul = pico comercial)

### Análisis internos (`interno/`)

- `redes.html` — perfil comprador WC + audiencia Meta + cruce leads→pedido  
- `organico-ux.html` — GSC YoY (ganados/perdidos), CrUX, landings GA4  
- `paid.html` — Google/Meta vs WooCommerce (ROAS/CAC gold)

## Data disponible en el repo

**Sí (agregados / warehouse):** `dashboard/data/*.json` (salvo PII), `dashboard/db/bps.db`, scripts, HTML.

**No (a propósito, PII):** orders completos con email/teléfono, leads Meta/Clientify crudos, matches email-level, CSVs de nacimiento. Ver `.gitignore`. Pedir acceso aparte si hace falta para un análisis concreto.

## Rebuild local

```bash
python3 scripts/refresh_google_sources.py   # GA4 + GSC + Ads (OAuth local)
python3 scripts/build_bps_db.py             # SQLite
python3 scripts/rebuild_proposal_from_db.py # propuesta HTML
python3 scripts/build_interno_analisis.py   # hub interno
```

## Privacidad

No se publican ficheros con PII. La propuesta y los JSON del repo son agregados o métricas de plataforma.
