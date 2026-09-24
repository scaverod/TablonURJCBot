# Bot de Telegram – Tablón oficial URJC

[![CI](https://github.com/scaverod/TablonURJCBot/actions/workflows/ci.yml/badge.svg)](https://github.com/scaverod/TablonURJCBot/actions/workflows/ci.yml)
[![Resumen diario](https://github.com/scaverod/TablonURJCBot/actions/workflows/tablon.yml/badge.svg)](https://github.com/scaverod/TablonURJCBot/actions/workflows/tablon.yml)
[![Release](https://img.shields.io/github/v/release/scaverod/TablonURJCBot)](https://github.com/scaverod/TablonURJCBot/releases/latest)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Licencia: MIT](https://img.shields.io/github/license/scaverod/TablonURJCBot)](LICENSE)
[![Telegram](https://img.shields.io/badge/Telegram-bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![Último commit](https://img.shields.io/github/last-commit/scaverod/TablonURJCBot/main)](https://github.com/scaverod/TablonURJCBot/commits/main)
[![Estrellas](https://img.shields.io/github/stars/scaverod/TablonURJCBot?style=social)](https://github.com/scaverod/TablonURJCBot/stargazers)
[![Forks](https://img.shields.io/github/forks/scaverod/TablonURJCBot?style=social)](https://github.com/scaverod/TablonURJCBot/network/members)

Cada día te manda por Telegram un resumen con los anuncios nuevos publicados en
<https://sede.urjc.es/tablon-oficial> (título, fecha y enlace).

Funciona gratis con **GitHub Actions**: no necesita servidor.

## Cómo funciona

- El workflow `.github/workflows/tablon.yml` se ejecuta cada día a las 12:34 (hora de Madrid,
  todo el año). GitHub puede retrasarlo un rato.
- Lee el tablón desde el anuncio más reciente hacia atrás hasta encontrar uno ya enviado,
  y manda todos los nuevos en un único resumen (partido en varios mensajes si es muy largo).
- Los IDs ya enviados se guardan en `estado.json`, en la rama **`estado`** del repo
  (así `main` no se ensucia). Si GitHub se salta algún día, al siguiente llega todo junto.
- Si no hay anuncios nuevos, no manda nada.
- La primera vez solo manda un mensaje de "configurado" (no te envía el histórico).

## Límites (y qué pasa si hay muchos anuncios)

| Límite | Valor | Qué hace el bot |
| --- | --- | --- |
| Tamaño de un mensaje de Telegram | 4096 caracteres | Parte el resumen en varios mensajes numerados (1/7, 2/7…) de ~15 anuncios cada uno. 100 anuncios ≈ 7 mensajes. |
| Velocidad de envío de Telegram | ~1 mensaje/s por chat | Espera 1,5 s entre mensajes. Si Telegram responde "demasiadas peticiones" (429), espera lo que indique y reintenta (hasta 5 veces). |
| Anuncios por ejecución | 500 (`MAX_PAGINAS` = 50 páginas de 10) | Si hubiera más, manda los 500 más recientes y avisa al final con el enlace al tablón. |
| Títulos muy largos | 800 caracteres | Los recorta con "…". |
| Duración del workflow | 10 min | 500 anuncios tardan ~1-2 min. |

Si el envío falla a mitad (p. ej. Telegram caído), el estado se guarda **después de cada
mensaje enviado**: al día siguiente solo se mandan los anuncios que faltaban, sin repetir ninguno.

Probado con datos reales del tablón: 100 nuevos (7 mensajes, con un 429 intermedio), más de 500
(se corta en 500 con aviso) y un fallo en el tercer mensaje (27 enviados + 73 al día siguiente).

## Puesta en marcha

### 1. Crear el bot en Telegram

1. En Telegram abre **@BotFather** → `/newbot` → ponle nombre y usuario (acabado en `bot`).
2. Copia el **token**.
3. Abre tu bot y mándale cualquier mensaje (p. ej. `/start`). Sin esto el bot no puede escribirte.

### 2. Averiguar tu chat_id

Abre en el navegador (cambiando `<TOKEN>` por el tuyo):

```text
https://api.telegram.org/bot<TOKEN>/getUpdates
```

Busca `"chat":{"id":123456789,...}`: ese número es tu chat_id.
Si sale `"result":[]`, vuelve a escribirle algo al bot y recarga.

### 3. Configurar los secretos en GitHub

En el repo: **Settings → Secrets and variables → Actions → New repository secret**:

| Nombre | Valor |
| --- | --- |
| `TELEGRAM_TOKEN` | el token de @BotFather |
| `TELEGRAM_CHAT_ID` | tu chat_id (varios separados por comas) |

> El repo es público: el token **nunca** debe ir en ningún archivo, solo en los secretos.

### 4. Probarlo

Pestaña **Actions → Tablón URJC → Run workflow**. En ~30 s te llega "✅ Bot del Tablón URJC
configurado". A partir de ahí, cada mañana recibirás los anuncios nuevos.

Para cambiar la hora, edita la línea `cron` del workflow (va en hora de Madrid, según `timezone`).

## Probar en local

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # rellena TELEGRAM_TOKEN y TELEGRAM_CHAT_ID
.venv/bin/python bot.py     # crea estado.json en local
```

## Desarrollo

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest --cov      # tests unitarios con cobertura
.venv/bin/ruff check .      # lint
```

Los tests no hacen peticiones reales: la web del tablón y la API de Telegram se simulan con
`httpx.MockTransport`. Cubren el parseo del HTML, el troceo de mensajes, los reintentos ante
errores 429/5xx, el guardado del estado y la recuperación tras un fallo a mitad de envío.
El workflow `CI` los ejecuta en Python 3.10–3.13 en cada push y pull request.

Las dependencias van con versión fija. Dependabot abre cada mes un pull request con las
actualizaciones (paquetes de Python y acciones de GitHub), y el CI lo comprueba antes de aceptarlo.

Si la web del tablón cambia y el bot deja de encontrar anuncios, el workflow diario falla a
propósito para que GitHub avise por correo, en vez de quedarse callado.

## Notas

- GitHub desactiva los workflows programados si el repo pasa 60 días sin actividad.
  Los commits diarios a la rama `estado` deberían evitarlo; si aun así pasa, GitHub avisa por
  correo y se reactiva con un clic en la pestaña Actions.
- Para volver a empezar de cero, borra la rama `estado`.
- Para cambiar la foto, descripción o nombre del bot: en **@BotFather**, `/setuserpic`,
  `/setdescription`, `/setabouttext` o `/setname`.
- El bot no responde a mensajes: solo envía el resumen diario.

## Estructura

- `tablon.py` – scraping del listado paginado del tablón
- `bot.py` – detecta los anuncios nuevos y manda el resumen por Telegram
- `tests/` – tests unitarios (pytest)
- `.github/workflows/tablon.yml` – ejecución diaria y guardado del estado
- `.github/workflows/ci.yml` – lint y tests en cada push y pull request
- `.github/dependabot.yml` – actualizaciones automáticas de dependencias

## Licencia

[MIT](LICENSE) © 2026 Sergio Cavero
