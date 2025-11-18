from langfuse import get_client
from evaluation.tasks import tami_llm_task
from evaluation.evaluators import (
    schema_valid_evaluator,
    tool_match_evaluator,
    args_match_evaluator,
    time_semantics_evaluator,
    overall_evaluator,
    raw_output_includes_evaluator,
)

langfuse = get_client()

dataset = langfuse.get_dataset("assistant-llm-v2")

result = dataset.run_experiment(
    name="assistant-llm-v2-eval",
    description="Replay Assistant LLM on single-turn dataset",
    task=tami_llm_task,
    evaluators=[
        schema_valid_evaluator,
        tool_match_evaluator,
        args_match_evaluator,
        time_semantics_evaluator,
        overall_evaluator,
        raw_output_includes_evaluator,  
    ],
    metadata={"app": "assistant", "variant": "llm-v2"},
)

print(result.format(include_item_results=True))
#print(result.format())

