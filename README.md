# Proyecto Fútbol

Estructura separada por responsabilidades:

```text
data/     datos, HTMLs, cachés y dataset final
scrapeo/  lógica de scraping, limpieza y features
ui/       interfaz web
../soccer_scraper_sessions/  perfiles de Chrome
docs/     documentación
```

Uso típico:

```bash
cd scrapeo
py -3 -m pip install -e .
py -3 scripts/run_collection.py
py -3 -m soccer_scraper.cli build-dataset --config config/config.yml
py -3 scripts/sync_whoscored_artifacts.py
py -3 scripts/build_features.py
```

UI:

```bash
cd ui
py -3 -m pip install -e .
py -3 -m pip install -e ../scrapeo
streamlit run src/app.py
```
