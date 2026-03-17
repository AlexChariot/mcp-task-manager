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

from typing import List, Literal, Optional
from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP
from database import get_connection, init_db
import csv
import io
import json
from fpdf import FPDF
import sqlite3

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
    id: int
    title: str
    completed: bool
    priority: Priority
    tags: List[str]
    due_date: Optional[str]
    created_at: str
    description: Optional[str] = None      # NOUVEAU
    project_id: Optional[int] = None       # NOUVEAU
    parent_id: Optional[int] = None        # NOUVEAU
    sort_order: Optional[int] = None       # NOUVEAU

class Project(BaseModel):
    id: int
    name: str
    description: Optional[str]
    color: Optional[str]
    created_at: str

class TaskStats(BaseModel):
    total: int
    completed: int
    open: int
    overdue: int
    by_priority: dict
    by_tag: dict


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
        due_date=row["due_date"],
        created_at=row["created_at"],
        description=row["description"] if "description" in row.keys() else None,
        project_id=row["project_id"] if "project_id" in row.keys() else None,
        parent_id=row["parent_id"] if "parent_id" in row.keys() else None,
        sort_order=row["sort_order"] if "sort_order" in row.keys() else None,
    )


def row_to_project(row) -> Project:
    """
    Convertit une ligne SQLite en modèle Project.

    Centraliser cette logique évite les incohérences
    si la structure évolue.
    """
    return Project(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        color=row["color"],
        created_at=row["created_at"],
    )


# -----------------------------------------------------------------------------
# CRUD Tools
# -----------------------------------------------------------------------------

@mcp.tool()
def create_task(
    title: str,
    priority: Priority = "medium",
    tags: List[str] = [],
    due_date: Optional[str] = None  # format: "YYYY-MM-DD"
) -> Task:
    """
    Crée une nouvelle tâche.

    - priority: low | medium | high
    - tags: liste de labels (ex: ["projetA", "backend"])
    - due_date: date limite au format YYYY-MM-DD (optionnel)
    """
    tags_str = ",".join(tags)

    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO tasks (title, priority, tags, due_date) VALUES (?, ?, ?, ?)",
            (title, priority, tags_str, due_date)
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)
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
    """
    Supprime une tâche par son identifiant.

    ⚠️ Si la tâche a des sous-tâches, elles sont supprimées aussi.
    """
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise ValueError(f"Task {id} not found")

        # Suppression explicite des sous-tâches (ne pas dépendre du CASCADE SQLite
        # qui nécessite PRAGMA foreign_keys = ON activé à chaque connexion)
        conn.execute("DELETE FROM tasks WHERE parent_id = ?", (id,))
        conn.execute("DELETE FROM tasks WHERE id = ?", (id,))
        conn.commit()

    return f"Task {id} deleted."


@mcp.tool()
def update_task_title(id: int, title: str) -> Task:
    """
    Modifie le titre d'une tâche existante.


    - id: identifiant de la tâche
    - title: nouveau titre à utiliser
    """
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise ValueError("Task not found")

        conn.execute("UPDATE tasks SET title = ? WHERE id = ?", (title, id))
        conn.commit()

        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (id,)).fetchone()

    return row_to_task(row)

@mcp.tool()
def update_task_tags(
    id: int,
    add_tags: List[str] = [],
    remove_tags: List[str] = []
) -> Task:
    """
    Modifie les tags d'une tâche existante de façon incrémentale.

    - id: identifiant de la tâche
    - add_tags: tags à ajouter (ignorés s'ils existent déjà)
    - remove_tags: tags à supprimer (ignorés s'ils sont absents)
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (id,)
        ).fetchone()

        if row is None:
            raise ValueError("Task not found")

        current_tags = set(row["tags"].split(",")) if row["tags"] else set()
        updated_tags = (current_tags | set(add_tags)) - set(remove_tags)
        tags_str = ",".join(sorted(updated_tags))

        conn.execute(
            "UPDATE tasks SET tags = ? WHERE id = ?",
            (tags_str, id)
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (id,)
        ).fetchone()

    return row_to_task(row)

@mcp.tool()
def update_task_priority(id: int, priority: Priority) -> Task:
    """
    Modifie la priorité d'une tâche existante.

    - id: identifiant de la tâche
    - priority: nouvelle priorité (low | medium | high)
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (id,)
        ).fetchone()

        if row is None:
            raise ValueError("Task not found")

        conn.execute(
            "UPDATE tasks SET priority = ? WHERE id = ?",
            (priority, id)
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (id,)
        ).fetchone()

    return row_to_task(row)


