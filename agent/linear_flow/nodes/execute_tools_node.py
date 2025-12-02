from agent.linear_flow.state import LinearAgentState
from agent.linear_flow.tools import ToolRegistry, ToolCallPlan
from agent.linear_flow.tools import ToolSpec  # or wherever you put it
from typing import Callable
from observability.obs import span_step, safe_update_current_span_io
from datetime import datetime
from agent.linear_flow.utils import update_context_with_tool_result
from shared.user import get_user

def _maybe_resolve_task_id_from_index(state: dict, tool_name: str, args: dict) -> dict:
    if tool_name != "process_task":
        return args

    raw_item_id = args.get("item_id")
    if not (isinstance(raw_item_id, str) and raw_item_id.isdigit()):
        # Not a numeric index, leave as-is
        return args

    ctx = state.get("context", {})
    user = get_user(ctx.get("user_id"))
    if user and getattr(user, "runtime", None):
        last_listing = user.runtime.last_tasks_listing
    if not last_listing:
        # No listing available → nothing to map, leave "1" and let it fail
        return args

    items = last_listing.get("items") or []
    idx_1based = int(raw_item_id)
    if not (1 <= idx_1based <= len(items)):
        # out of range
        return args

    chosen = items[idx_1based - 1]
    real_id = chosen.get("item_id")
    if not real_id:
        return args

    new_args = dict(args)
    new_args["item_id"] = real_id
    return new_args


def make_execute_tools_node(
    tools: ToolRegistry,
    max_history: int = 10,
) -> Callable[[LinearAgentState], LinearAgentState]:

    def execute_tools_node(state: LinearAgentState) -> LinearAgentState:
        plans = state.get("actions") or []
        state.setdefault("context", {})

        with span_step(
            "execute_tools",
            kind="node",
            node="execute_tools",
            tool_count=len(plans),
        ):
            for plan in plans:
                # if plan is ToolCallPlan, keep dot-access; if dict, use ["tool"]
                tool_name = plan.tool
                tool_args = plan.args

                tool_args = _maybe_resolve_task_id_from_index(state, tool_name, tool_args)

                entry = tools.tools.get(tool_name)
                if isinstance(entry, ToolSpec):
                    func = entry.fn
                else:
                    func = entry  # plain callable

                if not func:
                    tool_result = {
                        "tool": tool_name,
                        "args": tool_args,
                        "result": None,
                        "error": f"Unknown tool: {tool_name}",
                        "timestamp": datetime.now().isoformat(),
                    }
                    state["context"] = update_context_with_tool_result(
                        state["context"], tool_result, max_history=max_history
                    )
                    continue

                try:
                    with span_step(
                        f"tool.{tool_name}",
                        kind="tool",
                        tool=tool_name,
                        node="execute_tools",
                        redact_input=True,
                    ):
                        safe_update_current_span_io(
                            input={"args": tool_args},
                            redact=True,
                        )

                        result = func(tool_args, state)

                        safe_update_current_span_io(
                            output=result,
                            redact=True,
                        )

                        tool_result = {
                            "tool": tool_name,
                            "args": tool_args,
                            "result": result,
                            "error": None,
                            "timestamp": datetime.now().isoformat(),
                        }

                        state["context"] = update_context_with_tool_result(
                            state["context"], tool_result, max_history=max_history
                        )

                except Exception as e:
                    tool_result = {
                        "tool": tool_name,
                        "args": tool_args,
                        "result": None,
                        "error": str(e),
                        "timestamp": datetime.now().isoformat(),
                    }
                    state["context"] = update_context_with_tool_result(
                        state["context"], tool_result, max_history=max_history
                    )

            state["actions"] = []
            return state

    return execute_tools_node
