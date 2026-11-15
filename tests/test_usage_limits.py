"""Site-wide paid-call limit: daily cap, spacing, persistence and request fallback."""

from datetime import UTC, datetime
from pathlib import Path

from combustion_atlas.app.core import EvidenceRequest, apply_paid_limit
from combustion_atlas.app.usage import PaidCallLimiter

NOON = datetime(2026, 11, 15, 12, 0, tzinfo=UTC).timestamp()


def test_daily_cap_and_spacing_persist_and_reset(tmp_path: Path) -> None:
    path = tmp_path / "usage/paid.json"
    limiter = PaidCallLimiter(path, daily_limit=2, min_interval_s=60)
    assert limiter.acquire(NOON).allowed
    spaced = limiter.acquire(NOON + 10)
    assert not spaced.allowed and "one per minute" in (spaced.reason or "")
    assert spaced.retry_after_s == 51
    assert limiter.acquire(NOON + 61).remaining_today == 0
    # A restarted server reads the same state from disk.
    restarted = PaidCallLimiter(path, daily_limit=2, min_interval_s=60)
    capped = restarted.acquire(NOON + 200)
    assert not capped.allowed and "daily limit of 2" in (capped.reason or "")
    assert restarted.status(NOON + 200)["remaining_today"] == 0
    tomorrow = datetime(2026, 11, 16, 0, 1, tzinfo=UTC).timestamp()
    assert restarted.acquire(tomorrow).allowed  # resets at 00:00 UTC
    assert not PaidCallLimiter(tmp_path / "x.json").enabled  # 0 = unlimited


def test_limited_answers_fall_back_to_free_keyword_search(tmp_path: Path) -> None:
    limiter = PaidCallLimiter(tmp_path / "paid.json", daily_limit=1)
    request = EvidenceRequest(
        question="flame spread", method="hybrid", generate_answer=True, allow_provider_calls=True
    )
    first, limited = apply_paid_limit(request, limiter, exempt=False)
    assert limited is None and first.generate_answer
    second, limited = apply_paid_limit(request, limiter, exempt=False)
    assert limited is not None and "daily limit" in str(limited["reason"])
    assert second.method == "keyword" and not second.generate_answer
    admin, limited = apply_paid_limit(request, limiter, exempt=True)
    assert limited is None and admin.generate_answer  # admins are not counted
    keyword = EvidenceRequest(question="flame spread")
    assert apply_paid_limit(keyword, limiter, exempt=False)[1] is None  # free search
