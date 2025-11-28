from typing import Any, Dict

from evaluation.tami_router_task import tami_router_task
from evaluation.evaluators import (
    schema_valid_evaluator,
    tool_match_evaluator,
    args_match_evaluator,
    time_semantics_evaluator,
    overall_evaluator,
)


def _call_evaluator(evaluator, *, item, output) -> Any:
    """
    Adapter so evaluators work both in:
      - Langfuse mode: evaluator(input=..., output=..., expected_output=..., metadata=...)
      - Old manual mode: evaluator(output), evaluator(output, expected_output)
    """
    kwargs = {
        "input": getattr(item, "input", None),
        "output": output,
        "expected_output": getattr(item, "expected_output", None),
        "metadata": getattr(item, "metadata", None),
    }

    # Preferred: new keyword-only Langfuse style
    try:
        return evaluator(**kwargs)
    except TypeError:
        pass

    # Fallback: evaluator(output, expected_output)
    try:
        return evaluator(output, kwargs["expected_output"])
    except TypeError:
        pass

    # Fallback: evaluator(output)
    return evaluator(output)


def run_one_item_with_validators(item) -> Dict[str, Any]:
    """
    Run a single Langfuse dataset item through the router task and all evaluators.

    Supports both:
      - New evaluators with signature: (*, input, output, expected_output=None, metadata=None, **kwargs)
      - Older positional-style evaluators.
    """
    # 1) Run task on this dataset item
    task_result = tami_router_task(item=item)

    # 2) Run evaluators (with adapter)
    evaluations = {
        "schema_valid": _call_evaluator(schema_valid_evaluator, item=item, output=task_result),
        "tool_match": _call_evaluator(tool_match_evaluator, item=item, output=task_result),
        "args_match": _call_evaluator(args_match_evaluator, item=item, output=task_result),
        "time_semantics": _call_evaluator(time_semantics_evaluator, item=item, output=task_result),
        "overall": _call_evaluator(overall_evaluator, item=item, output=task_result),
    }

    return {
        "item_id": getattr(item, "id", None),
        "input": getattr(item, "input", None),
        "expected_output": getattr(item, "expected_output", None),
        "metadata": getattr(item, "metadata", None),
        "task_result": task_result,
        "evaluations": evaluations,
    }