@mcp.tool()
def update_task_due_date(id: int, due_date: Optional[str]) -> Task:
    """
    Modifie ou supprime la date limite d'une tâche.

    - due_date: format YYYY-MM-DD, ou None pour supprimer
    """
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise ValueError("Task not found")

        conn.execute("UPDATE tasks SET due_date = ? WHERE id = ?", (due_date, id))
        conn.commit()

        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (id,)).fetchone()

    return row_to_task(row)

@mcp.tool()
def update_task_description(id: int, description: Optional[str]) -> Task:
    """
    Ajoute, modifie ou supprime la description d'une tâche.

    - id: identifiant de la tâche
    - description: texte long libre, ou None pour supprimer
    """
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise ValueError(f"Task {id} not found")

        conn.execute(
            "UPDATE tasks SET description = ? WHERE id = ?",
            (description, id)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (id,)).fetchone()

    return row_to_task(row)

@mcp.tool()
def list_overdue_tasks() -> List[Task]:
    """Liste les tâches non complétées dont la deadline est dépassée."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM tasks
            WHERE completed = 0
            AND due_date IS NOT NULL
            AND due_date < DATE('now')
            ORDER BY due_date ASC
        """).fetchall()

    return [row_to_task(row) for row in rows]


@mcp.tool()
def list_tasks_due_today() -> List[Task]:
    """Liste les tâches non complétées dont la deadline est aujourd'hui."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM tasks
            WHERE completed = 0
            AND due_date = DATE('now')
            ORDER BY
                CASE priority
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                END
        """).fetchall()

    return [row_to_task(row) for row in rows]


# -----------------------------------------------------------------------------
# Projects Management
# -----------------------------------------------------------------------------


@mcp.tool()
def create_project(
    name: str,
    description: Optional[str] = None,
    color: Optional[str] = None   # format: "#RRGGBB"
) -> Project:
    """
    Crée un nouveau projet.

    - name: nom unique du projet
    - description: description libre (optionnel)
    - color: couleur hex pour l'UI, ex: "#FF5733" (optionnel)
    """
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO projects (name, description, color) VALUES (?, ?, ?)",
                (name, description, color)
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        except sqlite3.IntegrityError:
            raise ValueError(f"A project named '{name}' already exists")
        

    return row_to_project(row)


@mcp.tool()
def list_projects() -> List[Project]:
    """
    Liste tous les projets avec leur nombre de tâches associées.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY created_at ASC"
        ).fetchall()

    return [row_to_project(row) for row in rows]


@mcp.tool()
def delete_project(id: int, unassign_tasks: bool = True) -> str:
    """
    Supprime un projet.

    - id: identifiant du projet
    - unassign_tasks: si True, les tâches associées restent mais
      perdent leur projet_id ; si False, elles sont supprimées avec le projet.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Project {id} not found")

        if not unassign_tasks:
            conn.execute("DELETE FROM tasks WHERE project_id = ?", (id,))

        conn.execute("DELETE FROM projects WHERE id = ?", (id,))
        conn.commit()

    return f"Project {id} deleted."


@mcp.tool()
def assign_task_to_project(task_id: int, project_id: Optional[int]) -> Task:
    """
    Associe une tâche à un projet, ou la dissocie (project_id=None).

    - task_id: identifiant de la tâche
    - project_id: identifiant du projet, ou None pour dissocier
    """
    with get_connection() as conn:
        if project_id is not None:
            proj = conn.execute(
                "SELECT id FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
            if proj is None:
                raise ValueError(f"Project {project_id} not found")

        task = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        conn.execute(
            "UPDATE tasks SET project_id = ? WHERE id = ?",
            (project_id, task_id)
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()

    return row_to_task(row)


@mcp.tool()
def list_tasks_by_project(project_id: int) -> List[Task]:
    """
    Liste toutes les tâches d'un projet, triées par sort_order puis création.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks
            WHERE project_id = ?
            ORDER BY
                COALESCE(sort_order, 9999) ASC,
                created_at ASC
            """,
            (project_id,)
        ).fetchall()

    return [row_to_task(row) for row in rows]

# -----------------------------------------------------------------------------
# Status Management
# -----------------------------------------------------------------------------

@mcp.tool()
def complete_task(id: int) -> Task:
    """Marque une tâche comme complétée."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise ValueError(f"Task {id} not found")

        conn.execute("UPDATE tasks SET completed = 1 WHERE id = ?", (id,))
        conn.commit()

        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (id,)).fetchone()

    return row_to_task(row)

@mcp.tool()
def uncomplete_task(id: int) -> Task:
    """Marque une tâche comme non complétée."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise ValueError(f"Task {id} not found")

        conn.execute("UPDATE tasks SET completed = 0 WHERE id = ?", (id,))
        conn.commit()

        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (id,)).fetchone()

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
# Ordering tasks
# -----------------------------------------------------------------------------

