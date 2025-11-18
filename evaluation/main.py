from langfuse import get_client
from evaluation.tasks import tami_llm_task
from evaluation.evaluators import (
    schema_valid_evaluator,
    tool_match_evaluator,
    args_match_evaluator,
    time_semantics_evaluator,
    overall_evaluator,
)

langfuse = get_client()

dataset = langfuse.get_dataset("assistant-v1")

result = dataset.run_experiment(
    name="assistant-v1-eval",
    description="Replay Assistant on multi-turn dataset",
    task=tami_llm_task,
    evaluators=[
        schema_valid_evaluator,
        tool_match_evaluator,
        args_match_evaluator,
        time_semantics_evaluator,
        overall_evaluator,
    ],
    metadata={"app": "assistant", "variant": "v1"},
)

print(result.format(include_item_results=True))
#print(result.format())

