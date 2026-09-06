# 0005 — Carteira virtual permanente em USDT com âncora em BRL e Risk Engine `paper_v1` (decisões do Everton de 2026-09-06)

- **Status:** aceito em 2026-09-06 (diretiva do dono + decisão conjunta Claude ⇄ Astra, `.claude/state/dialogue-M3.md`, 3 rodadas)
- **Data:** 2026-09-06

## Contexto

O contrato do Risk Engine (`docs/RISK_ENGINE.md` v1) foi escrito antes de o projeto medir qualquer coisa e **nunca teve consumidor**. A oitava rodada de conhecimento (KB-0066 a KB-0075, `obsidian/11-KNOWLEDGE/Strategy Backlog.md`) confrontou-o com o dado e achou dois defeitos estruturais: `risk_per_trade_pct` **nunca atuava** (os limiares implícitos ficam acima do `max_stop_distance_pct` de cada perfil, então o check de distância reprovava antes, e o risco bruto no stop ficava 6 a 8× abaixo do rótulo), e o multiplicador do kill switch **não garantia redução** (multiplicava o orçamento de risco, não o tamanho, então em algumas combinações a posição saía do mesmo tamanho enquanto o painel prometia "tamanho × 0,5"). A rodada terminou com sete decisões que só o dono podia tomar. Em 2026-09-06 o Everton respondeu às sete e foi além, numa diretiva de sete partes mais uma lista de validação.

## Decisão

Adotar integralmente a diretiva do Everton como o perfil de risco da carteira virtual, num preset novo chamado **`paper_v1`**, e reescrever `docs/RISK_ENGINE.md` como **contrato v2** fiel a ela.

**Os valores dele, sem alteração nem invenção:**

| Item | Valor |
|---|---|
| Capital | R$100.000 fictícios, convertidos em USDT na abertura com cotação, fonte e instante registrados; lucros reinvestidos; **sem aporte e sem reset** |
| Risco por operação | 0,25 % do patrimônio atual, **incluindo custos estimados**; é teto, não meta |
| Risco agregado | 1 % somando posições abertas e entradas pendentes; liberar 1 % por operação exige aprovação dele |
| Participação | 1 % do volume de referência de um minuto = `min(último minuto completo, mediana dos 30 minutos completos)`, agregando todos os agentes, sem fracionar ordens, com validação adicional do livro |
| Exposição | 40 % total, 10 % por moeda, 5 posições, β-BTC ≤ 0,5× do patrimônio (em módulo); pendentes contam |
| Kill switch | AVISO em 1 % de perda diária **ou** 4 % de drawdown → tamanho final × 0,5; BLOQUEADO em 2 % **ou** 8 % → entradas param, pendentes canceladas, proteções continuam, sem liquidação automática, retomada só com autorização dele. Dia em `America/Sao_Paulo`, pico histórico sem reset |
| Modalidade | SPOT, sem empréstimo, alavancagem, short ou futuros; `ENABLE_LIVE_TRADING=false` |
| Universo | piso de 50 M USDT de volume 24 h por par na exchange de execução; abaixo disso, radar e shadow, sem capital |

**Além dos valores, a arquitetura fechada com a Astra** (detalhe em `docs/plans/M3.md` → "Decisão conjunta"): ledger em USDT com âncora imutável em BRL e série histórica de câmbio, resultado operacional separado da variação cambial; carteira principal **única e permanente** por escopo, com a brecha "arquivar e reabrir" explicitamente proibida; simulador de execução só com ordem a mercado, cancelamento terminal do restante na **entrada** e intenção de saída **durável** na proteção, sem fill fabricado; Risk Engine puro entre sinal e ordem, com a decisão persistida antes de qualquer ordem, o limitante vencedor publicado e o estado `unavailable` reprovando por padrão; ordem fixa de travas sistema → organização → portfolio com releitura na mesma transação do efeito; β versionado com validade ancorada no fim da janela; seleção `fifo_v1` com rejeição terminal por falta de vaga.

## Alternativas consideradas

- **Manter o contrato v1 e só acrescentar os números.** Rejeitado: os dois defeitos medidos são de **fórmula**, não de valor — o rótulo continuaria não descrevendo o comportamento.
- **Executar sobre os preços do perpétuo como proxy do spot.** Rejeitado como opção conforme: mede execução num instrumento que não é o que a diretiva manda operar. Só existiria se o Everton mudasse a modalidade, explicitamente. Fica como a pergunta 1 a ele.
- **Escolher entre sinais elegíveis pelo score do M2.** Rejeitado no M3: seria a primeira vez que o score decide dinheiro sem nunca ter sido validado como preditor.
- **Ordens limit com modelo de fila.** Rejeitado no M3: sem posição em fila e sem L3, qualquer modelo seria invenção rotulada de simulação.
- **Reset da carteira por meio de um portfolio novo.** Rejeitado: preservaria as linhas antigas e ainda assim reiniciaria patrimônio e pico, e destravaria um BLOQUEADO sem a autorização exigida.

## Divergência registrada

A Astra derrubou, nas três rodadas, doze afirmações minhas — as principais: o termo cambial calculado sobre o **caixa** em vez do equity total (ela conferiu com `Decimal` e mostrou um erro de R$8.200 no exemplo); "reset = novo portfolio" como saída legítima; a saída de proteção executando com "o pior candidato disponível" quando falta livro, que é **fabricar proteção**; "o stop executa pior por construção", quando o preço pode sair melhor, igual ou pior; generalizar para as saídas o cancelamento terminal do restante, que deixaria unidades desprotegidas depois de um fill parcial; e as afirmações sem consulta "só o BTC teria β válido" e "a participação será **sempre** o limitante" — a medição de 46 USDT vem de **perpétuos**, numa janela histórica, e não descreve a população SPOT futura. Todas aceitas e corrigidas no contrato e no plano. Eu mantive, e ela aceitou: o `fifo_v1` como política inicial, a instrumentação da participação em vez de qualquer afrouxamento, e a fronteira do M3 em entradas manuais.

## Consequências

- `docs/RISK_ENGINE.md` passa a ser v2, com a matriz §9.1 dizendo, para cada controle do v1, se foi mantido, substituído ou é inaplicável — nada de margem, futuros ou preset permissivo entra de carona.
- `docs/ROADMAP.md` muda: M3 deixa de ser só paper trading e passa a ser "carteira virtual + Risk Engine"; o M4 fica com agentes e a ponte sinal → proposta.
- O M3 **não** declara modo autônomo. A ponte entre sinal e proposta não existe, e sinal `research_only` do Shadow Lab continua recusado (`docs/plans/SHADOW-LAB.md`).
- Nove conflitos entre a diretiva e o sistema que existe estão em `docs/plans/M3.md` → "Perguntas ao Everton antes de alterar qualquer limite". **Nenhum limite foi alterado**, como a própria diretiva exige.
- O preset `paper_v1` exige um valor novo no enum `risk_preset` e uma migração; a carteira principal exige índice único parcial que não depende de `status` nem exclui `deleted_at`.

## Referências

`.claude/state/directive-risk-engine-2026-09-06.md` (diretiva verbatim + análise de conflitos), `.claude/state/dialogue-M3.md`, `docs/RISK_ENGINE.md` v2, `docs/plans/M3.md`, `obsidian/11-KNOWLEDGE/Strategy Backlog.md` (oitava rodada), KB-0066 a KB-0075, commit `e6ed2c4`.
