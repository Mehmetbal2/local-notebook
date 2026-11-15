# SearXNG (web search)

Local Notebook uses a local [SearXNG](https://github.com/searxng/searxng) instance
for web search in chat, reports and "Add source → Search the web".

* Address: `http://127.0.0.1:8888` (change with `SEARXNG_PORT` in `.env`)
* Requires Docker (OrbStack on macOS, Docker Desktop on Windows/Linux).
* `./start.sh` starts the container when Docker is available and stops it on
  `./start.sh down`. Set `LOCAL_NOTEBOOK_SEARXNG=0` in `.env` to manage it yourself.
* Settings: `config/settings.yml` (the JSON output format must stay enabled).

Check that it works:

```bash
curl 'http://127.0.0.1:8888/search?q=test&format=json' | head -c 300
```
