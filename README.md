# Bot de Telegram – Tablón oficial URJC

Avisa por Telegram cada vez que se publica un anuncio en
<https://sede.urjc.es/tablon-oficial> (título, categorías, emisor, anexos y enlace).

## Comandos

| Comando | Qué hace |
| --- | --- |
| `/hoy` | Anuncios publicados hoy |
| `/ayer` | Anuncios de ayer |
| `/fecha 22/09/2026` | Anuncios de un día concreto |
| `/ultimos 15` | Últimos N anuncios (10 por defecto, máx. 50) |
| `/buscar erasmus` | Busca por título |
| `/start` / `/stop` | Activa / desactiva los avisos |
| `/ayuda` | Ayuda |

## Cómo funciona

- Cada `INTERVALO_MIN` minutos (5 por defecto) lee la primera página del tablón y compara los IDs
  con los ya vistos (guardados en SQLite, `data/tablon.db`).
- En el primer arranque marca como vistos los anuncios actuales **sin avisar** (para no mandarte
  el histórico). A partir de ahí solo avisa de lo nuevo.
- Si se pierde la base de datos no pasa nada grave: vuelve a inicializarse sin spam.

## 1. Crear el bot en Telegram

1. En Telegram, abre **@BotFather** → `/newbot` → ponle nombre y usuario (acabado en `bot`).
2. Copia el **token** que te da.

## 2. Probarlo en local

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # y pega tu token en TELEGRAM_TOKEN
.venv/bin/python bot.py
```

Abre tu bot en Telegram (desde el móvil o el PC) y escribe `/start`.

> Opcional: para que nadie más pueda usarlo, pon tu chat_id en `ALLOWED_CHAT_IDS`.
> Si lo pones mal, el propio bot te responde diciendo cuál es tu chat_id.

## 3. Desplegarlo 24/7

El bot tiene que estar siempre encendido en algún sitio (tu Mac no vale si lo apagas).
El móvil solo necesita la app de Telegram.

### Opción A – Railway (la más fácil, ~5 $/mes)

1. Sube esta carpeta a un repositorio de GitHub (el `.gitignore` ya excluye `.env` y los HTML).
2. En <https://railway.app> → *New Project* → *Deploy from GitHub repo*. Detecta el `Dockerfile`.
3. En *Variables* añade `TELEGRAM_TOKEN` (y `ALLOWED_CHAT_IDS` si quieres).
4. En *Settings → Volumes* añade un volumen montado en `/app/data` (para conservar los vistos).

### Opción B – Un servidor propio (VPS, Oracle Cloud Free Tier, Raspberry Pi…)

```bash
git clone <tu-repo> tablon && cd tablon
cp .env.example .env && nano .env      # pon el token
docker build -t tablon-bot .
docker run -d --name tablon-bot --restart unless-stopped \
  --env-file .env -v "$PWD/data:/app/data" tablon-bot
docker logs -f tablon-bot              # ver que arranca
```

Sin Docker también vale: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
y un servicio systemd que ejecute `.venv/bin/python bot.py`.

> Evita los planes gratuitos que "duermen" el servicio (p. ej. Render free): el bot dejaría de
> comprobar el tablón mientras está dormido.

## Estructura

- `tablon.py` – scraping del tablón (listado, filtros por fecha/título, detalle de un anuncio)
- `storage.py` – SQLite con anuncios vistos y suscriptores
- `bot.py` – comandos de Telegram y comprobación periódica
