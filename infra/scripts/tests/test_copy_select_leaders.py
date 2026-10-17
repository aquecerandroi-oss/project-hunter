"""``copy_select_leaders.py`` — the CLI that freezes the pilot's leader list.

End to end over ``httpx.MockTransport`` with labelled synthetic boards: the
frozen JSON (rule text + sha256, per-response times, list sha256, strata), the
request budget, ``--dry-run``, the refusal to overwrite a cohort, and what
happens on 429. Nothing touches a socket, a database or ``.env``.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for extra in (SCRIPTS_DIR, SCRIPTS_DIR / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import copy_leaders_rule as rule  # noqa: E402
import copy_select_leaders as cli  # noqa: E402
from copy_leaders_rig import PERSONAL_MARKER, FakeApi, addr, wire_board, wire_entry  # noqa: E402

NOW = datetime(2026, 10, 9, 15, 30, 5, tzinfo=UTC)


def boards_for(n: int) -> dict[tuple[str, str], dict[str, Any]]:
    """Complete views (100 rows): ``n`` real wallets, the rest losing fillers."""
    wallets = [wire_entry(addr(i), rank=i + 1, verified=i % 2 == 0) for i in range(n)]

    def view(real: list[dict[str, Any]]) -> dict[str, Any]:
        fillers = [
            wire_entry(addr(1000 + i), realized="-1", unrealized="0")
            for i in range(100 - len(real))
        ]
        return wire_board(real + fillers)

    out: dict[tuple[str, str], dict[str, Any]] = {}
    for period in ("daily", "weekly", "monthly"):
        for sort in ("combined", "realized"):
            out[(period, sort)] = view(wallets if period != "daily" else wallets[:3])
    return out


def run(api: FakeApi, out_dir: Path, *argv: str) -> int:
    return cli.main(
        ["--out-dir", str(out_dir), *argv],
        client=api.client(),
        now=lambda: NOW,
        sleep=lambda s: None,
    )


def files(out_dir: Path) -> list[Path]:
    return sorted(out_dir.glob("leaders-*.json")) if out_dir.exists() else []


def no_floats(text: str) -> dict[str, Any]:
    def refuse(token: str) -> object:
        raise AssertionError(f"float in the frozen file: {token}")

    return json.loads(text, parse_float=refuse)


def test_freezes_the_top_twenty_with_everything_a_future_verdict_needs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    api = FakeApi(boards_for(25), {addr(i): 100 + i for i in range(25)})
    assert run(api, tmp_path) == 0

    (path,) = files(tmp_path)
    assert path.name == "leaders-20261009T153005Z.json"
    text = path.read_text(encoding="utf-8")
    doc = no_floats(text)
    assert doc["schema"] == "copy-leaders/1"
    assert doc["known_at"] == "2026-10-09T15:30:05.000Z"
    assert (
        doc["rule"]["sha256"]
        == rule.RULE_SHA256
        == hashlib.sha256(doc["rule"]["text"].encode()).hexdigest()
    )
    assert doc["rule"]["version"] == rule.RULE_VERSION
    assert [w["address"] for w in doc["wallets"]] == [addr(i) for i in range(20)]
    first = doc["wallets"][0]
    assert first["stratum"] == "regra" and first["rule_rank"] == 1
    assert first["realized_pnl_sol"] == "10.0" and first["is_verified"] is True
    assert first["followers"] == {
        "count": 100,
        "read_at": "2026-10-09T15:30:05.000Z",
        "status": "ok",
    }
    canonical = json.dumps(doc["wallets"], sort_keys=True, separators=(",", ":"))
    assert doc["list_sha256"] == hashlib.sha256(canonical.encode()).hexdigest()
    assert doc["requests"] == {"used": 26, "budget": 30, "stop_reason": None}
    assert len(api.requests) == 26
    assert len(doc["responses"]) == 26  # 6 views + 20 follower reads, every one recorded
    assert doc["responses"][0]["endpoint"] == "/pnl-leaderboard"
    assert doc["responses"][0]["window_start_sec"] == 1_789_900_000
    assert len(doc["responses"][0]["body_sha256"]) == 64
    assert doc["responses"][6]["endpoint"] == f"/users/{addr(0)}"
    assert doc["funnel"]["eligible"] == 25 and doc["funnel"]["rule_selected"] == 20
    assert doc["funnel"]["wallets_seen"] == 122 and len(doc["evaluated"]) == 122
    kept = next(e for e in doc["evaluated"] if e["address"] == addr(0))
    assert kept["eligible"] is True and len(kept["rows"]) == 6  # the rows behind every filter
    assert kept["rows"][0]["board"] in {"daily:combined", "daily:realized"}
    dropped = next(e for e in doc["evaluated"] if e["address"] == addr(1000))
    assert dropped["reject_reason"] == "realized_not_positive"
    body = {k: v for k, v in doc.items() if k != "content_sha256"}
    canonical_doc = json.dumps(body, sort_keys=True, separators=(",", ":"))
    assert doc["content_sha256"] == hashlib.sha256(canonical_doc.encode()).hexdigest()
    # public addresses and numbers only
    assert PERSONAL_MARKER not in text
    assert "username" not in text.lower() and "profile" not in text.lower()

    out = capsys.readouterr().out
    assert rule.RULE_SHA256 in out and "REGRA copy-leaders-rule/1" in out
    assert doc["list_sha256"] in out
    assert addr(0) not in out  # the screen shows truncated addresses only
    assert addr(0)[:4] + ".." + addr(0)[-4:] in out


def test_dry_run_prints_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    api = FakeApi(boards_for(25), {addr(i): 1 for i in range(25)})
    out_dir = tmp_path / "copy-pilot"
    assert run(api, out_dir, "--dry-run") == 0
    assert files(out_dir) == [] and not out_dir.exists()
    out = capsys.readouterr().out
    assert "DRY-RUN" in out


def test_includes_are_tagged_and_the_budget_still_fits(tmp_path: Path) -> None:
    included = [addr(100 + i) for i in range(4)]
    api = FakeApi(boards_for(25), {addr(i): i for i in range(130)})
    argv = [arg for a in included for arg in ("--include", a)]
    assert run(api, tmp_path, *argv) == 0
    doc = json.loads(files(tmp_path)[0].read_text(encoding="utf-8"))
    assert len(doc["wallets"]) == 24
    tagged = [w for w in doc["wallets"] if w["stratum"] == "escolha_everton"]
    assert [w["address"] for w in tagged] == included
    assert all(w["rule_selected"] is False and w["boards"] == [] for w in tagged)
    assert all(w["everton_pick"] is True for w in tagged)
    assert not any(w["everton_pick"] for w in doc["wallets"] if w["stratum"] == "regra")
    assert len(api.requests) == 30 == doc["requests"]["used"]


def test_an_invalid_or_excess_include_sends_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    api = FakeApi(boards_for(25))
    assert run(api, tmp_path, "--include", "0xnot-solana") == 64
    assert run(api, tmp_path, *[x for i in range(5) for x in ("--include", addr(i))]) == 64
    assert api.requests == [] and files(tmp_path) == []
    assert "--include" in capsys.readouterr().err


def test_a_written_cohort_is_never_overwritten_or_replaced_silently(tmp_path: Path) -> None:
    api = FakeApi(boards_for(25), {addr(i): 1 for i in range(25)})
    assert run(api, tmp_path) == 0
    (first,) = files(tmp_path)
    before = first.read_bytes()

    again = FakeApi(boards_for(25), {addr(i): 1 for i in range(25)})
    assert run(again, tmp_path) == 4
    assert again.requests == []  # refused before the first request
    assert first.read_bytes() == before

    later = FakeApi(boards_for(25), {addr(i): 1 for i in range(25)})
    code = cli.main(
        ["--out-dir", str(tmp_path), "--new-cohort", "rule v2 after review"],
        client=later.client(),
        now=lambda: datetime(2026, 10, 10, 1, 0, 0, tzinfo=UTC),
        sleep=lambda s: None,
    )
    assert code == 0
    second = files(tmp_path)[-1]
    assert second != first and first.read_bytes() == before
    doc = json.loads(second.read_text(encoding="utf-8"))
    old = json.loads(before)
    assert doc["supersedes"] == {
        "file": first.name,
        "list_sha256": old["list_sha256"],
        "reason": "rule v2 after review",
    }
    assert doc["cohort_id"] != old["cohort_id"]


def test_a_stop_status_on_a_board_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    api = FakeApi(boards_for(25), override=lambda r: httpx.Response(429))
    assert run(api, tmp_path) == 2
    assert len(api.requests) == 1
    assert files(tmp_path) == []
    assert "http_429" in capsys.readouterr().err


def test_a_429_on_followers_still_freezes_the_list_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def override(request: httpx.Request) -> httpx.Response | None:
        return httpx.Response(429) if request.url.path.endswith(addr(2)) else None

    api = FakeApi(boards_for(25), {addr(i): 7 for i in range(25)}, override=override)
    assert run(api, tmp_path) == 3
    doc = json.loads(files(tmp_path)[0].read_text(encoding="utf-8"))
    statuses = [w["followers"]["status"] for w in doc["wallets"]]
    assert statuses[:2] == ["ok", "ok"]
    assert statuses[2] == "http_429"  # the wallet that got the 429 itself
    assert set(statuses[3:]) == {"not_read:http_429"}  # never asked
    assert all(w["followers"]["count"] is None for w in doc["wallets"][2:])
    assert doc["requests"]["stop_reason"] == "http_429"
    assert len(api.requests) == 6 + 3
    assert "http_429" in capsys.readouterr().err


def test_an_empty_selection_is_not_written(tmp_path: Path) -> None:
    board = wire_board([wire_entry(addr(i), positions=1) for i in range(100)])
    api = FakeApi(
        {(p, s): board for p in ("daily", "weekly", "monthly") for s in ("combined", "realized")}
    )
    assert run(api, tmp_path) == 5
    assert files(tmp_path) == []
    assert len(api.requests) == 6  # nothing to read followers for


def test_the_script_never_references_the_database_or_env() -> None:
    source = "".join(
        (SCRIPTS_DIR / name).read_text(encoding="utf-8")
        for name in (
            "copy_select_leaders.py",
            "copy_leaders_http.py",
            "copy_leaders_rule.py",
            "copy_leaders_doc.py",
        )
    )
    for forbidden in (
        "sqlalchemy",
        "psycopg",
        "asyncpg",
        "os.environ",
        ".env",
        "getenv",
        "Authorization",
        "Cookie",
    ):
        assert forbidden not in source, forbidden


def test_a_truncated_view_never_selects_anything(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    boards = boards_for(25)
    boards[("weekly", "realized")] = wire_board([wire_entry(addr(i)) for i in range(40)])
    api = FakeApi(boards)
    assert run(api, tmp_path) == 2
    assert files(tmp_path) == []
    assert "weekly:realized" in capsys.readouterr().err


def test_the_boundary_is_stamped_in_milliseconds_rounded_up() -> None:
    import copy_leaders_doc as doc_module

    early = datetime(2026, 10, 9, 4, 47, 0, 900_100, tzinfo=UTC)
    assert doc_module.iso_ceil(early) == "2026-10-09T04:47:00.901Z"
    exact = datetime(2026, 10, 9, 4, 47, 0, 900_000, tzinfo=UTC)
    assert doc_module.iso_ceil(exact) == "2026-10-09T04:47:00.900Z"
    edge = datetime(2026, 10, 9, 4, 47, 0, 999_500, tzinfo=UTC)
    assert doc_module.iso_ceil(edge) == "2026-10-09T04:47:01.000Z"


def test_the_same_includes_in_any_order_freeze_the_same_list(tmp_path: Path) -> None:
    picks = [addr(100), addr(101), addr(102)]
    users = {addr(i): i for i in range(130)}
    hashes: list[str] = []
    for index, order in enumerate((picks, list(reversed(picks)))):
        out = tmp_path / str(index)
        api = FakeApi(boards_for(25), users)
        argv = [arg for a in order for arg in ("--include", a)]
        assert run(api, out, *argv) == 0
        doc = json.loads(files(out)[0].read_text(encoding="utf-8"))
        hashes.append(doc["list_sha256"])
        assert [w["address"] for w in doc["wallets"][20:]] == picks
        assert api.paths[-3:] == [f"/users/{a}" for a in picks]
    assert hashes[0] == hashes[1]


def test_cohort_id_file_name_and_known_at_come_from_the_same_rounded_up_instant(
    tmp_path: Path,
) -> None:
    edge = datetime(2026, 10, 9, 15, 30, 5, 999_500, tzinfo=UTC)
    api = FakeApi(boards_for(25), {addr(i): 1 for i in range(25)})
    code = cli.main(
        ["--out-dir", str(tmp_path)], client=api.client(), now=lambda: edge, sleep=lambda s: None
    )
    assert code == 0
    (path,) = files(tmp_path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["known_at"] == doc["t0_not_before"] == "2026-10-09T15:30:06.000Z"
    assert doc["cohort_id"] == "copy-pilot-20261009T153006Z"
    assert path.name == "leaders-20261009T153006Z.json"


def test_a_corrupt_predecessor_is_a_clear_refusal_not_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "leaders-20261009T000000Z.json").write_text('{"schema": "copy-le', encoding="utf-8")
    api = FakeApi(boards_for(25))
    assert run(api, tmp_path, "--new-cohort", "after a torn write") == 4
    assert api.requests == []
    assert "leaders-20261009T000000Z.json" in capsys.readouterr().err


def test_a_predecessor_whose_list_hash_does_not_match_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    api = FakeApi(boards_for(25), {addr(i): 1 for i in range(25)})
    assert run(api, tmp_path) == 0
    (first,) = files(tmp_path)
    doc = json.loads(first.read_text(encoding="utf-8"))
    doc["wallets"][0]["address"] = addr(999)
    first.write_text(json.dumps(doc), encoding="utf-8")
    later = FakeApi(boards_for(25))
    assert run(later, tmp_path, "--new-cohort", "x") == 4
    assert later.requests == []
    assert "list_sha256" in capsys.readouterr().err


def test_publishing_is_atomic_write_once_and_leaves_no_temp_file(tmp_path: Path) -> None:
    import copy_leaders_doc as doc_module

    document = {"cohort_id": "copy-pilot-20261009T044701Z", "list_sha256": "x"}
    path = doc_module.write_frozen(tmp_path, document)
    assert path.name == "leaders-20261009T044701Z.json"
    assert json.loads(path.read_text(encoding="utf-8")) == document
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        doc_module.write_frozen(tmp_path, {**document, "list_sha256": "y"})
    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == [path.name]  # no temp left behind


def test_a_failed_write_publishes_nothing(tmp_path: Path) -> None:
    import copy_leaders_doc as doc_module

    bad = {"cohort_id": "copy-pilot-20261009T044701Z", "value": object()}
    with pytest.raises(TypeError):
        doc_module.write_frozen(tmp_path, bad)
    assert list(tmp_path.iterdir()) == []
