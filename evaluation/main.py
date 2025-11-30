from langfuse import get_client
from evaluation.runner import run_one_item_with_validators
from evaluation.utility import write_result_to_pretty_json_per_item

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

def run_one():
    item = get_item_by_id(dataset, "e6fc164a-3fa4-44c8-9218-6894b296f18b")
    result = run_one_item_with_validators(item)
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
    run_one()