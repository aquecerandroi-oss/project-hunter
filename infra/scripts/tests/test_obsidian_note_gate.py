"""``obsidian_note_gate`` (T4.93) — pure logic, no database, no network.

Run: ``uv run pytest infra/scripts/tests/test_obsidian_note_gate.py -q``
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _load() -> ModuleType:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        "hunter_infra_obsidian_note_gate_ut", SCRIPTS_DIR / "obsidian_note_gate.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _note(tmp_path: Path, name: str, text: str) -> Path:
    note_dir = tmp_path / "obsidian" / "11-KNOWLEDGE"
    note_dir.mkdir(parents=True, exist_ok=True)
    note_path = note_dir / name
    note_path.write_text(text, encoding="utf-8")
    return note_path


def test_none_note_is_refused_note_required(tmp_path: Path) -> None:
    gate = _load()
    with pytest.raises(gate.NoteRefused, match="note_required") as excinfo:
        gate.gate(None, [["operator/5"]], repo_root=tmp_path)
    assert "operator/5" in str(excinfo.value)


def test_note_outside_obsidian_is_refused(tmp_path: Path) -> None:
    gate = _load()
    outside = tmp_path / "docs" / "note.md"
    outside.parent.mkdir(parents=True)
    outside.write_text("operator/5", encoding="utf-8")
    with pytest.raises(gate.NoteRefused, match="note_outside_obsidian"):
        gate.gate("docs/note.md", [["operator/5"]], repo_root=tmp_path)


def test_note_escaping_the_repo_with_dotdot_is_refused(tmp_path: Path) -> None:
    gate = _load()
    with pytest.raises(gate.NoteRefused, match="note_outside_obsidian"):
        gate.gate("obsidian/../secret.md", [["operator/5"]], repo_root=tmp_path)


def test_missing_file_is_refused(tmp_path: Path) -> None:
    gate = _load()
    with pytest.raises(gate.NoteRefused, match="note_missing"):
        gate.gate("obsidian/11-KNOWLEDGE/ghost.md", [["operator/5"]], repo_root=tmp_path)


def test_non_markdown_file_is_refused(tmp_path: Path) -> None:
    gate = _load()
    note_dir = tmp_path / "obsidian" / "11-KNOWLEDGE"
    note_dir.mkdir(parents=True)
    (note_dir / "note.txt").write_text("operator/5", encoding="utf-8")
    with pytest.raises(gate.NoteRefused, match="note_not_markdown"):
        gate.gate("obsidian/11-KNOWLEDGE/note.txt", [["operator/5"]], repo_root=tmp_path)


def test_note_not_mentioning_the_target_is_refused(tmp_path: Path) -> None:
    gate = _load()
    _note(tmp_path, "note.md", "discussão sobre outra coisa qualquer")
    with pytest.raises(gate.NoteRefused, match="note_does_not_mention_target"):
        gate.gate("obsidian/11-KNOWLEDGE/note.md", [["operator/5"]], repo_root=tmp_path)


def test_a_valid_note_mentioning_the_target_case_insensitively_is_accepted(
    tmp_path: Path,
) -> None:
    gate = _load()
    _note(tmp_path, "note.md", "# EXP-M24\n\nRevisão de OPERATOR/5 concluída.")
    proof = gate.gate("obsidian/11-KNOWLEDGE/note.md", [["operator/5"]], repo_root=tmp_path)
    assert proof.path == "obsidian/11-KNOWLEDGE/note.md"
    assert len(proof.sha256) == 64
    # git_blob_sha is best-effort (``git hash-object`` needs no repository at
    # all, just the git binary): a 40-char hex digest when git is on PATH,
    # None only if it isn't.
    assert proof.git_blob_sha is None or len(proof.git_blob_sha) == 40


def test_one_spelling_per_group_is_enough(tmp_path: Path) -> None:
    gate = _load()
    _note(tmp_path, "note.md", "fala de momentum/v1 aqui")
    proof = gate.gate(
        "obsidian/11-KNOWLEDGE/note.md", [["momentum v1", "momentum/v1"]], repo_root=tmp_path
    )
    assert proof.path == "obsidian/11-KNOWLEDGE/note.md"


def test_every_group_must_be_covered_not_just_one(tmp_path: Path) -> None:
    """T4.93 review (Astra): a batch ``--set-param --all-active`` must not be
    justified by a note that covers only one of several changed rule sets."""
    gate = _load()
    _note(tmp_path, "note.md", "fala só de operator/5 aqui")
    with pytest.raises(gate.NoteRefused, match="note_does_not_mention_target") as excinfo:
        gate.gate(
            "obsidian/11-KNOWLEDGE/note.md", [["operator/5"], ["flow_v2/6"]], repo_root=tmp_path
        )
    assert "flow_v2/6" in str(excinfo.value)


def test_a_dotted_suffix_does_not_satisfy_the_base_versions_check(tmp_path: Path) -> None:
    """T4.93 review round 2 (Astra): ``momentum v1.1`` must not stand in for
    ``momentum v1`` — a version identifier routinely continues with a dot."""
    gate = _load()
    _note(tmp_path, "note.md", "ativação de momentum v1.1 concluída")
    with pytest.raises(gate.NoteRefused, match="note_does_not_mention_target"):
        gate.gate(
            "obsidian/11-KNOWLEDGE/note.md", [["momentum v1", "momentum/v1"]], repo_root=tmp_path
        )


def test_a_hyphenated_suffix_does_not_satisfy_the_base_versions_check(tmp_path: Path) -> None:
    """Same review: ``momentum v2-irma-03`` must not stand in for ``momentum v2``."""
    gate = _load()
    _note(tmp_path, "note.md", "linha irmã: momentum v2-irma-03")
    with pytest.raises(gate.NoteRefused, match="note_does_not_mention_target"):
        gate.gate(
            "obsidian/11-KNOWLEDGE/note.md", [["momentum v2", "momentum/v2"]], repo_root=tmp_path
        )


def test_a_sentence_ending_period_still_lets_the_mention_count(tmp_path: Path) -> None:
    """The stricter boundary must not make ordinary prose fail: a mention at
    the end of a sentence (target immediately followed by ``.`` then a space
    or end of text) is still a real mention, not a dotted-suffix false
    positive."""
    gate = _load()
    _note(tmp_path, "note.md", "Revisão concluída para operator/5.")
    proof = gate.gate("obsidian/11-KNOWLEDGE/note.md", [["operator/5"]], repo_root=tmp_path)
    assert proof.path == "obsidian/11-KNOWLEDGE/note.md"


def test_a_longer_label_does_not_satisfy_a_shorter_ones_check(tmp_path: Path) -> None:
    """``operator/50`` must not stand in for ``operator/5`` (word boundary,
    not a bare substring search)."""
    gate = _load()
    _note(tmp_path, "note.md", "revisão de operator/50")
    with pytest.raises(gate.NoteRefused, match="note_does_not_mention_target"):
        gate.gate("obsidian/11-KNOWLEDGE/note.md", [["operator/5"]], repo_root=tmp_path)


def test_an_unrelated_versions_note_does_not_satisfy_a_bare_version_alone(tmp_path: Path) -> None:
    """A note about ``volume_anomaly v1`` must not free ``momentum v1``: a
    compound spelling (key *and* version together) is required, not the bare
    version alone."""
    gate = _load()
    _note(tmp_path, "note.md", "ativação de volume_anomaly v1 concluída")
    with pytest.raises(gate.NoteRefused, match="note_does_not_mention_target"):
        gate.gate(
            "obsidian/11-KNOWLEDGE/note.md", [["momentum v1", "momentum/v1"]], repo_root=tmp_path
        )


def test_a_symlinked_note_escaping_the_vault_is_refused(tmp_path: Path) -> None:
    gate = _load()
    outside = tmp_path / "outside.md"
    outside.write_text("operator/5", encoding="utf-8")
    note_dir = tmp_path / "obsidian" / "11-KNOWLEDGE"
    note_dir.mkdir(parents=True)
    link = note_dir / "escape.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks need elevated privileges on this machine")
    with pytest.raises(gate.NoteRefused, match="note_outside_obsidian"):
        gate.gate("obsidian/11-KNOWLEDGE/escape.md", [["operator/5"]], repo_root=tmp_path)


def test_the_hash_matches_the_exact_bytes_checked_for_the_mention(tmp_path: Path) -> None:
    import hashlib

    gate = _load()
    note_path = _note(tmp_path, "note.md", "fala de operator/5 aqui")
    proof = gate.gate("obsidian/11-KNOWLEDGE/note.md", [["operator/5"]], repo_root=tmp_path)
    assert proof.sha256 == hashlib.sha256(note_path.read_bytes()).hexdigest()


def test_describe_required_note_names_one_spelling_per_group() -> None:
    gate = _load()
    message = gate.describe_required_note([["operator/5"], ["flow_v2/6", "flow_v2 6"]])
    assert "operator/5" in message and "flow_v2/6" in message and "--note" in message


def test_provenance_helpers_shape_the_proof() -> None:
    gate = _load()
    proof = gate.NoteProof(path="obsidian/x.md", sha256="a" * 64, git_blob_sha=None)
    tag = gate.provenance_note(proof)
    assert "obsidian/x.md" in tag and "sha256=" in tag and "indisponivel" in tag
    data = gate.provenance_data(proof)
    assert data == {"note": "obsidian/x.md", "note_sha256": "a" * 64, "note_git_blob_sha": None}


def test_default_repo_root_finds_the_real_obsidian_folder() -> None:
    gate = _load()
    assert (gate.default_repo_root() / "obsidian" / "11-KNOWLEDGE").is_dir()
