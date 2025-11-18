def aggregate_tokens_from_run(turn) -> tuple[int, int, int]:
    """
    Extract (input_tokens, output_tokens, total_tokens) from a RunResult.
    Matches Agents SDK shape: turn.raw_responses[i].usage.{input_tokens,...}
    """
    input_total = 0
    output_total = 0
    total_total = 0

    raw = getattr(turn, "raw_responses", None)
    if isinstance(raw, list):
        for rr in raw:
            if not isinstance(rr, dict):
                continue
            usage = rr.get("usage")
            if not isinstance(usage, dict):
                continue
            inp = usage.get("input_tokens", 0) or 0
            out = usage.get("output_tokens", 0) or 0
            tot = usage.get("total_tokens", inp + out) or 0

            input_total += int(inp)
            output_total += int(out)
            total_total += int(tot)

    return input_total, output_total, total_total
