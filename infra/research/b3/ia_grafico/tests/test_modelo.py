"""Cliente do modelo: o falso, a política "primeira resposta válida em até duas tentativas"
e o adaptador do Codex em dry-run (nenhuma rede, nenhuma chamada real nestes testes)."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from infra.research.b3.ia_grafico.codex_cliente import (
    ClienteCodex,
    ConfigCodex,
    ExecucaoDesligada,
    ler_eventos,
)
from infra.research.b3.ia_grafico.modelo import ClienteFalso, Pedido, RespostaCrua, chamar
from infra.research.b3.ia_grafico.resposta import Lado

VALIDA = json.dumps(
    {
        "side": "sell",
        "entry_type": "market",
        "entry_y": None,
        "stop_y": 0.3,
        "target_y": -0.4,
        "confidence": 0.5,
        "levels": [],
        "rationale": "topo duplo",
    }
)
PEDIDO = Pedido(png=b"\x89PNG-sintetico", texto="prompt")


def _relogio() -> Iterator[datetime]:
    t = datetime(2026, 10, 17, 12, tzinfo=UTC)
    while True:
        yield t
        t += timedelta(seconds=1)


def _falso(*respostas: str, eventos: int = 0) -> ClienteFalso:
    fila = list(respostas)
    relogio = _relogio()
    return ClienteFalso(
        lambda _p: fila.pop(0), relogio=lambda: next(relogio), eventos_ferramenta=eventos
    )


def test_primeira_valida_conta_e_nao_ha_segunda_chamada() -> None:
    cliente = _falso(VALIDA, "nunca lida")
    resposta, registros = chamar(cliente, PEDIDO)
    assert resposta is not None and resposta.lado is Lado.VENDA
    assert [r.status for r in registros] == ["valida"] and registros[0].tentativa == 1


def test_invalida_repete_uma_vez_e_depois_desiste() -> None:
    resposta, registros = chamar(_falso("lixo", VALIDA), PEDIDO)
    assert resposta is not None and [r.status for r in registros] == ["invalida", "valida"]
    resposta, registros = chamar(_falso("lixo", "```json{}```"), PEDIDO)
    assert resposta is None and [r.motivo for r in registros] == ["nao_e_json", "nao_e_json"]


def test_uso_de_ferramenta_invalida_o_ensaio_sem_repetir() -> None:
    resposta, registros = chamar(_falso(VALIDA, VALIDA, eventos=1), PEDIDO)
    assert resposta is None and len(registros) == 1
    assert registros[0].motivo == "isolamento_violado"


def test_registro_guarda_resposta_crua_hashes_e_ambiente() -> None:
    _, (reg,) = chamar(_falso(VALIDA), PEDIDO)
    assert reg.resposta_crua == VALIDA and reg.modelo == "falso/teste"
    assert len(reg.sha256_pedido) == 64 and len(reg.sha256_png) == 64
    assert {"python", "numpy", "zlib"} <= set(reg.ambiente)
    assert reg.inicio < reg.fim


def test_nome_da_imagem_e_opaco() -> None:
    assert PEDIDO.nome_imagem.endswith(".png") and len(PEDIDO.nome_imagem) == 20


def test_codex_em_dry_run_monta_argv_isolado_e_nao_executa(tmp_path: Path) -> None:
    cliente = ClienteCodex(ConfigCodex(), base=tmp_path)
    plano = cliente.plano(PEDIDO)
    argv = plano.argv
    assert argv[:2] == ["codex", "exec"] and argv[-1] == "-"  # pedido por stdin
    for flag in (
        "-s",
        "read-only",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--json",
        "--output-schema",
        "-o",
        "-i",
    ):
        assert flag in argv
    assert argv[argv.index("-m") + 1] == "gpt-6-astra"
    assert "prompt" not in argv  # o texto vai por stdin, nunca na linha de comando
    assert plano.diretorio_trabalho != plano.arquivo_esquema.parent
    with pytest.raises(ExecucaoDesligada):
        cliente.responder(PEDIDO)


def test_codex_executado_com_runner_falso_le_saida_tokens_e_ferramentas(tmp_path: Path) -> None:
    eventos = "\n".join(
        json.dumps(e)
        for e in (  # forma documentada dos eventos de `codex exec --json` (amostra sintética)
            {"type": "thread.started", "thread_id": "x"},
            {"type": "item.completed", "item": {"type": "reasoning", "text": "..."}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": VALIDA}},
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 1500, "cached_input_tokens": 0, "output_tokens": 300},
            },
        )
    )
    vistos: list[list[str]] = []

    def runner(argv: list[str], entrada: str) -> tuple[int, str, str]:
        vistos.append(argv)
        trabalho = Path(argv[argv.index("-C") + 1])
        assert [p.name for p in trabalho.iterdir()] == [PEDIDO.nome_imagem]  # só a imagem
        assert entrada == "prompt"
        Path(argv[argv.index("-o") + 1]).write_text(VALIDA, encoding="utf-8")
        return 0, eventos, ""

    cliente = ClienteCodex(
        ConfigCodex(),
        base=tmp_path,
        executar=True,
        runner=runner,
        versao_declarada="codex-cli 0.153.4",
    )
    crua = cliente.responder(PEDIDO)
    assert crua.texto == VALIDA and (crua.tokens_entrada, crua.tokens_saida) == (1500, 300)
    assert crua.eventos_ferramenta == 0 and len(vistos) == 1


def test_ler_eventos_conta_ferramenta_e_soma_tokens() -> None:
    linhas = [
        json.dumps(
            {"type": "item.started", "item": {"type": "command_execution", "command": "ls"}}
        ),
        json.dumps({"type": "item.completed", "item": {"type": "command_execution"}}),
        json.dumps({"type": "item.completed", "item": {"type": "web_search"}}),
        "não é json",
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}),
    ]
    ev = ler_eventos("\n".join(linhas))
    assert ev.ferramentas == 2 and (ev.tokens_entrada, ev.tokens_saida) == (10, 2)
    assert ev.linhas_ilegiveis == 1


class _Quebra:
    modelo = "quebra/teste"

    def __init__(self, depois: str | None = None) -> None:
        self.depois, self.n = depois, 0

    def responder(self, pedido: Pedido) -> RespostaCrua:
        self.n += 1
        if self.depois is None or self.n == 1:
            raise TimeoutError("codex demorou")
        t = datetime(2026, 10, 17, tzinfo=UTC)
        return RespostaCrua(self.depois, "quebra/teste", "teste", t, t + timedelta(seconds=1))


def test_erro_do_cliente_vira_tentativa_registrada_e_repete_uma_vez() -> None:
    """Astra R2: um timeout não pode sumir com a tentativa nem ser reenviado sem registro."""
    resposta, registros = chamar(_Quebra(depois=VALIDA), PEDIDO)
    assert resposta is not None and [r.motivo for r in registros] == ["erro_cliente", None]
    assert "TimeoutError" in registros[0].resposta_crua and registros[0].modelo == "quebra/teste"
    resposta, registros = chamar(_Quebra(), PEDIDO)
    assert resposta is None and [r.motivo for r in registros] == ["erro_cliente", "erro_cliente"]


def test_telemetria_invalida_nao_conta_como_isolamento_provado() -> None:
    relogio = _relogio()
    cliente = ClienteFalso(lambda _p: VALIDA, relogio=lambda: next(relogio), telemetria_ok=False)
    resposta, registros = chamar(cliente, PEDIDO)
    assert resposta is None and [r.motivo for r in registros] == ["telemetria_invalida"] * 2


def _runner_com(stdout: str, codigo: int = 0):  # type: ignore[no-untyped-def]
    def runner(argv: list[str], entrada: str) -> tuple[int, str, str]:
        Path(argv[argv.index("-o") + 1]).write_text(VALIDA, encoding="utf-8")
        return codigo, stdout, ""

    return runner


_COMPLETO = "\n".join(
    json.dumps(e)
    for e in (
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": VALIDA}},
        {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
    )
)


def test_codex_exige_telemetria_completa_legivel_e_saida_zero(tmp_path: Path) -> None:
    def crua(stdout: str, codigo: int = 0) -> RespostaCrua:
        c = ClienteCodex(
            ConfigCodex(),
            base=tmp_path,
            executar=True,
            runner=_runner_com(stdout, codigo),
            versao_declarada="codex-cli 0.153.4",
        )
        return c.responder(PEDIDO)

    ok = crua(_COMPLETO)
    assert ok.telemetria_ok and ok.eventos_brutos == _COMPLETO
    assert not crua(_COMPLETO, codigo=1).telemetria_ok  # saída não zero, mesmo com texto
    assert not crua(_COMPLETO + "\n{truncad").telemetria_ok  # linha ilegível
    sem_fim = "\n".join(_COMPLETO.splitlines()[:2])
    assert not crua(sem_fim).telemetria_ok  # sem turn.completed: protocolo incompleto


def test_codex_recusa_chamada_com_varias_voltas_internas(tmp_path: Path) -> None:
    """Sentinela de 17/10: a tentativa de ler a isca foi bloqueada pelo sandbox **sem** emitir item
    de ferramenta; só a entrada de 51 411 tokens (uma volta mede ~15,4 mil) denunciou as voltas."""
    eventos = "\n".join(
        json.dumps(e)
        for e in (
            {"type": "item.completed", "item": {"type": "agent_message", "text": VALIDA}},
            {"type": "turn.completed", "usage": {"input_tokens": 51411, "output_tokens": 391}},
        )
    )
    c = ClienteCodex(
        ConfigCodex(),
        base=tmp_path,
        executar=True,
        runner=_runner_com(eventos),
        versao_declarada="codex-cli 0.153.4",
    )
    crua = c.responder(PEDIDO)
    assert crua.eventos_ferramenta == 0 and not crua.telemetria_ok


HOMOLOGADA = "codex-cli 0.153.4"


def _crua(
    tmp: Path, stdout: str, *, versao: str | None = HOMOLOGADA, saida: str = VALIDA
) -> RespostaCrua:
    def runner(argv: list[str], entrada: str) -> tuple[int, str, str]:
        Path(argv[argv.index("-o") + 1]).write_text(saida, encoding="utf-8")
        return 0, stdout, ""

    c = ClienteCodex(ConfigCodex(), base=tmp, executar=True, runner=runner, versao_declarada=versao)
    return c.responder(PEDIDO)


def _ev(*eventos: Mapping[str, object]) -> str:
    return "\n".join(json.dumps(e) for e in eventos)


MSG = {"type": "item.completed", "item": {"type": "agent_message", "text": VALIDA}}
FIM = {"type": "turn.completed", "usage": {"input_tokens": 15000, "output_tokens": 500}}


def test_telemetria_estrita_sondas_da_astra_r3(tmp_path: Path) -> None:
    assert _crua(tmp_path, _ev({"type": "turn.started"}, MSG, FIM)).telemetria_ok
    # uso ausente não vira zero
    assert not _crua(tmp_path, _ev(MSG, {"type": "turn.completed", "usage": {}})).telemetria_ok
    # evento desconhecido (protocolo mudou ou truncou) não passa
    novo = {"type": "new.tool", "item": {"type": "command_execution"}}
    assert not _crua(tmp_path, _ev(MSG, novo, FIM)).telemetria_ok
    # falha de turno, ou dois turnos
    assert not _crua(tmp_path, _ev(MSG, {"type": "turn.failed"}, FIM)).telemetria_ok
    assert not _crua(tmp_path, _ev(MSG, FIM, FIM)).telemetria_ok
    # a mensagem do agente tem de ser a resposta gravada em -o
    assert not _crua(tmp_path, _ev(MSG, FIM), saida=VALIDA.replace("0.5", "0.6")).telemetria_ok


def test_versao_nao_homologada_nao_envia_nada(tmp_path: Path) -> None:
    enviados: list[int] = []

    def runner(argv: list[str], entrada: str) -> tuple[int, str, str]:
        enviados.append(1)
        return 0, "", ""

    c = ClienteCodex(
        ConfigCodex(),
        base=tmp_path,
        executar=True,
        runner=runner,
        versao_declarada="codex-cli 9.9.9",
    )
    crua = c.responder(PEDIDO)
    assert not crua.telemetria_ok and enviados == [] and "homologada" in crua.texto


INI = {"type": "turn.started"}
FIO = {"type": "thread.started", "thread_id": "x"}


def test_telemetria_sequencia_e_estrutura_sondas_da_astra_r4(tmp_path: Path) -> None:
    # a forma real da sentinela (sem o teto) passa
    assert _crua(tmp_path, _ev(FIO, INI, MSG, FIM)).telemetria_ok
    # ferramenta em item.updated conta como ferramenta e invalida
    upd = {"type": "item.updated", "item": {"type": "command_execution", "command": "cat x"}}
    crua = _crua(tmp_path, _ev(FIO, INI, upd, MSG, FIM))
    assert crua.eventos_ferramenta == 1
    # turn.completed antes da mensagem final, ou sem turn.started
    assert not _crua(tmp_path, _ev(FIO, INI, FIM, MSG)).telemetria_ok
    assert not _crua(tmp_path, _ev(FIO, MSG, FIM)).telemetria_ok
    # evento de item sem o objeto item
    assert not _crua(tmp_path, _ev(FIO, INI, {"type": "item.started"}, MSG, FIM)).telemetria_ok
