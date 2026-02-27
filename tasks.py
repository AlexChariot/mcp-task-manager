from typing import List
from pydantic import BaseModel

# ---- Modèle de données ----

class Task(BaseModel):
    id: int
    title: str
    completed: bool = False


# ---- État en mémoire ----

tasks: List[Task] = []
id_counter = 1


# ---- Tools MCP ----

def create_task(title: str) -> Task:
    """
    Crée une nouvelle tâche.
    """
    global id_counter
    task = Task(id=id_counter, title=title)
    id_counter += 1
    tasks.append(task)
    return task


def list_tasks() -> List[Task]:
    """
    Retourne toutes les tâches.
    """
    return tasks


def complete_task(id: int) -> Task:
    """
    Marque une tâche comme complétée.
    """
    for task in tasks:
        if task.id == id:
            task.completed = True
            return task

    raise ValueError("Task not found")