from typing import List, Literal
from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP
from database import get_connection, init_db

mcp = FastMCP("task-manager")

# Initialise la base au démarrage
init_db()


Priority = Literal["low", "medium", "high"]

class Task(BaseModel):
    id: int
    title: str
    completed: bool
    priority: Priority
    tags: List[str]
    created_at: str
    

tasks: List[Task] = []
id_counter = 1



def row_to_task(row) -> Task:
    return Task(
        id=row["id"],
        title=row["title"],
        completed=bool(row["completed"]),
        priority=row["priority"],
        tags=row["tags"].split(",") if row["tags"] else [],
        created_at=row["created_at"],
    )



@mcp.tool()
def create_task(
    title: str,
    priority: Priority = "medium",
    tags: List[str] = []
) -> Task:

    tags_str = ",".join(tags)

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks (title, priority, tags)
            VALUES (?, ?, ?)
            """,
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
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM tasks").fetchall()

    return [
        Task(
            id=row["id"],
            title=row["title"],
            completed=bool(row["completed"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]
    
@mcp.tool()
def uncomplete_task(id: int) -> Task:
    with get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET completed = 0 WHERE id = ?",
            (id,)
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (id,)
        ).fetchone()

        if row is None:
            raise ValueError("Task not found")

    return Task(
        id=row["id"],
        title=row["title"],
        completed=bool(row["completed"]),
        created_at=row["created_at"],
    )

@mcp.tool()
def complete_task(id: int) -> Task:
    with get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET completed = 1 WHERE id = ?",
            (id,)
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (id,)
        ).fetchone()

        if row is None:
            raise ValueError("Task not found")

    return Task(
        id=row["id"],
        title=row["title"],
        completed=bool(row["completed"]),
        created_at=row["created_at"],
    )
    
@mcp.tool()
def delete_task(id: int) -> str:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM tasks WHERE id = ?",
            (id,)
        )
        conn.commit()

        if cursor.rowcount == 0:
            raise ValueError("Task not found")

    return f"Task {id} deleted successfully."


@mcp.tool()
def list_open_tasks() -> List[Task]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE completed = 0 ORDER BY created_at ASC"
        ).fetchall()

    return [row_to_task(row) for row in rows]

@mcp.tool()
def list_completed_tasks() -> List[Task]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE completed = 1 ORDER BY created_at DESC"
        ).fetchall()

    return [row_to_task(row) for row in rows]

@mcp.tool()
def count_open_tasks() -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as count FROM tasks WHERE completed = 0"
        ).fetchone()

    return row["count"]

@mcp.tool()
def count_completed_tasks() -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as count FROM tasks WHERE completed = 1"
        ).fetchone()

    return row["count"]

@mcp.tool()
def delete_open_tasks() -> str:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM tasks WHERE completed = 0"
        )
        conn.commit()

    return f"{cursor.rowcount} open task(s) deleted."

@mcp.tool()
def delete_completed_tasks() -> str:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM tasks WHERE completed = 1"
        )
        conn.commit()

        deleted_count = cursor.rowcount

    return f"{deleted_count} completed task(s) deleted."

@mcp.tool()
def get_next_task() -> Task | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM tasks
            WHERE completed = 0
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        return None

    return row_to_task(row)


@mcp.tool()
def mark_all_completed() -> str:
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE tasks SET completed = 1 WHERE completed = 0"
        )
        conn.commit()

    return f"{cursor.rowcount} task(s) marked as completed."


@mcp.tool()
def search_tasks(keyword: str) -> List[Task]:

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


@mcp.tool()
def list_tasks_by_priority() -> List[Task]:

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

    pattern = f"%{tag}%"

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE tags LIKE ?",
            (pattern,)
        ).fetchall()

    return [row_to_task(row) for row in rows]

@mcp.tool()
def reset_all_tasks() -> str:
    with get_connection() as conn:
        conn.execute("DELETE FROM tasks")
        conn.commit()

    return "All tasks deleted."





if __name__ == "__main__":
    mcp.run()