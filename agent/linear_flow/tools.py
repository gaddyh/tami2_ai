# agent_runtime/types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Mapping

from pydantic import BaseModel

from agent.linear_flow.state import LinearAgentState

ToolFn = Callable[[Dict[str, Any], LinearAgentState], Any]


@dataclass
class ToolCallPlan:
    tool: str
    args: Dict[str, Any]
    id: Optional[str] = None


@dataclass
class ToolResult:
    tool: str
    args: Dict[str, Any]
    result: Any
    error: Optional[str] = None

@dataclass
class ToolSpec:
    fn: ToolFn
    args_model: type[BaseModel]
    description: str = "No description provided."


class ToolRegistry(BaseModel):
    tools: Dict[str, Any]  # fn or ToolSpec

    def get(self, name: str) -> Optional[ToolFn]:
        t = self.tools.get(name)
        if isinstance(t, ToolSpec):
            return t.fn
        return t  # old style


from typing import get_origin, get_args, Literal
from pydantic import BaseModel

from typing import get_origin, get_args, Union

def _extract_type(field_type) -> str:
    origin = get_origin(field_type)

    # Handle Optional / Union[..., None]
    if origin is Union:
        args = get_args(field_type)
        # e.g. Optional[str] → (str, NoneType)
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return f"{_extract_type(non_none[0])} | null"
        # Generic union
        return " | ".join(_extract_type(a) for a in args)

    if origin is Literal:
        values = [repr(v) for v in get_args(field_type)]
        return " | ".join(values)

    if origin in (list, List):
        return f"List[{_extract_type(get_args(field_type)[0])}]"

    if origin in (dict, Dict):
        k, v = get_args(field_type)
        return f"Dict[{_extract_type(k)}, {_extract_type(v)}]"

    return getattr(field_type, "__name__", str(field_type))



def _collect_fields(model: type[BaseModel]) -> dict:
    """Collect fields including inherited ones."""
    fields = {}
    for cls in reversed(model.__mro__):
        if issubclass(cls, BaseModel):
            fields.update(cls.model_fields)
    return fields


from models.base_item import BaseActionItem
from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from typing import get_origin, get_args, Union
from pydantic import BaseModel

def _unwrap_model_type(field_type) -> Optional[type[BaseModel]]:
    """
    Try to find a nested Pydantic model type inside field_type.
    Handles:
      - Recurrence
      - Optional[Recurrence]
      - List[Participant]
      - List[Optional[Reminder]]
      - Union[Recurrence, None]
    Returns the first BaseModel subclass it finds, or None.
    """
    origin = get_origin(field_type)

    # Optional[...] / Union[..., None]
    if origin is Union:
        for arg in get_args(field_type):
            if arg is type(None):
                continue
            m = _unwrap_model_type(arg)
            if m is not None:
                return m
        return None

    # List[...] or list[...]
    if origin in (list, List):
        inner = get_args(field_type)[0]
        return _unwrap_model_type(inner)

    # Direct model class
    if isinstance(field_type, type) and issubclass(field_type, BaseModel):
        return field_type

    return None

def render_tool_reference(
    tool_name: str,
    description: str,
    args_model: type[BaseModel],
) -> str:
    """Render a single tool reference block."""
    lines = []
    lines.append("-" * 40)
    lines.append(f"TOOL: {tool_name}")
    lines.append(f"Purpose: {description}")
    lines.append("")
    lines.append("Arguments (JSON object):")

    all_fields = _collect_fields(args_model)

    # collect nested models so we can document them after the main field list
    nested_models: list[tuple[str, type[BaseModel]]] = []

    for field_name, field_info in all_fields.items():
        ftype = _extract_type(field_info.annotation)
        default_val = field_info.default

        # pydantic v2: required fields have default PydanticUndefined
        is_required = default_val is PydanticUndefined
        req_label = "required" if is_required else "optional"

        default_text = ""
        if (default_val is not PydanticUndefined) and (default_val is not None):
            default_text = f", default={default_val!r}"

        lines.append(f"  {field_name:12s} ({ftype}, {req_label}{default_text})")

        if field_info.description:
            lines.append(f"      {field_info.description}")

        # NEW: detect nested Pydantic models for extra docs
        model_type = _unwrap_model_type(field_info.annotation)
        if model_type is not None:
            nested_models.append((field_name, model_type))

    # -------------------------------------------------
    # Conditional domain rules for BaseActionItem tools
    # -------------------------------------------------
    if issubclass(args_model, BaseActionItem):
        lines.append("Notes:")
        lines.append(
            '  - When command == "create": item_id must be null / omitted.'
        )
        lines.append(
            '  - When command == "update" or "delete": item_id must be provided.'
        )
        lines.append(
            '  - item_type must match the specific tool (e.g. "task" for process_task).'
        )

    # NEW: nested model details
    for parent_name, model_type in nested_models:
        lines.append(f"      Nested object '{parent_name}' → {model_type.__name__} fields:")
        sub_fields = _collect_fields(model_type)
        for sub_name, sub_info in sub_fields.items():
            sub_type = _extract_type(sub_info.annotation)
            sub_default = sub_info.default
            sub_required = sub_default is PydanticUndefined
            sub_req_label = "required" if sub_required else "optional"

            sub_default_text = ""
            if (sub_default is not PydanticUndefined) and (sub_default is not None):
                sub_default_text = f", default={sub_default!r}"

            lines.append(
                f"        - {sub_name}: ({sub_type}, {sub_req_label}{sub_default_text})"
            )
            if sub_info.description:
                lines.append(f"          {sub_info.description}")

    lines.append("-" * 40)
    return "\n".join(lines)


def build_tools_reference(tool_registry) -> str:
    blocks = []

    for name, tool in tool_registry.tools.items():

        # If ToolSpec: pull from it
        if isinstance(tool, ToolSpec):
            desc = tool.description
            args_model = tool.args_model

        # If old style fn: read metadata (fallback)
        else:
            desc = getattr(tool, "description", "No description provided.")
            args_model = getattr(tool, "args_model", None)

        if args_model is None:
            raise ValueError(
                f"Tool '{name}' must define args_model=SomePydanticClass "
                f"(either via ToolSpec or as attributes on the function)"
            )

        block = render_tool_reference(name, desc, args_model)
        blocks.append(block)

    return "=== TOOLS REFERENCE ===\n" + "\n\n".join(blocks)

