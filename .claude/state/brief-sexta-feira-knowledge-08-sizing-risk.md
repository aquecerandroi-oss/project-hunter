# Brief — Sexta-feira: rodada 8 de conhecimento — dimensionamento de posição e Risk Engine

**Origem:** sugestão da própria Sexta-feira ao fechar a rodada 5 ("como o tamanho da posição sai do R, do teto de capacidade e dos limites por mercado; é a peça que fecha o caminho para o M4") e a diretiva do Everton de 2026-09-06 ("adquirir todo conhecimento dessa área"; "o virtual precisa estar pronto antes do dinheiro real"). O Lab hoje não dimensiona nada (KB-0036: a sombra nunca declara o tamanho). O M3/M4 vão precisar de um Risk Engine com regras que ninguém escreveu ainda.

**Regra operacional:** nunca Bash em background; comandos em primeiro plano com timeout ≤ 5 min. Método das rodadas anteriores (`obsidian/11-KNOWLEDGE/`; leia `Index.md`, `Strategy Backlog.md`, `Registro de Tentativas.md`; a numeração continua em KB-0066). Escreva só em `obsidian/11-KNOWLEDGE/**`; commit e push só desses arquivos a cada 3 notas (`docs(knowledge): ...`, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`). Síntese própria, fontes abertas com URL, sem cópia, sem serviço pago. A VPS está disponível para medir (`ssh hunter-vps`, `docker exec hunter-postgres-1 psql -U hunter -d hunter -c "..."`, só SELECT). Outras instâncias estão em `services/**` e `packages/**`; não toque neles nem em `.env*`.

## O que já existe e a nota tem de ler antes de propor
`packages/risk-core/**` e `hunter_core.execution` (o que há de sizing/kill switch, se algo), `docs/plans/M3.md`/`M4.md` se existirem, `docs/PIPELINE.md`, `.claude/agents/risk-engine-guardian.md` (o que o guardião exige), KB-0036 (capacidade por livro), KB-0046 (R-múltiplos), KB-0050 (Carver: sizing por volatilidade), KB-0064 (quedas por coorte e requisitos para o Risk Engine), KB-0041/0042 (deslocamento de entrada e custo real).

## Temas (8–10 notas)
1. **R como unidade e o risco por operação**: fração fixa de capital por R (0,25–1 %), o que a literatura aberta diz sobre ruína e drawdown em função dessa fração (Ralph Vince, Van Tharp, Kelly e as suas críticas — fração de Kelly, half-Kelly), e por que Kelly cheio é inaceitável com estimativas ruidosas de expectancy.
2. **Sizing por volatilidade** (Carver, Turtles/ATR): posição = risco alvo / (ATR₀ × multiplicador do stop); como isso interage com `atr_pct_min/max` e com o custo por R já medido (KB-0057, KB-0058).
3. **Capacidade e impacto**: teto de notional por mercado a partir da profundidade do livro (KB-0036) e do volume; regra de "nunca mais que x % do volume de 1 min/5 min"; lei da raiz quadrada com a ressalva da KB-0040.
4. **Correlação e exposição agregada**: cem altcoins reagindo ao BTC (KB-0060: β mediano 2,8 e R² 0,15 nas memes) — exposição bruta, exposição em β-BTC, limite por cluster; o que a literatura aberta de risk parity/vol targeting diz que se transfere.
5. **Drawdown, kill switch e circuit breakers**: regras de parada diária/semanal, redução de tamanho após perdas, "cooldown"; evidência aberta (e o que é só convenção de prop-firm); o que o `risk-engine-guardian` já exige.
6. **Alavancagem em perpétuos**: margem cruzada vs isolada, liquidação da exchange vs o nosso stop, funding como custo de carregar, e por que o M4 começa sem alavancagem (`ENABLE_LIVE_TRADING=false` e sem alavancagem são decisões do Everton).
7. **Risco operacional**: lacunas de dados (tape descoberto, KB-0044 e a cobertura da T2.5-adapter), latência (KB-0041), erro de instrumento (funding, KB da rodada 5) — regras de "não operar quando…".
8. **Medição do que já temos**: com SQL na VPS, a distribuição de notional que caberia em cada mercado do universo a 5 bps de impacto, e quantos mercados suportariam 500 / 2.000 / 10.000 USDT por sinal — a tabela que o M3 vai precisar.
9. (opcional) **Paper trading honesto**: o que a literatura e a prática dizem sobre a diferença paper→real (fills, filas, rejeições), e o que a sombra tem de simular antes de o M4 alegar qualquer coisa.

## Para cada nota
Template `_TEMPLATE-NOTE.md`, "Segunda opinião (Astra)" por nota (`bash infra/scripts/astra.sh ask KB-<slug> "..."`). Linha no `Index.md` (tema novo "Dimensionamento e risco"). Aqui a saída não é candidata de estratégia: é uma seção nova no `Strategy Backlog.md` chamada **"Regras propostas para o Risk Engine (M3/M4)"** — cada regra com nome, fórmula/parâmetro, dado necessário (temos?), o que a refutaria ou quando ela erra, e a marcação "decisão do Everton" onde for (capital, fração de risco, alavancagem, kill switch). Nada é ativado; nada vira código nesta rodada.

Relatório final em português: notas, regras propostas em ordem de prioridade para o M3, medições feitas na VPS, discordâncias da Astra, fontes que não abriram.
