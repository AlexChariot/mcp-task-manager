"""
MCP Task Manager Server

Ce module expose un ensemble de tools MCP permettant de gérer des tâches
persistées en SQLite.

Design principles:
- SQLite simple (pas d’ORM)
- Tools atomiques et orientés métier
- Mapping centralisé row -> Task
- Priorités et tags simples (CSV en base)

⚠️ Si la structure de la table change, mettre à jour:
- le modèle Task
- la fonction row_to_task
"""

from typing import List, Literal
from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP
from database import get_connection, init_db


# -----------------------------------------------------------------------------
# MCP Server Initialization
# -----------------------------------------------------------------------------

mcp = FastMCP("task-manager")

# Initialise la base au démarrage.
# Important: idempotent grâce à CREATE TABLE IF NOT EXISTS.
init_db()


# -----------------------------------------------------------------------------
# Domain Model
# -----------------------------------------------------------------------------

Priority = Literal["low", "medium", "high"]


class Task(BaseModel):
    """
    Représentation d'une tâche exposée au modèle.

    - id: identifiant unique
    - title: description libre
    - completed: état
    - priority: niveau de priorité
    - tags: liste simple de labels projet
    - created_at: timestamp SQLite
    """
    id: int
    title: str
    completed: bool
    priority: Priority
    tags: List[str]
    created_at: str


# -----------------------------------------------------------------------------
# Internal Helpers
# -----------------------------------------------------------------------------

def row_to_task(row) -> Task:
    """
    Convertit une ligne SQLite en modèle Task.

    Centraliser cette logique évite les incohérences
    si la structure évolue.
    """
    return Task(
        id=row["id"],
        title=row["title"],
        completed=bool(row["completed"]),
        priority=row["priority"],
        tags=row["tags"].split(",") if row["tags"] else [],
        created_at=row["created_at"],
    )


# -----------------------------------------------------------------------------
# CRUD Tools
# -----------------------------------------------------------------------------

@mcp.tool()
def create_task(
    title: str,
    priority: Priority = "medium",
    tags: List[str] = []
) -> Task:
    """
    Crée une nouvelle tâche.

    - priority: low | medium | high
    - tags: liste de labels (ex: ["projetA", "backend"])
    """
    tags_str = ",".join(tags)

    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO tasks (title, priority, tags) VALUES (?, ?, ?)",
            (title, priority, tags_str)
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (cursor.lastrowid,)
        ).fetchone()

    return row_to_task(row)


@mcp.tool()
def list_tasks() -> List[Task]:
    """Retourne toutes les tâches."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM tasks").fetchall()

    return [row_to_task(row) for row in rows]


@mcp.tool()
def delete_task(id: int) -> str:
    """Supprime une tâche par son identifiant."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (id,))
        conn.commit()

        if cursor.rowcount == 0:
            raise ValueError("Task not found")

    return f"Task {id} deleted."

@mcp.tool()
def update_task_tags(id: int, tags: List[str]) -> Task:
    """
    Met à jour les tags d'une tâche existante.

    - id: identifiant de la tâche
    - tags: nouvelle liste de tags (remplace les tags existants)
    """
    tags_str = ",".join(tags)

    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE tasks SET tags = ? WHERE id = ?",
            (tags_str, id)
        )
        conn.commit()

        if cursor.rowcount == 0:
            raise ValueError("Task not found")

        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (id,)
        ).fetchone()

    return row_to_task(row)

# -----------------------------------------------------------------------------
# Status Management
# -----------------------------------------------------------------------------

@mcp.tool()
def complete_task(id: int) -> Task:
    """Marque une tâche comme complétée."""
    with get_connection() as conn:
        conn.execute("UPDATE tasks SET completed = 1 WHERE id = ?", (id,))
        conn.commit()

        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (id,)).fetchone()

        if row is None:
            raise ValueError("Task not found")

    return row_to_task(row)


@mcp.tool()
def uncomplete_task(id: int) -> Task:
    """Marque une tâche comme non complétée."""
    with get_connection() as conn:
        conn.execute("UPDATE tasks SET completed = 0 WHERE id = ?", (id,))
        conn.commit()

        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (id,)).fetchone()

        if row is None:
            raise ValueError("Task not found")

    return row_to_task(row)


@mcp.tool()
def mark_all_completed() -> str:
    """
    Marque toutes les tâches ouvertes comme complétées.

    ⚠️ Opération globale.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE tasks SET completed = 1 WHERE completed = 0"
        )
        conn.commit()

    return f"{cursor.rowcount} task(s) marked as completed."


# -----------------------------------------------------------------------------
# Filtering & Query Tools
# -----------------------------------------------------------------------------

@mcp.tool()
def list_open_tasks() -> List[Task]:
    """Liste uniquement les tâches non complétées."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE completed = 0 ORDER BY created_at ASC"
        ).fetchall()

    return [row_to_task(row) for row in rows]


@mcp.tool()
def list_completed_tasks() -> List[Task]:
    """Liste uniquement les tâches complétées."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE completed = 1 ORDER BY created_at DESC"
        ).fetchall()

    return [row_to_task(row) for row in rows]


@mcp.tool()
def list_tasks_by_priority() -> List[Task]:
    """
    Trie les tâches par priorité (high > medium > low),
    puis par date de création.
    """
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM tasks
            ORDER BY
                CASE priority
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                END,
                created_at ASC
        """).fetchall()

    return [row_to_task(row) for row in rows]


@mcp.tool()
def list_tasks_by_tag(tag: str) -> List[Task]:
    """
    Liste les tâches contenant un tag spécifique.

    ⚠️ Les tags sont stockés en CSV.
    Cette recherche utilise LIKE, donc approximation.
    """
    pattern = f"%{tag}%"

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE tags LIKE ?",
            (pattern,)
        ).fetchall()

    return [row_to_task(row) for row in rows]


@mcp.tool()
def search_tasks(keyword: str) -> List[Task]:
    """
    Recherche plein texte simple dans:
    - title
    - tags
    """
    pattern = f"%{keyword}%"

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks
            WHERE title LIKE ?
            OR tags LIKE ?
            ORDER BY created_at DESC
            """,
            (pattern, pattern)
        ).fetchall()

    return [row_to_task(row) for row in rows]


# -----------------------------------------------------------------------------
# Bulk Operations
# -----------------------------------------------------------------------------

@mcp.tool()
def delete_completed_tasks() -> str:
    """Supprime toutes les tâches complétées."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM tasks WHERE completed = 1"
        )
        conn.commit()

    return f"{cursor.rowcount} completed task(s) deleted."


@mcp.tool()
def reset_all_tasks() -> str:
    """
    Supprime absolument toutes les tâches.

    ⚠️ Destructif. À utiliser consciemment.
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM tasks")
        conn.commit()

    return "All tasks deleted."


# -----------------------------------------------------------------------------
# Entry Point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    # Important: ne rien print() ici.
    # MCP utilise stdout pour le protocole.
    mcp.run()