@mcp.tool()
def set_task_order(task_id: int, position: int) -> Task:
    """
    Définit la position d'une tâche dans l'ordre manuel d'affichage.

    - task_id: identifiant de la tâche
    - position: entier positif (1 = en premier)

    Les autres tâches sont décalées automatiquement pour éviter
    les doublons de position.
    """
    with get_connection() as conn:
        task = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        # Décale les tâches dont la position >= nouvelle position
        conn.execute(
            """
            UPDATE tasks
            SET sort_order = sort_order + 1
            WHERE sort_order >= ?
              AND id != ?
            """,
            (position, task_id)
        )

        conn.execute(
            "UPDATE tasks SET sort_order = ? WHERE id = ?",
            (position, task_id)
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()

    return row_to_task(row)


@mcp.tool()
def list_tasks_ordered() -> List[Task]:
    """
    Retourne toutes les tâches triées par ordre manuel (sort_order),
    les tâches sans ordre défini apparaissent en dernier.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks
            ORDER BY
                COALESCE(sort_order, 9999) ASC,
                created_at ASC
            """
        ).fetchall()

    return [row_to_task(row) for row in rows]


@mcp.tool()
def reset_task_order() -> str:
    """
    Supprime l'ordre manuel de toutes les tâches (remet sort_order à NULL).
    """
    with get_connection() as conn:
        conn.execute("UPDATE tasks SET sort_order = NULL")
        conn.commit()

    return "Task order reset for all tasks."



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
# Sub-tasks
# -----------------------------------------------------------------------------

@mcp.tool()
def create_subtask(
    parent_id: int,
    title: str,
    priority: Priority = "medium",
    tags: List[str] = [],
    due_date: Optional[str] = None
) -> Task:
    """
    Crée une sous-tâche liée à une tâche parente.

    - parent_id: identifiant de la tâche parente
    - title, priority, tags, due_date: identiques à create_task

    ⚠️ Si la tâche parente est supprimée, toutes ses sous-tâches
       sont supprimées automatiquement (ON DELETE CASCADE).
    ⚠️ Si la tâche parente est complétée, les sous-tâches sont
       complétées aussi (voir complete_task).
    """
    with get_connection() as conn:
        parent = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (parent_id,)
        ).fetchone()
        if parent is None:
            raise ValueError(f"Parent task {parent_id} not found")

        tags_str = ",".join(tags)
        cursor = conn.execute(
            """
            INSERT INTO tasks (title, priority, tags, due_date, parent_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, priority, tags_str, due_date, parent_id)
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()

    return row_to_task(row)


@mcp.tool()
def list_subtasks(parent_id: int) -> List[Task]:
    """
    Liste toutes les sous-tâches d'une tâche parente.

    - parent_id: identifiant de la tâche parente
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE parent_id = ? ORDER BY created_at ASC",
            (parent_id,)
        ).fetchall()

    return [row_to_task(row) for row in rows]


@mcp.tool()
def complete_task_with_subtasks(id: int) -> List[Task]:
    """
    Marque une tâche ET toutes ses sous-tâches comme complétées.

    - id: identifiant de la tâche parente

    Retourne la liste de toutes les tâches complétées (parente + enfants).
    """
    with get_connection() as conn:
        task = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (id,)
        ).fetchone()
        if task is None:
            raise ValueError(f"Task {id} not found")

        # Complète la tâche parente ET toutes ses sous-tâches
        conn.execute(
            "UPDATE tasks SET completed = 1 WHERE id = ? OR parent_id = ?",
            (id, id)
        )
        conn.commit()

        rows = conn.execute(
            "SELECT * FROM tasks WHERE id = ? OR parent_id = ?",
            (id, id)
        ).fetchall()

    return [row_to_task(row) for row in rows]


# -----------------------------------------------------------------------------
# Combined filter
# -----------------------------------------------------------------------------


