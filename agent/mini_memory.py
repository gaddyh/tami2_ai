# mini_memory.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, List, Dict, Any, Optional, Literal
import math
import time
import asyncio

Role = Literal["system", "user", "assistant", "tool"]

# ---- Interfaces we rely on from Agents SDK sessions ----
# session.get_items(limit: int | None) -> list[dict]
# session.add_items(items: list[dict]) -> None
# session.clear_session() -> None
#
# Items are plain dicts; we’ll use a consistent shape:
#   { "role": Role, "content": str, "meta": {...}, "ts": float }
# Summary checkpoints are system messages with meta.kind == "tami.summary.v1"

@dataclass
class MemoryPolicy:
    hard_token_budget: int = 10000         # total tokens to load (summary + recent turns)
    max_recent_turns: int = 40            # safety cap on raw turns
    summary_every_n_turns: int = 80       # create/update summary after this many new turns
    min_gap_between_summaries_sec: int = 60  # avoid rapid re-summarization
    summary_tag: str = "tami.summary.v1"

TokenCounter = Callable[[str], int]
Summarizer = Callable[[str], str]

def default_token_counter(text: str) -> int:
    # Cheap heuristic ~4 chars per token. Replace with tiktoken if you want.
    return max(1, math.ceil(len(text) / 4))

