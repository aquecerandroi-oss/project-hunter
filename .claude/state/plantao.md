# Plantão da Sexta-feira — nota do turno

Atualizado: 2026-09-08, **madrugada** (turno no Hermes). Plantão de documentação:
EXP-0005 aberto, Changelog consolidado, "Sexta-feira no Hermes" escrita, três
bugs abertos. Nenhuma linha de código tocada, nenhuma suíte rodada.

## O que mudou neste turno

- **EXP-0005 aberto** (`obsidian/05-EXPERIMENTS/EXP-0005-momentum-paper.md`): a
  linha paper do momentum v1 (D10) com Hipótese e Protocolo congelados, sem
  avaliação. A coorte paper nasce quando a `0010` chegar à VPS e o Everton ativar
  a versão com `--paper-line`. Ligada a EXP-0001 e às decisões D10/D1/D2.
- **Changelog consolidado** com os 12 commits da tarde de 09-07 e da manhã de
  09-08 (de `8822b31` a `e26a4ee`): T3.0c spot ingest, T3.0d spot event ids,
  T3.5c worker usa 0009, T3.9b V4-V9, T3.0e exit band, T3.14b+T3.5d bridge+kill,
  T3.15 purpose, Hermes profile, T3.15b bridge gate, review T3.15b, M3 report
  DRAFT, T3.0e review.
- **"Sexta-feira no Hermes"** (`obsidian/04-AGENTS/`): o que mudou (motor,
  delegação, Astra, Claude Code), regras da casa (brief, commit, git, PATH,
  index.lock), o que fica igual (regras duras, decisões do Everton, memória em
  `obsidian/`).
- **Três bugs abertos** em `obsidian/07-BUGS/Open Bugs.md`: `market_betas` vazia
  na VPS (produtor horário nunca entregue, T3.7b em voo); candles só 11 dias na
  VPS (beta exige 20 contíguos, backfill 31 d em voo); 160 erros de pyright em
  `test_restart_recovery.py`.

## Saúde

| Onde | Estado |
|---|---|
| VPS | Não verificado (escopo de escrita fechado; sem SSH neste turno) |
| Local | Não verificado (madrugada; Docker Desktop não checado) |

## Em voo (não tocar nos arquivos)

| Tarefa | Arquivos |
|---|---|
| T3.0f (spot collector as its own service) | `services/market-worker/**` |
| T3.7b (β producer + 31-day backfill) | `services/scanner-worker/**`, `packages/indicators/**` |

## Próximo passo

1. **Segundo deploy da VPS** (Everton): traz `0010` + T3.15b e destrava a linha
   paper (D10).
2. **Revisões T3.0e e T3.15/0010** (Sexta-feira): database-architect +
   risk-engine-guardian + security-reviewer, quando a cota da Astra voltar
   (2026-09-12) ou por subagentes do Hermes.
3. **T3.10**: consolidar docs e escrever `docs/reports/M3.md` no formato
   estendido (DRAFT já existe em `700d58f`).
4. **2026-09-09/10**: segunda avaliação datada do EXP-0003 (condição 2 do M2).

## O que preciso do Everton

**O segundo deploy da VPS.** Sem ele, a `0010` não chega ao banco de produção,
a T3.15b não sobe, e a linha paper do momentum (D10) não pode nascer. É um
comando só: `MARKET_SHARDS=4 bash infra/vps/compose.sh update`. Depois disso, a
ativação da linha paper é ato dele (D10, sete condições).
