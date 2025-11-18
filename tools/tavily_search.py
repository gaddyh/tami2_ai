from agents import function_tool
from tavily import TavilyClient
from observability.telemetry import mark_error
from tools.base import summarize
from dotenv import load_dotenv
from observability.obs import instrument_io
load_dotenv(".venv/.env")

tavily_client = TavilyClient()

@function_tool(strict_mode=True)
@instrument_io(
    name="tool.web_search",
    meta={"agent": "tami", "operation": "tool", "tool": "web_search", "schema": "web_search.v1"},
    input_fn=lambda query: {"query": query},
    output_fn=summarize,
    redact=True,
)
def web_search(query: str) -> str:
    """
    Perform a Tavily web search and return summarized results with metrics & spans.
    """
    try:
        # --- Tavily Call ---
        response = tavily_client.search(
            query,
            search_depth="advanced",
            max_results=5,
        )

        return response or "No results found."

    except Exception as e:
        mark_error(e, kind="ToolError.web_search")
        raise