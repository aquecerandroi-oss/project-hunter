"""Adaptador do Codex CLI (``codex exec``) — **dry-run por padrão**.

Isolamento (Astra R1): cada chamada roda num diretório de trabalho novo que contém **só** a
imagem, com nome opaco; o esquema e o arquivo de saída ficam num diretório irmão (lidos/escritos
pelo próprio CLI, não pelo agente); ``--ignore-user-config`` (sem MCP nem configuração do
usuário), ``--ignore-rules``, ``-s read-only``, ``--ephemeral``; o pedido vai por stdin. Os eventos
de ``--json`` são lidos: qualquer item de ferramenta (shell, busca, MCP, arquivo) invalida o ensaio.

**Aceite estrito da telemetria (Astra R3):** versão do CLI homologada, verificada **antes** de
enviar; só tipos de evento conhecidos; exatamente um ``turn.completed`` com uso completo (entrada e
saída inteiras), nenhum ``turn.failed``/``error``; uma única mensagem do agente igual ao arquivo de
``-o``; saída 0; entrada ≤ teto de tokens (alarme de voltas internas). Isso **não prova**
isolamento — a sentinela de 17/10 mostrou tentativa bloqueada sem evento; são alarmes. Para o lote
real, a API direta sem ferramentas é o caminho que dispensa essa prova (desenho §2, §4).

Executar exige ``executar=True`` explícito. Uso em lote na conta ChatGPT é decisão do Everton
(cota compartilhada; termos a conferir) — ver ``docs/design/ia-le-grafico.md`` §4.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from infra.research.b3.ia_grafico.modelo import Pedido, RespostaCrua
from infra.research.b3.ia_grafico.protocolo import ESQUEMA_RESPOSTA

Runner = Callable[[list[str], str], tuple[int, str, str]]
_NAO_FERRAMENTA = frozenset({"agent_message", "reasoning"})
_TIPOS_CONHECIDOS = frozenset(
    {
        "thread.started",
        "turn.started",
        "turn.completed",
        "turn.failed",
        "item.started",
        "item.updated",
        "item.completed",
        "error",
    }
)


class ExecucaoDesligada(RuntimeError):
    """O adaptador está em dry-run: nenhuma chamada real sai sem ``executar=True``."""


@dataclass(frozen=True, slots=True)
class ConfigCodex:
    modelo: str = "gpt-6-astra"
    esforco: str = "medium"
    executavel: str = "codex"
    timeout_s: int = 300
    teto_tokens_entrada: int = 20_000
    """Uma volta com o pedido congelado mediu 15 434–15 436 tokens (codex-cli 0.153.4); acima disto
    houve voltas internas — tentativa de ferramenta que o sandbox bloqueou sem emitir evento."""
    versao_homologada: str = "codex-cli 0.153.4"
    """Outra versão = medir de novo (teto de tokens, eventos) antes do lote; nunca aceitar calado."""


@dataclass(frozen=True, slots=True)
class Plano:
    argv: list[str]
    diretorio_trabalho: Path
    arquivo_imagem: Path
    arquivo_esquema: Path
    arquivo_saida: Path


@dataclass(frozen=True, slots=True)
class Eventos:
    ferramentas: int
    tokens_entrada: int | None
    tokens_saida: int | None
    linhas_ilegiveis: int
    tipos_desconhecidos: int = 0
    turnos_completos: int = 0
    falhas: int = 0
    mensagens: tuple[str, ...] = ()
    estrutura_invalida: int = 0
    sequencia_ok: bool = False

    @property
    def turno_completo(self) -> bool:
        return self.turnos_completos == 1 and self.tokens_entrada is not None

    def aceitavel(self, texto_saida: str, teto_tokens: int) -> bool:
        return (
            self.linhas_ilegiveis == 0
            and self.tipos_desconhecidos == 0
            and self.estrutura_invalida == 0
            and self.sequencia_ok
            and self.falhas == 0
            and self.turno_completo
            and self.tokens_saida is not None
            and (self.tokens_entrada or 0) <= teto_tokens
            and len(self.mensagens) == 1
            and self.mensagens[0].strip() == texto_saida.strip()
        )


def _inteiro(v: object) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def ler_eventos(jsonl: str) -> Eventos:
    """Lê o ``--json`` falhando fechado (Astra R4): ferramenta em qualquer fase do item (inclusive
    ``item.updated``) conta; evento de item sem objeto ``item`` é estrutura inválida; a sequência
    homologada é ``thread.started``? → ``turn.started`` → itens → ``turn.completed`` (último evento),
    com a mensagem final concluída **dentro** do turno."""
    fases = {"item.started": 0, "item.updated": 0, "item.completed": 0}
    ilegiveis = desconhecidos = turnos = falhas = estrutura = 0
    entrada: int | None = None
    saida: int | None = None
    mensagens: list[str] = []
    estado, sequencia_ok = "inicio", True
    for linha in jsonl.splitlines():
        if not linha.strip():
            continue
        try:
            ev = json.loads(linha)
        except ValueError:
            ilegiveis += 1
            continue
        if not isinstance(ev, dict):
            ilegiveis += 1
            continue
        evento = cast(dict[str, object], ev)
        tipo, item, uso = evento.get("type"), evento.get("item"), evento.get("usage")
        if tipo not in _TIPOS_CONHECIDOS:
            desconhecidos += 1
        falhas += int(tipo in ("turn.failed", "error"))
        if estado == "fim":
            sequencia_ok = False
        if tipo == "thread.started":
            sequencia_ok &= estado == "inicio"
        elif tipo == "turn.started":
            sequencia_ok &= estado == "inicio"
            estado = "turno"
        elif isinstance(tipo, str) and tipo in fases:
            sequencia_ok &= estado == "turno"
            if not isinstance(item, dict):
                estrutura += 1
                continue
            it = cast(dict[str, object], item)
            if it.get("type") not in _NAO_FERRAMENTA:
                fases[tipo] += 1
            elif it.get("type") == "agent_message" and tipo == "item.completed":
                mensagens.append(str(it.get("text", "")))
        elif tipo == "turn.completed":
            sequencia_ok &= estado == "turno" and bool(mensagens)
            estado = "fim"
            turnos += 1
            u = cast(dict[str, object], uso) if isinstance(uso, dict) else {}
            entrada, saida = _inteiro(u.get("input_tokens")), _inteiro(u.get("output_tokens"))
        elif isinstance(item, dict):  # tipo desconhecido carregando item: trata como ferramenta
            fases["item.completed"] += 1
    return Eventos(
        max(fases.values()),
        entrada,
        saida,
        ilegiveis,
        desconhecidos,
        turnos,
        falhas,
        tuple(mensagens),
        estrutura,
        sequencia_ok and estado == "fim",
    )


def _subprocess(argv: list[str], entrada: str, timeout_s: int) -> tuple[int, str, str]:
    executavel = shutil.which(argv[0]) or argv[0]  # no Windows o CLI é `codex.cmd`
    proc = subprocess.run(
        [executavel, *argv[1:]],
        input=entrada,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout_s,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


class ClienteCodex:
    def __init__(
        self,
        config: ConfigCodex,
        *,
        base: Path | None = None,
        executar: bool = False,
        runner: Runner | None = None,
        versao_declarada: str | None = None,
    ) -> None:
        """``versao_declarada`` só existe para o runner de teste (sem CLI real não há o que ler)."""
        self.config, self._base, self._executar = config, base, executar
        self.modelo = config.modelo
        self._real = runner is None
        self._runner: Runner = runner or (lambda a, e: _subprocess(a, e, config.timeout_s))
        self._versao: str | None = None if self._real else versao_declarada

    def versao(self) -> str:
        """Versão do CLI, lida uma vez (com runner de teste, a declarada — ou desconhecida)."""
        if self._versao is None:
            if not self._real:
                self._versao = "desconhecida (runner de teste)"
            else:
                codigo, saida, _ = _subprocess([self.config.executavel, "--version"], "", 30)
                self._versao = saida.strip() if codigo == 0 else f"desconhecida (saída {codigo})"
        return self._versao

    def plano(self, pedido: Pedido) -> Plano:
        raiz = Path(tempfile.mkdtemp(prefix="h042-", dir=self._base))
        trabalho, apoio = raiz / "w", raiz / "apoio"
        trabalho.mkdir()
        apoio.mkdir()
        imagem = trabalho / pedido.nome_imagem
        esquema, saida = apoio / "esquema.json", apoio / "saida.json"
        c = self.config
        argv = [
            c.executavel,
            "exec",
            "-m",
            c.modelo,
            "-c",
            f'model_reasoning_effort="{c.esforco}"',
            "-s",
            "read-only",
            "-C",
            str(trabalho),
            "--skip-git-repo-check",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "-i",
            str(imagem),
            "--output-schema",
            str(esquema),
            "-o",
            str(saida),
            "--json",
            "-",
        ]
        return Plano(argv, trabalho, imagem, esquema, saida)

    def responder(self, pedido: Pedido) -> RespostaCrua:
        if not self._executar:
            raise ExecucaoDesligada(
                "ClienteCodex em dry-run; use executar=True por decisão explícita"
            )
        inicio = datetime.now(UTC)
        versao = self.versao()
        if versao != self.config.versao_homologada:
            return RespostaCrua(
                texto=f"<versão {versao!r} não homologada ({self.config.versao_homologada}); nada enviado>",
                modelo=self.config.modelo,
                cliente="codex-cli",
                inicio=inicio,
                fim=datetime.now(UTC),
                telemetria_ok=False,
                versao_cliente=versao,
            )
        p = self.plano(pedido)
        p.arquivo_imagem.write_bytes(pedido.png)
        p.arquivo_esquema.write_text(json.dumps(ESQUEMA_RESPOSTA), encoding="utf-8")
        codigo, stdout, stderr = self._runner(p.argv, pedido.texto)
        fim = datetime.now(UTC)
        ev = ler_eventos(stdout)
        texto = p.arquivo_saida.read_text(encoding="utf-8") if p.arquivo_saida.exists() else ""
        if codigo != 0 and not texto:
            texto = f"<codex saiu com {codigo}: {stderr.strip()[:300]}>"
        return RespostaCrua(
            texto=texto,
            modelo=self.config.modelo,
            cliente="codex-cli",
            inicio=inicio,
            fim=fim,
            parametros={"esforco": self.config.esforco, "sandbox": "read-only"},
            tokens_entrada=ev.tokens_entrada,
            tokens_saida=ev.tokens_saida,
            eventos_ferramenta=ev.ferramentas,
            telemetria_ok=codigo == 0 and ev.aceitavel(texto, self.config.teto_tokens_entrada),
            eventos_brutos=stdout,
            versao_cliente=versao,
        )