@mcp.tool()
def filter_tasks(
    tag: Optional[str] = None,
    priority: Optional[Priority] = None,
    completed: Optional[bool] = None,
    project_id: Optional[int] = None,
    has_due_date: Optional[bool] = None,
    parent_id: Optional[int] = None,   # None = toutes, -1 = top-level uniquement
) -> List[Task]:
    """
    Filtre les tâches par combinaison de critères.

    Tous les paramètres sont optionnels et cumulables (AND logique).

    - tag: filtre sur un tag spécifique (recherche LIKE)
    - priority: low | medium | high
    - completed: True = complétées, False = ouvertes, None = toutes
    - project_id: filtre sur un projet
    - has_due_date: True = avec échéance, False = sans échéance
    - parent_id: -1 = tâches top-level seulement (sans parent),
                 >0 = sous-tâches d'un parent précis,
                 None = toutes (défaut)

    Exemple : filter_tasks(tag="Sekaidojo", priority="high", completed=False)
    """
    clauses = []
    params = []

    if tag is not None:
        clauses.append("tags LIKE ?")
        params.append(f"%{tag}%")

    if priority is not None:
        clauses.append("priority = ?")
        params.append(priority)

    if completed is not None:
        clauses.append("completed = ?")
        params.append(1 if completed else 0)

    if project_id is not None:
        clauses.append("project_id = ?")
        params.append(project_id)

    if has_due_date is True:
        clauses.append("due_date IS NOT NULL")
    elif has_due_date is False:
        clauses.append("due_date IS NULL")

    if parent_id == -1:
        clauses.append("parent_id IS NULL")
    elif parent_id is not None:
        clauses.append("parent_id = ?")
        params.append(parent_id)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    query = f"""
        SELECT * FROM tasks
        {where}
        ORDER BY
            CASE priority
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
            END,
            COALESCE(due_date, '9999-12-31') ASC,
            created_at ASC
    """

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

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
# Export Tools - JSON, CSV, PDF
# -----------------------------------------------------------------------------

def _get_all_tasks_for_export():
    """Helper interne : récupère toutes les tâches avec le nom du projet."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                t.*,
                p.name AS project_name
            FROM tasks t
            LEFT JOIN projects p ON t.project_id = p.id
            ORDER BY
                COALESCE(t.sort_order, 9999),
                t.created_at ASC
        """).fetchall()
    return rows


@mcp.tool()
def export_tasks_json(include_completed: bool = True) -> str:
    """
    Exporte toutes les tâches au format JSON (chaîne de caractères).

    - include_completed: inclure les tâches complétées (défaut: True)

    Retourne une chaîne JSON prête à écrire dans un fichier .json.
    """
    rows = _get_all_tasks_for_export()

    tasks = []
    for row in rows:
        if not include_completed and row["completed"]:
            continue
        tasks.append({
            "id": row["id"],
            "title": row["title"],
            "completed": bool(row["completed"]),
            "priority": row["priority"],
            "tags": row["tags"].split(",") if row["tags"] else [],
            "due_date": row["due_date"],
            "description": row["description"],
            "project": row["project_name"],
            "parent_id": row["parent_id"],
            "sort_order": row["sort_order"],
            "created_at": row["created_at"],
        })

    return json.dumps(tasks, ensure_ascii=False, indent=2)


@mcp.tool()
def export_tasks_csv(include_completed: bool = True) -> str:
    """
    Exporte toutes les tâches au format CSV (chaîne de caractères).

    - include_completed: inclure les tâches complétées (défaut: True)

    Retourne une chaîne CSV prête à écrire dans un fichier .csv.
    """
    rows = _get_all_tasks_for_export()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_ALL)

    # En-tête
    writer.writerow([
        "id", "title", "completed", "priority", "tags",
        "due_date", "description", "project", "parent_id",
        "sort_order", "created_at"
    ])

    for row in rows:
        if not include_completed and row["completed"]:
            continue
        writer.writerow([
            row["id"],
            row["title"],
            "yes" if row["completed"] else "no",
            row["priority"],
            row["tags"] or "",
            row["due_date"] or "",
            row["description"] or "",
            row["project_name"] or "",
            row["parent_id"] or "",
            row["sort_order"] or "",
            row["created_at"],
        ])

    return output.getvalue()


