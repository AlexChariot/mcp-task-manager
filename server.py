# from mcp.server.fastmcp import FastMCP
# from tasks import create_task, list_tasks, complete_task

# # Initialise le serveur MCP
# mcp = FastMCP("task-manager")

# # Enregistre les tools
# mcp.tool()(create_task)
# mcp.tool()(list_tasks)
# mcp.tool()(complete_task)

# if __name__ == "__main__":
#     mcp.run()
    
    
from typing import List
from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("task-manager")

class Task(BaseModel):
    id: int
    title: str
    completed: bool = False

tasks: List[Task] = []
id_counter = 1


@mcp.tool()
def create_task(title: str) -> Task:
    global id_counter
    task = Task(id=id_counter, title=title)
    id_counter += 1
    tasks.append(task)
    return task


@mcp.tool()
def list_tasks() -> List[Task]:
    return tasks


@mcp.tool()
def complete_task(id: int) -> Task:
    for task in tasks:
        if task.id == id:
            task.completed = True
            return task
    raise ValueError("Task not found")


if __name__ == "__main__":
    mcp.run()