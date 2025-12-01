from langfuse import get_client
from evaluation.runner import tami_router_task
from evaluation.evaluators import (
    schema_valid_evaluator,
    tool_match_evaluator,
    args_match_evaluator,
    time_semantics_evaluator,
    overall_evaluator,
    raw_output_includes_evaluator,
)

langfuse = get_client()

dataset = langfuse.get_dataset("linear_tami2")

result = dataset.run_experiment(
    name="linear_tami2-eval",
    description="Replay linear_tami2 on dataset",
    task=tami_router_task,
    evaluators=[
        schema_valid_evaluator,
        tool_match_evaluator,
        args_match_evaluator,
        time_semantics_evaluator,
        overall_evaluator,
        raw_output_includes_evaluator,  
    ],
    metadata={"app": "linear_tami2", "variant": "llm-v2"},
)

print(result.format(include_item_results=True))
#print(result.format())

