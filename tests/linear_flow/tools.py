# notes_agent/tools.py
from agent.linear_flow.tools import ToolRegistry, ToolSpec
from agent.linear_flow.tools import build_tools_reference

from models.task_item import TaskItem, BulkTasksAction
from models.get_query import GetItemsQuery
from tests.linear_flow.tami_dummy_tools import (
    process_task_tool,
    get_items_tool,
)
# start simple prompt, a few tools only
tools = ToolRegistry(
    tools={
        "process_task": ToolSpec(
            fn=process_task_tool,
            args_model=TaskItem,
            description="Create, update or delete a task.",
        ),
        "get_items": ToolSpec(
            fn=get_items_tool,
            args_model=GetItemsQuery,
            description="Get items.",
        ),
    }
)

tools_reference = build_tools_reference(tools)
print("Tools reference:\n", tools_reference)