@mcp.tool()
def export_tasks_pdf(
    output_path: str = "tasks_export.pdf",
    include_completed: bool = True,
    title: str = "Task Export"
) -> str:
    """
    Génère un export PDF des tâches et le sauvegarde sur disque.

    - output_path: chemin du fichier PDF à créer
    - include_completed: inclure les tâches complétées (défaut: True)
    - title: titre affiché en haut du PDF

    Dépendance : pip install fpdf2

    Retourne le chemin du fichier créé.
    """
    rows = _get_all_tasks_for_export()

    PRIORITY_COLORS = {
        "high":   (220, 53,  69),   # rouge
        "medium": (255, 193, 7),    # jaune
        "low":    (40,  167, 69),   # vert
    }

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)

    # --- Titre ---
    pdf.set_font("Helvetica", style="B", size=16)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 12, title, ln=True, align="C")
    pdf.ln(4)

    # --- En-tête de tableau ---
    col_widths = [10, 70, 22, 20, 35, 30]
    headers = ["#", "Titre", "Priorité", "Statut", "Tags", "Échéance"]

    pdf.set_fill_color(50, 50, 50)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", style="B", size=9)

    for w, h in zip(col_widths, headers):
        pdf.cell(w, 8, h, border=1, fill=True, align="C")
    pdf.ln()

    # --- Lignes ---
    pdf.set_font("Helvetica", size=9)
    fill = False

    for row in rows:
        if not include_completed and row["completed"]:
            continue

        # Couleur de fond alternée
        if fill:
            pdf.set_fill_color(245, 245, 245)
        else:
            pdf.set_fill_color(255, 255, 255)

        pdf.set_text_color(30, 30, 30)

        priority = row["priority"]
        r, g, b = PRIORITY_COLORS.get(priority, (100, 100, 100))
        status = "✓" if row["completed"] else "○"
        tags_str = row["tags"] or ""
        due = row["due_date"] or "—"
        title_cell = row["title"][:38] + "…" if len(row["title"]) > 38 else row["title"]

        values = [
            str(row["id"]),
            title_cell,
            priority.capitalize(),
            status,
            tags_str[:18],
            due,
        ]

        for i, (w, val) in enumerate(zip(col_widths, values)):
            # Colonne priorité : texte coloré
            if i == 2:
                pdf.set_text_color(r, g, b)
            else:
                pdf.set_text_color(30, 30, 30)
            pdf.cell(w, 7, val, border=1, fill=True, align="C" if i != 1 else "L")

        pdf.ln()
        fill = not fill

        # Description en sous-ligne si présente
        if row["description"]:
            pdf.set_text_color(100, 100, 100)
            pdf.set_font("Helvetica", style="I", size=8)
            desc = row["description"][:90] + "…" if len(row["description"]) > 90 else row["description"]
            pdf.cell(10, 5, "", border=0)
            pdf.cell(170, 5, f"  ↳ {desc}", border=0, ln=True)
            pdf.set_font("Helvetica", size=9)

    # --- Pied de page ---
    pdf.ln(6)
    pdf.set_text_color(150, 150, 150)
    pdf.set_font("Helvetica", style="I", size=8)
    total = sum(1 for r in rows if include_completed or not r["completed"])
    pdf.cell(0, 6, f"Total : {total} tâche(s)", align="R")

    pdf.output(output_path)
    return output_path

# -----------------------------------------------------------------------------
# Stats Tools
# -----------------------------------------------------------------------------

@mcp.tool()
def get_stats() -> TaskStats:
    """Retourne un résumé statistique des tâches."""
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        completed = conn.execute("SELECT COUNT(*) FROM tasks WHERE completed = 1").fetchone()[0]
        overdue = conn.execute("""
            SELECT COUNT(*) FROM tasks
            WHERE completed = 0 AND due_date IS NOT NULL AND due_date < DATE('now')
        """).fetchone()[0]

        by_priority = {}
        for p in ["high", "medium", "low"]:
            by_priority[p] = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE priority = ?", (p,)
            ).fetchone()[0]

        rows = conn.execute("SELECT tags FROM tasks WHERE tags != ''").fetchall()
        by_tag = {}
        for row in rows:
            for tag in row["tags"].split(","):
                by_tag[tag] = by_tag.get(tag, 0) + 1

    return TaskStats(
        total=total,
        completed=completed,
        open=total - completed,
        overdue=overdue,
        by_priority=by_priority,
        by_tag=by_tag,
    )

# -----------------------------------------------------------------------------
# Entry Point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    # Important: ne rien print() ici.
    # MCP utilise stdout pour le protocole.
    mcp.run()

