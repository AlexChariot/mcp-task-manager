import sqlite3
from pathlib import Path

DB_PATH = Path("tasks.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        # Table tasks enrichie
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                priority TEXT NOT NULL DEFAULT 'medium',
                tags TEXT DEFAULT '',
                due_date DATE DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                description TEXT DEFAULT NULL,         -- NOUVEAU: description longue
                project_id INTEGER DEFAULT NULL,       -- NOUVEAU: projet associé
                parent_id INTEGER DEFAULT NULL,        -- NOUVEAU: tâche parente (sous-tâches)
                sort_order INTEGER DEFAULT NULL,       -- NOUVEAU: ordre manuel d'affichage
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
                FOREIGN KEY (parent_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
        """)

        # NOUVEAU: table projets
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT NULL,
                color TEXT DEFAULT NULL,              -- ex: "#FF5733"
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()