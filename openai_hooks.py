from agents import Agent, function_tool, Runner, RunHooks

# custom_hooks.py
from observability.obs import span_attrs, safe_update_current_span_io
from observability.telemetry import mark_error
from tools.base import summarize


class CustomHooks(RunHooks):
    async def on_tool_end(self, context, agent, tool, result: str):
        """
        Lifecycle instrumentation that mirrors your @instrument_io decorator.
        Fires after ANY tool finishes (function tool, search tool, WebSearchTool, etc.)
        """
        try:
            tool_name = getattr(tool, "name", "unknown")
            user_id = getattr(context.context, "user_id", "unknown")

            with span_attrs(
                "hook.tool_end",
                agent=getattr(agent, "name", "unknown"),
                operation="tool_end",
                tool=tool_name,
                user_id=user_id
            ) as span:

                # Result is a string; summarize before logging
                try:
                    summarized = summarize(result)
                except Exception:
                    summarized = {"str": result[:200]}

                safe_update_current_span_io(
                    output={
                        "tool": tool_name,
                        "result": summarized
                    },
                    redact=True,
                )

        except Exception as e:
            # Hooks must NEVER break the main run
            mark_error(e, kind="HookError.tool_end")


