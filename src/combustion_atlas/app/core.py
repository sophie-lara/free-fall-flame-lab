"""Request models and the evidence logic behind the API (no web framework code)."""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from combustion_atlas.providers import ProviderConfig
from combustion_atlas.providers.openai_answers import OpenAIAnswerProvider
from combustion_atlas.rag.search import retrieve_conversation
from combustion_atlas.rag.store import DocumentStore

from .usage import PaidCallLimiter

LOG = logging.getLogger("combustion_atlas.app")


class HistoryTurn(BaseModel):
    """An earlier turn of the conversation, sent by the browser for follow-up questions."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(default="", max_length=4000)


class EvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=1000)
    # Earlier turns (oldest first); only the last few are used, to interpret follow-ups.
    history: list[HistoryTurn] = Field(default_factory=list, max_length=6)
    method: Literal["keyword", "dense", "hybrid"] = "keyword"
    investigation: str | None = Field(default=None, max_length=80)
    generate_answer: bool = False
    allow_provider_calls: bool = False
    # Quarantined uploads this browser made (their source IDs); searchable only by it.
    include_sources: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("include_sources")
    @classmethod
    def _source_ids(cls, value: list[str]) -> list[str]:
        import re as _re

        if any(not _re.fullmatch(r"[a-f0-9]{16}", item) for item in value):
            raise ValueError("include_sources must be 16-character source IDs")
        return value


# Greetings and other small talk get a friendly reply without searching or AI calls.
# Patterns match the whole message, so real questions are never intercepted.
_TOPIC = "flames in free fall"
_INTRO = (
    "I answer questions about NASA's microgravity combustion experiments (BASS, BASS-II, "
    "FLEX and Saffire), quoting the original reports and tables."
)
SMALL_TALK: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(hi|hello|hey|hiya|howdy|yo|greetings|hi there|hello there|hey there|"
            r"good (morning|afternoon|evening)|hi atlas|hello atlas)"
        ),
        f"Hi! {_INTRO} What would you like to know about {_TOPIC}?",
    ),
    (
        re.compile(
            r"(how are you|how are you doing|how's it going|hows it going|what's up|whats up|sup)"
        ),
        f"Doing well, thanks! What would you like to know about {_TOPIC}?",
    ),
    (
        re.compile(
            r"(thanks|thank you|thank you so much|thanks a lot|thx|ty|cheers|great|awesome|"
            r"perfect|cool|ok|okay|nice|got it)"
        ),
        f"You're welcome! Ask anything else about {_TOPIC} whenever you like.",
    ),
    (
        re.compile(
            r"(who are you|what are you|what can you do|what do you do|help|how does this work|"
            r"what is this|what is combustion atlas)"
        ),
        f"{_INTRO} Try asking how flames behave in microgravity, what a specific test "
        "measured, or to see figures from an experiment.",
    ),
    (
        re.compile(r"(bye|goodbye|see you|see ya|good night)"),
        "Thanks for visiting! Come back anytime with more questions about fire in space.",
    ),
]


def small_talk(question: str) -> str | None:
    """A friendly reply when the whole message is a greeting, thanks or similar."""
    text = re.sub(r"[\s!.,?:;)(]+", " ", question.casefold()).strip()
    text = re.sub(r"\s+(atlas|there|team|everyone|friend)$", "", text)
    if not text or len(text) > 40:
        return None
    for pattern, reply in SMALL_TALK:
        if pattern.fullmatch(text):
            return reply
    return None


def small_talk_payload(request: EvidenceRequest, reply: str) -> dict[str, object]:
    return {"question": request.question, "method": request.method, "results": [], "reply": reply}


def apply_paid_limit(
    request: EvidenceRequest, limiter: PaidCallLimiter | None, exempt: bool
) -> tuple[EvidenceRequest, dict[str, object] | None]:
    """Downgrade a paid request to free keyword search when the site limit is reached."""
    paid = request.generate_answer or request.method != "keyword"
    if not paid or limiter is None or exempt:
        return request, None
    decision = limiter.acquire()
    if decision.allowed:
        return request, None
    limited: dict[str, object] = {
        "reason": decision.reason,
        "retry_after_s": decision.retry_after_s,
        "remaining_today": decision.remaining_today,
    }
    return request.model_copy(update={"method": "keyword", "generate_answer": False}), limited


def ask_evidence(
    workspace: Atlas,
    request: EvidenceRequest,
    *,
    limiter: PaidCallLimiter | None = None,
    exempt: bool = False,
) -> dict[str, object]:
    if reply := small_talk(request.question):
        return small_talk_payload(request, reply)  # no search, no AI call, not counted
    if not workspace.database.is_file():
        raise ValueError("Build the document index to search evidence")
    if (
        request.method != "keyword" or request.generate_answer
    ) and not request.allow_provider_calls:
        raise ValueError("Enable OpenAI calls for semantic search or generated answers")
    from openai import OpenAIError

    from .streaming import answer_unavailable, charged_call, semantic_unavailable

    original = request
    request, limited = apply_paid_limit(request, limiter, exempt)
    charged = charged_call(original, limiter, exempt, limited)
    fallback = None
    with DocumentStore(workspace.read_database) as store:
        try:
            results = retrieve_conversation(
                store,
                request.question,
                [turn.question for turn in request.history],
                extra_queries=broad_queries(request),
                method=request.method,
                investigation=request.investigation or None,
                visible_sources=frozenset(request.include_sources),
            )
        except (ValueError, OpenAIError) as exc:
            if request.method == "keyword":
                raise
            fallback = semantic_unavailable(exc)
            results = retrieve_conversation(
                store,
                request.question,
                [turn.question for turn in request.history],
                method="keyword",
                investigation=request.investigation or None,
                visible_sources=frozenset(request.include_sources),
            )
    payload: dict[str, object] = {
        "question": request.question,
        "method": "keyword" if fallback else request.method,
        "results": results,
    }
    if fallback:
        payload["retrieval_fallback"] = fallback
    if limited:
        payload["limited"] = limited
    if request.generate_answer:
        try:
            provider = OpenAIAnswerProvider(ProviderConfig.from_environment())
            payload["answer"] = provider.answer(
                request.question,
                results,
                history=[turn.model_dump() for turn in request.history],
            ).model_dump()
            payload["answered_by"] = provider.answered_by()
        except (ValueError, OpenAIError) as exc:
            refund = charged and isinstance(exc, OpenAIError)
            if refund and limiter is not None:
                limiter.refund()
            payload["answer_unavailable"] = answer_unavailable(exc, refunded=refund)
    elif charged and fallback and limiter is not None:
        limiter.refund()
    return payload


def broad_queries(request: EvidenceRequest) -> list[str]:
    """Focused extra searches for broad questions when AI answers are on (else none)."""
    from combustion_atlas.rag.search import is_broad

    if (
        not (request.generate_answer and request.allow_provider_calls)
        or request.method == "keyword"
    ):
        return []
    if not is_broad(request.question):
        return []
    from combustion_atlas.providers.openai_answers import expand_query

    return expand_query(request.question)


class PaidLimitReached(Exception):
    """A paid call was refused by the site-wide limit (HTTP 429)."""

    def __init__(self, reason: str, retry_after_s: int):
        super().__init__(reason)
        self.retry_after_s = retry_after_s


MAX_UPLOAD_BYTES = 80 * 1024 * 1024


def ingest_upload(
    workspace: Atlas,
    body: bytes,
    *,
    filename: str,
    investigation: str,
    source_url: str | None,
    embed: bool,
    folder_name: str = "raw/uploads",
) -> dict[str, object]:
    """Save an uploaded PDF under data/raw/uploads and add it without replacing the index."""
    import re

    from combustion_atlas.rag.build import add_document

    if not body.startswith(b"%PDF-"):
        raise ValueError("Upload a PDF file")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.()-]{0,78}", investigation):
        raise ValueError("Investigation ID: letters, numbers, spaces, '.', '_', '-' only")
    if source_url and not re.match(r"^https?://", source_url):
        raise ValueError("Source URL must start with http:// or https://")
    sha = hashlib.sha256(body).hexdigest()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(filename).stem).strip("-.")[:60] or "upload"
    folder = workspace.data / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{stem}.pdf"
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != sha:
        target = folder / f"{stem}-{sha[:8]}.pdf"
    if not target.exists():
        target.write_bytes(body)
    report = add_document(
        target,
        investigation_id=investigation,
        source_url=source_url or None,
        processed_dir=workspace.data / "processed/rag",
        database=workspace.database,
    )
    report["embedded_chunks"] = 0
    if embed:
        from combustion_atlas.providers import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider(ProviderConfig.from_environment())
        with DocumentStore(workspace.database) as store:
            missing = [
                c
                for c in store.chunks_missing_vectors(provider.model_key)
                if c.source_id == report["source_id"]
            ]
            if missing:
                vectors = provider.embed([c.text for c in missing])
                store.append_vectors(
                    model_key=provider.model_key,
                    model=provider.model,
                    dimensions=provider.dimensions,
                    vectors={c.chunk_id: v for c, v in zip(missing, vectors, strict=True)},
                )
            report["embedded_chunks"] = len(missing)
    report["saved_as"] = target.relative_to(workspace.root).as_posix()
    return report


class Atlas:
    """A project root: data/ with raw sources, processed files and the search index.

    `database` is the shared index (writes go here). `read_database` is what reads use:
    the same file locally, or a snapshot on fast local disk when `cache_dir` is set
    (Azure keeps data on a network share where every SQLite read is a round trip).
    """

    def __init__(self, root: Path, cache_dir: Path | None = None):
        self.root = root.resolve()
        self.data = self.root / "data"
        self.database = self.data / "embeddings/rag.sqlite3"
        self.cache_dir = cache_dir

    def database_signature(self) -> tuple[int, int] | None:
        """(mtime_ns, size) of the shared index, or None when it does not exist."""
        try:
            stat = self.database.stat()
        except FileNotFoundError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    @property
    def read_database(self) -> Path:
        if self.cache_dir is None:
            return self.database
        signature = self.database_signature()
        if signature is None:
            return self.database
        return _local_snapshot(self.database, self.cache_dir, signature)

    def source_rows(self) -> list[dict[str, Any]]:
        """Every indexed source (reports and table files), keyed by source ID."""
        rows: dict[str, dict[str, Any]] = {}
        if self.database.is_file():
            with sqlite3.connect(self.read_database) as connection:
                for sid, filename, url in connection.execute(
                    "SELECT DISTINCT source_id, filename, source_url FROM chunks"
                ):
                    rows.setdefault(
                        sid, {"source_id": sid, "file_name": filename, "source_url": url}
                    )
        return list(rows.values())

    def document_path(self, source: dict[str, Any]) -> Path | None:
        """The local file whose SHA-256 starts with the source ID, under data/raw."""
        raw = (self.data / "raw").resolve()
        name = str(source["file_name"])
        for candidate in raw.rglob("*"):
            if candidate.name != name or not candidate.is_file():
                continue
            path = candidate.resolve()
            if path.is_relative_to(raw) and hashlib.sha256(
                path.read_bytes()
            ).hexdigest().startswith(str(source["source_id"])):
                return path
        return None


_SNAPSHOT_LOCK = threading.Lock()
_SNAPSHOTS: dict[Path, Path] = {}
_STALE: set[Path] = set()  # old snapshots still open when they were replaced


def _remove_stale() -> None:
    """Delete replaced snapshots; ones still open (Windows) are retried next time."""
    for old in list(_STALE):
        try:
            old.unlink(missing_ok=True)
            _STALE.discard(old)
        except OSError:
            pass


def _local_snapshot(database: Path, cache_dir: Path, signature: tuple[int, int]) -> Path:
    """A consistent copy of the shared index on local disk, refreshed when it changes.

    Uses SQLite's online backup (a transactionally consistent snapshot even while the
    shared file is being written). Each version gets its own file, so a snapshot that
    readers still have open is never overwritten or renamed over (Windows forbids that);
    older versions are deleted once nothing holds them open.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(str(database.resolve()).encode()).hexdigest()[:12]
    target = cache_dir / f"rag-{name}-{signature[0]}-{signature[1]}.sqlite3"
    with _SNAPSHOT_LOCK:
        _remove_stale()
        if _SNAPSHOTS.get(database) == target and target.is_file():
            return target
        if not target.is_file():
            partial = target.with_suffix(".partial")
            partial.unlink(missing_ok=True)
            source = sqlite3.connect(database)
            copy = sqlite3.connect(partial)
            try:
                source.backup(copy)
            finally:
                copy.close()
                source.close()
            partial.rename(target)
        _SNAPSHOTS[database] = target
        _STALE.update(old for old in cache_dir.glob(f"rag-{name}-*.sqlite3") if old != target)
        _remove_stale()
        LOG.info("refreshed local index snapshot %s", target.name)
    return target
