"""A linha de comando da leitura: recusa sem a impressão digital registrada, recusa export
tirado antes de L ou depois de L + 1 h, não aceita outro número de réplicas e imprime o
relatório com a impressão digital e o ambiente."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from infra.research.exp_m26.calendario import LeituraAntecipada
from infra.research.exp_m26.impressao_digital import impressao
from infra.research.exp_m26.leitura import ExportForaDaJanela
from infra.research.exp_m26.ler import main
from infra.research.exp_m26.tests.test_carga import linhas_export, op_export

# seed 2026-09-29 12:00Z → T0 10-01 12:00 → sem metas, corte no dia 21 = 10-23 00:00Z,
# leitura 10-23 02:00Z.
NO_PRAZO = json.dumps(
    {
        "tipo": "meta",
        "exportado_em": "2026-10-23T02:30:00+00:00",
        "escritoras_abertas_desde": None,
        "escritoras_sem_inicio": 0,
        "preparadas": 0,
        "relogio_recuou_s": 0,
        "ve_toda_atividade": True,
    }
)


def _export(tmp_path: Path, meta: str = NO_PRAZO) -> Path:
    p = tmp_path / "h022.jsonl"
    p.write_text("\n".join(linhas_export(op_export(), meta=meta)) + "\n", encoding="utf-8")
    return p


def test_recusa_impressao_diferente(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--export", str(_export(tmp_path)), "--impressao", "0" * 64])
    assert rc == 2
    assert "não bate" in capsys.readouterr().err


def test_recusa_export_antes_da_leitura(tmp_path: Path) -> None:
    cedo = json.dumps({"tipo": "meta", "exportado_em": "2026-10-23T01:59:00+00:00"})
    with pytest.raises(LeituraAntecipada):
        main(["--export", str(_export(tmp_path, cedo)), "--impressao", impressao()])


def test_recusa_export_tardio(tmp_path: Path) -> None:
    tarde = json.dumps({"tipo": "meta", "exportado_em": "2026-10-23T03:00:01+00:00"})
    with pytest.raises(ExportForaDaJanela):
        main(["--export", str(_export(tmp_path, tarde)), "--impressao", impressao()])


def test_nao_ha_como_mudar_as_replicas(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--export", str(_export(tmp_path)), "--impressao", impressao(), "--reps", "100"])


def test_imprime_o_relatorio(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--export", str(_export(tmp_path)), "--impressao", impressao()])
    assert rc == 0
    rel = json.loads(capsys.readouterr().out)
    assert rel["impressao_digital"] == impressao()
    assert rel["export_sha256"] == hashlib.sha256(_export(tmp_path).read_bytes()).hexdigest()
    assert rel["reps"] == 10_000
    assert set(rel["ambiente"]) == {"python", "numpy"}
    assert rel["hipotese"] == "H-022"
    assert rel["corte"]["motivo"] == "dia_21"
    assert rel["primaria"]["categoria"] == "instrumento"
