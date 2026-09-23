"""Persistencia en SQLite: anuncios ya vistos y chats suscritos."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class Storage:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS vistos (id INTEGER PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS suscriptores (chat_id INTEGER PRIMARY KEY);
            """
        )
        self._db.commit()

    # --- anuncios vistos ---
    def hay_vistos(self) -> bool:
        return self._db.execute("SELECT 1 FROM vistos LIMIT 1").fetchone() is not None

    def filtrar_nuevos(self, ids: list[int]) -> list[int]:
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        vistos = {r[0] for r in self._db.execute(f"SELECT id FROM vistos WHERE id IN ({marks})", ids)}
        return [i for i in ids if i not in vistos]

    def marcar_vistos(self, ids: list[int]) -> None:
        self._db.executemany("INSERT OR IGNORE INTO vistos (id) VALUES (?)", [(i,) for i in ids])
        self._db.commit()

    # --- suscriptores ---
    def suscribir(self, chat_id: int) -> bool:
        cur = self._db.execute("INSERT OR IGNORE INTO suscriptores (chat_id) VALUES (?)", (chat_id,))
        self._db.commit()
        return cur.rowcount > 0

    def desuscribir(self, chat_id: int) -> bool:
        cur = self._db.execute("DELETE FROM suscriptores WHERE chat_id = ?", (chat_id,))
        self._db.commit()
        return cur.rowcount > 0

    def suscriptores(self) -> list[int]:
        return [r[0] for r in self._db.execute("SELECT chat_id FROM suscriptores")]
