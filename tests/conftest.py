import os
import sys
from pathlib import Path

# bot.py lee la configuración al importarse: se dan valores falsos antes de cargarlo.
os.environ.setdefault("TELEGRAM_TOKEN", "TOKEN-DE-PRUEBA")
os.environ.setdefault("TELEGRAM_CHAT_ID", "111, 222")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
