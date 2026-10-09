**RESUMO**

**APPROVE. Os dois must-fix da rodada 2 estão fechados.** Revisão como `code-reviewer`, restrita às correções solicitadas.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit.

**TESTES**

Executei `uv run pytest` com os seletores de interrupção do join, falha do worker e janela divergente em `test_wallets_stream_parallel.py`, com sincronização, cache e bytecode desabilitados:

```text
4 passed in 22.84s
```

Sondas adicionais em memória confirmaram:

- captura interrompida em **3.599,6 s**: estatística horária recusada;
- `last_t` vazio: **0 s**, sem exceção;
- recepção além do pedido: limitada a **3.600 s**;
- join de processo interrompido: retomado, demais processos tratados e interrupção relançada.

Não repeti a suíte completa nem os benchmarks.

**MUST-FIX**

Nenhum remanescente neste escopo.

1. **Encerramento fechado:** os processos são preservados antes do `shutdown`; a interrupção aciona término e join explícitos. Falhas da noite usam `abort_pool`. A regressão real passou. [stream_parallel.py:113](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:113), [stream_parallel.py:227](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:227), [teste:319](C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_stream_parallel.py:319).

2. **Duração fechada:** `capture_seconds` usa o último carimbo recebido, com padrão `t0` e teto solicitado; a drenagem deixa de acrescentar tempo. [density-probe.py:74](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallet-tape-density-probe.py:74), [wallet_tape_probe_net.py:64](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_net.py:64).

**NICE-TO-HAVE**

Há um cenário novo **conservador, não bloqueante**: `on_connect` apaga `last_t`. Reproduzi reconexão dos dois feeds depois de uma hora, sem novos logs: duração voltou a **0 s**. Isso omite uma estatística potencialmente válida, mas não aprova uma captura curta. Um máximo histórico separado evitaria essa perda. [wallet_tape_probe_stats.py:134](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:134).

**O QUE EU FARIA DIFERENTE**

Usaria esse máximo histórico para distinguir “nenhuma notificação recebida” de “carimbos apagados pela reconexão”.

**CONCORDO COM**

- `terminate` é adequado ao replay atual: resultados são descartáveis e `emit` ocorre no coordenador. Não encontrei operação durável do motor que precise terminar no worker. [stream_parallel.py:165](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:165), [stream_parallel.py:222](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:222).
- `_processes` continua sendo dependência privada; ausência numa versão futura não é falha demonstrada no ambiente suportado, limitado a Python **3.12**. [pyproject.toml:4](C:/dev/project-hunter/pyproject.toml:4).
- As faixas e a fonte de transporte foram corrigidas. Ressalva documental: a medição isolada de imports usa **parede**, portanto não demonstra uma parcela exata do startup em **CPU**. [registro:279](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:279), [transport-cost.py:47](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallets-transport-cost.py:47).

**OBSIDIAN**

- **Revisão da Astra: CPU do motor de carteiras, passo 3** — registrar APPROVE da rodada 3 e os quatro testes executados.
- **CPU do motor de carteiras: medir antes de reescrever** — registrar a limitação conservadora nas reconexões e distinguir parede de CPU na medição de imports.