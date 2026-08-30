# Blue Parrot School · Propuesta marketing 2026–27

Materiales del diagnóstico YoY (24–25 vs 25–26), estimador Google Ads y simulador de plan paid.

## Enlaces

- **URL canónica:** https://4ventures.es/propuestas/blueparrotschool/
- **Repo (cuenta marketing@4ventures.es):** https://github.com/4VenturesMarketing/blueparrotschool-propuesta

## Qué hay aquí

| Recurso | Descripción |
|---------|-------------|
| `index.html` | Entrada / hub |
| `propuesta-marketing-bps.html` | Propuesta completa (diagnóstico + simulador + roadmap) |
| `estimador-google-ads-bps.html` | Estimador Impression Share |
| `propuesta-cliente-bps.html` | Versión cliente resumida |
| `dashboard/data/` | JSON agregados (KPIs, Meta/Google, KW, bundles) |
| `dashboard/db/bps.db` | Warehouse SQLite del proyecto |
| `scripts/` | Rebuild de la propuesta desde DB |

## Rebuild local

```bash
python3 scripts/rebuild_proposal_from_db.py
```

## Privacidad

No se publican ficheros con PII (emails/teléfonos de leads u orders). Esos quedan fuera del repo (ver `.gitignore`).
