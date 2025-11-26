from langfuse import get_client
from evaluation.tami_router_task import tami_router_task
from evaluation.evaluators import (
    schema_valid_evaluator,
    tool_match_evaluator,
    args_match_evaluator,
    time_semantics_evaluator,
    overall_evaluator,
)

langfuse = get_client()

dataset = langfuse.get_dataset("linear-tami")

result = dataset.run_experiment(
    name="linear-tami-eval",
    description="Replay Linear Tami on multi-turn dataset",
    task=tami_router_task,
    evaluators=[
        schema_valid_evaluator,
        tool_match_evaluator,
        args_match_evaluator,
        time_semantics_evaluator,
        overall_evaluator,
    ],
    metadata={"app": "linear-tami", "variant": "v1"},
)

print(result.format(include_item_results=True))
#print(result.format())

