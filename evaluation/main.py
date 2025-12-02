from langfuse import get_client
from evaluation.runner import run_one_item_with_validators
from evaluation.utility import write_result_to_pretty_json_per_item
import json
from evaluation.tami_router_task import tami_router_task
langfuse = get_client()
dataset = langfuse.get_dataset("linear_tami2")

# items is a list, no parentheses
items = dataset.items

def get_item_by_id(dataset, item_id: str):
    for item in dataset.items:   # dataset.items is a LIST
        # item.id can be UUID, string, or something convertible — be safe
        if str(item.id) == str(item_id):
            return item
    raise KeyError(f"Dataset item not found: {item_id}")

def run_all():
    for item in items:
        result = run_one_item_with_validators(item)
        write_result_to_pretty_json_per_item(result)

def run_item(item_id: str):
   run_one(item_id)

def run_one(item_id: str):
    item = get_item_by_id(dataset, item_id)
    result = run_one_item_with_validators(item)
    write_result_to_pretty_json_per_item(result)

    print("raw result:", result)
    # After graph_state = result.get("state") or {}
    graph_state = result.get("state") or {}
    ctx = graph_state.get("context") or {}
    tools_meta = ctx.get("tools") or {}

    print("\n=== Tool Results ===")
    if not tools_meta:
        print("(no tools metadata)")
    else:
        for tool_name, meta in tools_meta.items():
            if not isinstance(meta, dict):
                continue
            latest = meta.get("latest")  # your update_context_with_tool_result structure
            last_error = meta.get("last_error")
            history = meta.get("history") or []

            print(f"- {tool_name}:")
            if latest:
                print("  latest:", json.dumps(latest, ensure_ascii=False))
            if last_error:
                print("  last_error:", json.dumps(last_error, ensure_ascii=False))
            if history:
                print(f"  history_len: {len(history)}")

    print("\n=== Item Info ===")
    print("ID:", result["item_id"])
    print("Input:", result["input"])
    print("Expected output:", result["expected_output"])
    print("Metadata:", result["metadata"])
    print("\n=== Task Result ===")
    print(result["task_result"])

    print("\n=== Evaluations ===")
    for name, ev in result["evaluations"].items():
        # ev is a langfuse.Evaluation
        print(f"{name}: value={ev.value}, comment={ev.comment}")


if __name__ == "__main__":
    #  "description": "Message to other person — requires recipient resolution"
    #item = get_item_by_id(dataset, "9fa695cb-86b4-46da-9b1c-de53304feb8a")
    #task_result = tami_router_task(item=item)
    #item = get_item_by_id(dataset, "9d466174-f283-4daa-8a2e-ee13b49dc02b")
    #task_result = tami_router_task(item=item)
    #item = get_item_by_id(dataset, "3ab29b6e-2623-441b-8f37-99171ceb5e6e")
    #task_result = tami_router_task(item=item)
    
    #run_item("ab7fc91f-789b-41cf-b551-b12898903873")
    #item = get_item_by_id(dataset, "ab7fc91f-789b-41cf-b551-b12898903873")
    #task_result = tami_router_task(item=item)

    #item = get_item_by_id(dataset, "9d466174-f283-4daa-8a2e-ee13b49dc02b")
    #task_result = tami_router_task(item=item)

    #item = get_item_by_id(dataset, "e931184f-ffd4-4e87-87b9-26071e4399a9")
    #task_result = tami_router_task(item=item)

    item = get_item_by_id(dataset, "686ec570-ef06-4fe7-9942-47b0a6de8869")
    task_result = tami_router_task(item=item)
    