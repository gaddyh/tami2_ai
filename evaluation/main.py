from langfuse import get_client
from evaluation.runner import run_one_item_with_validators
from evaluation.utility import write_result_to_pretty_json_per_item

langfuse = get_client()
dataset = langfuse.get_dataset("linear_tami2")

# items is a list, no parentheses
items = dataset.items

# Pick one
item = items[0]
for item in items:
    result = run_one_item_with_validators(item)
    write_result_to_pretty_json_per_item(result)