class MiniMemoryManager:
    def __init__(
        self,
        session,
        policy: MemoryPolicy = MemoryPolicy(),
        token_counter: TokenCounter = default_token_counter,
        summarizer: Optional[Summarizer] = None,
    ):
        self.session = session
        self.policy = policy
        self.count_tokens = token_counter
        self.summarize_fn = summarizer

    async def aload_context(self) -> List[Dict[str, Any]]:
        """Async: [summary] + [recent turns], budget-aware."""
        items = await self._a_all_items()
        summary = self._latest_summary(items)
        recent = self._recent_non_summary(items)

        context: List[Dict[str, Any]] = []
        total = 0

        if summary:
            context.append(summary)
            total += self._tokens(summary)

        bucket: List[Dict[str, Any]] = []
        for msg in reversed(recent):
            t = self._tokens(msg)
            if total + t > self.policy.hard_token_budget:
                break
            bucket.append(msg)
            total += t
            if len(bucket) >= self.policy.max_recent_turns:
                break

        context.extend(reversed(bucket))
        return context

    async def aappend_items(self, items: List[Dict[str, Any]]) -> None:
        await self.session.add_items(items)

    async def amaybe_checkpoint(self):
        if not self.summarize_fn:
            return

        items = await self._a_all_items()
        non_summary = self._recent_non_summary(items)
        summary = self._latest_summary(items)

        if summary and (time.time() - summary.get("ts", 0) < self.policy.min_gap_between_summaries_sec):
            return

        need_by_count = len(non_summary) >= self.policy.summary_every_n_turns
        need_by_tokens = self._tokens_bulk(non_summary) > self.policy.hard_token_budget * 1.5
        if not (need_by_count or need_by_tokens):
            return

        m = min(len(non_summary), 200)
        raw_text = self._flatten(non_summary[-m:])
        summary_text = self.summarize_fn(raw_text).strip()
        if not summary_text:
            return

        keep_recent_from_tail = min(len(non_summary), 12)
        new_items = [self._summary_item(summary_text), *non_summary[-keep_recent_from_tail:]]

        await self.session.clear_session()
        await self.session.add_items(new_items)

    # --- internal async fetch ---

    async def _a_all_items(self) -> List[Dict[str, Any]]:
        get = getattr(self.session, "get_items", None)
        if get is None:
            return []
        # If session.get_items is async (it is in your stack), just await it.
        if asyncio.iscoroutinefunction(get):
            try:
                items = await get(None)
            except TypeError:
                items = await get(10_000)
            return list(items)
        # Fallback to sync sessions if ever used
        try:
            return list(get(None))
        except TypeError:
            return list(get(10_000))



    # --------- Public API you’ll call from your agent boundary ----------

    def load_context(self) -> List[Dict[str, Any]]:
        """
        Load: [latest summary (if any)] + [last N turns trimmed to budget].
        """
        items = self._all_items()
        summary = self._latest_summary(items)
        recent = self._recent_non_summary(items)

        context: List[Dict[str, Any]] = []
        total = 0

        if summary:
            context.append(summary)
            total += self._tokens(summary)

        # Add recent turns from the end backwards until we hit the budget / caps
        bucket: List[Dict[str, Any]] = []
        for msg in reversed(recent):
            t = self._tokens(msg)
            if total + t > self.policy.hard_token_budget:
                break
            bucket.append(msg)
            total += t
            if len(bucket) >= self.policy.max_recent_turns:
                break

        context.extend(reversed(bucket))
        return context

    def append_user(self, text: str, meta: Optional[dict] = None):
        self._append("user", text, meta or {})

    def append_assistant(self, text: str, meta: Optional[dict] = None):
        self._append("assistant", text, meta or {})

    def append_tool(self, text: str, meta: Optional[dict] = None):
        self._append("tool", text, meta or {})

    def maybe_checkpoint(self):
        """
        If we crossed the 'summary_every_n_turns' or tokens are bloated, build/refresh a summary
        and compact the session to [summary + last K].
        """
        if not self.summarize_fn:
            return  # summarization disabled

        items = self._all_items()
        non_summary = self._recent_non_summary(items)
        summary = self._latest_summary(items)

        # Guard: avoid re-summarizing too frequently
        if summary and (time.time() - summary.get("ts", 0) < self.policy.min_gap_between_summaries_sec):
            return

        # Decide if we need a checkpoint
        need_by_count = len(non_summary) >= self.policy.summary_every_n_turns
        need_by_tokens = self._tokens_bulk(non_summary) > self.policy.hard_token_budget * 1.5

        if not (need_by_count or need_by_tokens):
            return

        # Build input to summarizer: keep it bounded to avoid huge prompt
        # Use last M messages to produce a global summary (M ~ 200 or token-bounded)
        m = min(len(non_summary), 200)
        raw_text = self._flatten(non_summary[-m:])

        summary_text = self.summarize_fn(raw_text).strip()
        if not summary_text:
            return

        # Compact session: keep summary + last few recent turns (so context stays sharp)
        # We rebuild the session content deterministically.
        keep_recent_from_tail = min(len(non_summary), 12)
        new_items: List[Dict[str, Any]] = [
            self._summary_item(summary_text),
            *non_summary[-keep_recent_from_tail:],
        ]

        self.session.clear_session()
        self.session.add_items(new_items)

    # ----------------- Internals -----------------

    def _append(self, role: Role, text: str, meta: dict):
        item = {"role": role, "content": text, "meta": meta, "ts": time.time()}
        self.session.add_items([item])

    def _summary_item(self, content: str) -> Dict[str, Any]:
        return {
            "role": "system",
            "content": content,
            "meta": {"kind": self.policy.summary_tag, "version": 1},
            "ts": time.time(),
        }

    import asyncio

    async def _aget_items_safe(self, limit=None):
        """Async helper for sessions with async get_items"""
        try:
            items = await self.session.get_items(limit)
        except TypeError:
            items = await self.session.get_items(10_000)
        return list(items)

    def _all_items(self):
        """Fetch all items; works for both sync and async sessions."""
        get = getattr(self.session, "get_items", None)
        if not get:
            return []
        # if coroutine
        if asyncio.iscoroutinefunction(get):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                # running inside async context (Agents SDK)
                # must be awaited by caller
                return asyncio.run_coroutine_threadsafe(
                    self._aget_items_safe(None), loop
                ).result()
            else:
                return asyncio.run(self._aget_items_safe(None))
        # fallback sync
        try:
            return list(get(None))
        except TypeError:
            return list(get(10_000))


    def _latest_summary(self, items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for itm in reversed(items):
            if itm.get("role") == "system" and itm.get("meta", {}).get("kind") == self.policy.summary_tag:
                return itm
        return None

    def _recent_non_summary(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [i for i in items if not (i.get("role") == "system" and i.get("meta", {}).get("kind") == self.policy.summary_tag)]

    def _flatten(self, items: List[Dict[str, Any]]) -> str:
        # Simple concatenation preserving roles; tweak if you want JSONL.
        lines = []
        for i in items:
            r = i.get("role", "?")
            c = (i.get("content") or "").strip()
            if c:
                lines.append(f"{r.upper()}: {c}")
        return "\n\n".join(lines)

    def _tokens(self, item: Dict[str, Any]) -> int:
        return self.count_tokens(item.get("content") or "")

    def _tokens_bulk(self, items: List[Dict[str, Any]]) -> int:
        return sum(self._tokens(i) for i in items)
