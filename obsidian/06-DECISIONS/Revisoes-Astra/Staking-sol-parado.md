---
tags: [astra, revisao, cripto, staking, tesouraria]
date: 2026-09-28
updated: 2026-09-28
status: fechada
owner: sexta-feira
decided_on: 2026-09-28
by: Astra + pesquisa
---

# Revisão da Astra — staking do SOL parado (28/09/2026)

**Tarefa:** estudo, sem dinheiro, se o SOL ocioso da carteira de operação deveria render staking ([[KB-0165-staking-do-sol-parado]]).

**Correções da Astra, todas aceitas:** (1) a checagem `wallet_unrecognized_holdings` prometida no `RISK_ENGINE_MEME.md` §3.2 é inerte no código — o parâmetro chega sempre vazio, então um LST na carteira não travaria a mesa nem seria contado (sairia como "perda do dia"); (2) a taxa de 0,1 % da Jito é do resgate direto, não da saída instantânea; (3) a saída atrasada da mSOL exige mínimo de 1,0043 SOL, acima do saldo inteiro; (4) época ~2 dias, e a comparação do rendimento com o aluguel de ATA estava invertida.

**Resultado:** não stakar enquanto nenhuma estratégia estiver confirmada — rendimento de ~0,0015–0,0056 SOL/ano sobre o excedente acima do piso de tesouraria não paga a complexidade. Decisão final do Everton. A lacuna da checagem virou tarefa de correção.

Bruto: `.claude/state/astra-review-staking-sol-parado.md`. Relacionado: [[Ideias do Everton]] · [[06-DECISIONS/Revisoes-Astra/Index|Revisões da Astra]]
