"""Validação estrita da resposta do modelo: cada recusa com motivo nomeado."""

from __future__ import annotations

import json
from typing import Any

import pytest

from infra.research.b3.ia_grafico.protocolo import ESQUEMA_RESPOSTA
from infra.research.b3.ia_grafico.resposta import Lado, RespostaInvalida, espelhar, validar


def _ok(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "side": "buy",
        "entry_type": "market",
        "entry_y": None,
        "stop_y": -0.30,
        "target_y": 0.45,
        "confidence": 0.6,
        "levels": [
            {
                "kind": "support",
                "y1": -0.3,
                "bars_ago1": None,
                "y2": None,
                "bars_ago2": None,
                "note": "fundo de ontem",
            },
            {
                "kind": "trendline",
                "y1": -0.8,
                "bars_ago1": 60,
                "y2": -0.2,
                "bars_ago2": 5,
                "note": "LTA",
            },
        ],
        "rationale": "fundos ascendentes e suporte segurando",
    }
    base.update(kw)
    return base


def _motivo(obj: object) -> str:
    texto = obj if isinstance(obj, str) else json.dumps(obj)
    with pytest.raises(RespostaInvalida) as e:
        validar(texto)
    return e.value.motivo


def test_compra_a_mercado_valida() -> None:
    r = validar(json.dumps(_ok()))
    assert r.lado is Lado.COMPRA and r.tipo_entrada == "market" and r.entrada_y is None
    assert (r.stop_y, r.alvo_y, r.confianca) == (-0.30, 0.45, 0.6)
    assert len(r.niveis) == 2 and r.niveis[1].tipo == "trendline"


def test_none_sem_geometria() -> None:
    r = validar(json.dumps(_ok(side="none", entry_type=None, stop_y=None, target_y=None)))
    assert r.lado is Lado.NENHUM
    assert _motivo(_ok(side="none", entry_type=None, target_y=None)) == "none_com_geometria"


@pytest.mark.parametrize(
    ("texto", "motivo"),
    [
        ("```json\n{}\n```", "nao_e_json"),
        ('ok: {"side": "buy"}', "nao_e_json"),
        ("[1, 2]", "nao_e_objeto"),
        ('{"side": "buy", "side": "sell"}', "chave_duplicada"),
        ("", "nao_e_json"),
    ],
)
def test_recusa_o_que_nao_e_json_puro(texto: str, motivo: str) -> None:
    assert _motivo(texto) == motivo


def test_recusa_chaves_faltando_ou_desconhecidas() -> None:
    sem = _ok()
    del sem["confidence"]
    assert _motivo(sem) == "chaves"
    assert _motivo(_ok(extra=1)) == "chaves"


@pytest.mark.parametrize(
    ("campos", "motivo"),
    [
        ({"side": "long"}, "lado"),
        ({"stop_y": 0.10}, "geometria"),  # stop acima da entrada numa compra
        ({"side": "sell"}, "geometria"),  # venda com stop abaixo e alvo acima
        ({"stop_y": -0.01}, "distancia_stop"),
        ({"stop_y": -3.5}, "distancia_stop"),
        ({"target_y": 5.5}, "distancia_alvo"),
        ({"confidence": 1.2}, "confianca"),
        ({"confidence": True}, "numero"),
        ({"stop_y": "-0.3"}, "numero"),
        ({"entry_type": "stop"}, "tipo_entrada"),
        ({"entry_y": -0.1}, "entrada_mercado_com_preco"),
        ({"entry_type": "limit", "entry_y": 0.1}, "limite_do_lado_errado"),
        ({"entry_type": "limit", "entry_y": None}, "limite_sem_preco"),
        ({"rationale": "x" * 601}, "racional"),
        ({"levels": [{"kind": "zona"}]}, "nivel"),
        ({"levels": [_ok()["levels"][0]] * 11}, "nivel"),
    ],
)
def test_recusas_nomeadas(campos: dict[str, Any], motivo: str) -> None:
    assert _motivo(_ok(**campos)) == motivo


def test_recusa_nan_e_infinito() -> None:
    assert _motivo('{"side": NaN}') == "nao_e_json"
    texto = json.dumps(_ok()).replace("0.45", "Infinity")
    assert _motivo(texto) == "nao_e_json"


def test_limite_de_compra_abaixo_e_geometria_relativa_a_entrada() -> None:
    r = validar(json.dumps(_ok(entry_type="limit", entry_y=-0.20, stop_y=-0.50, target_y=0.10)))
    assert r.entrada_y == -0.20
    assert _motivo(_ok(entry_type="limit", entry_y=-0.20, stop_y=-0.22, target_y=0.10)) == (
        "distancia_stop"
    )


def test_espelho_troca_lado_e_nega_a_geometria() -> None:
    r = validar(json.dumps(_ok(entry_type="limit", entry_y=-0.20, stop_y=-0.50, target_y=0.10)))
    e = espelhar(r)
    assert e.lado is Lado.VENDA and (e.entrada_y, e.stop_y, e.alvo_y) == (0.20, 0.50, -0.10)
    assert espelhar(e) == r


def test_esquema_do_codex_tem_as_mesmas_chaves_do_validador() -> None:
    assert set(ESQUEMA_RESPOSTA["properties"]) == set(_ok())
    assert set(ESQUEMA_RESPOSTA["required"]) == set(_ok())
    assert ESQUEMA_RESPOSTA["additionalProperties"] is False
