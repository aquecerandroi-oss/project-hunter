---
tags: [revisao-astra, meme, concentracao, maior-comprador, e2b, resultado, h-031]
date: 2026-10-07
updated: 2026-10-07
status: registro
owner: quant-engineer
decided_on: 2026-10-07
by: astra
tarefa: R88 — resultado da H-031 e o código que o produziu, antes do advogado-de-jesus e do defensor
veredito: "concorda com H-031, A e B = NÃO CONFIRMA; sha256 e as duas contas do empate de A reproduzidos; 4 must-fix de descrição absorvidos sem mudar rótulo"
---

# Revisão da Astra — resultado da H-031 (R88)

**Pedido:** rever `h031.txt` inteiro, o código (`stats88.py` com 10 testes, `freeze88.py`, `run88.py`,
`moinho88.py`), as réplicas SQL (`replica_A.txt`, `replica_B.txt`), o exploratório (`explore.txt`) e `real.txt`,
contra o pré-registro e a emenda ([[H-031-prereg]]). Transcrição: `.claude/state/astra-review-H-031-resultado.md`.

**O que ela reproduziu (em memória, sobre os CSVs):** sha256 da lista elegível `18dcd185…` igual ao `freeze.txt`; em A,
D_adj 0,0201 com o limiar como literal decimal e 0,0857 com a regra em float — 4 linhas mudam de braço (a mesma mint nos
quatro conjuntos).

**Concordou com:** os três rótulos; A não confirma também por nível negativo, IC cruzando zero e ausência de planalto
(não depende só do empate); sem erro de unidade nem de `Decimal` (`pnl_sol ÷ sol_spent` em `Decimal`, depois float);
sem antecipação (B antes do `await`; 0 carimbos depois da proposta no congelamento); a saída `creator_dump` é padrão
de `ExitRules`; as 6 posições reais são anedota. Os 20,8 % de réplicas de dia inválidas são limitação do desenho
corretamente capturada pela trava — não motivo para trocar o bootstrap agora.

**Quatro must-fix, todos absorvidos (nenhum muda rótulo):**

1. **Metades mudam o contraste** — suporte e pesos recalculados por metade (a 2.ª de A só tem `flow_v2/9`). →
   declarado como desvio na Fila e na KB.
2. **"Neutraliza no simulador" excede a evidência.** → redação trocada para associação: mais saídas `creator_dump` com
   concentração alta, sem vantagem de retorno ao excluir; neutralização = explicação possível, não demonstrada.
3. **Denominador da perda ≥ 50 % e "A sem criador".** → perda ≥ 50 % recalculada só sobre as medidas (B 7/390 = 1,8 %
   contra 70/1 257 = 5,6 %; a direção fica) e "A sem criador" declarado não avaliável (o `pedigree_e2b` não grava
   `is_creator`). `h031.txt` regenerado; os números decisórios não mudaram.
4. **Corte temporal efetivo** 07/10 00:00Z, não o congelamento (00:39:40Z). → declarado; sem reextração.

**Nice-to-have registado, sem efeito aqui:** `plateau()` remove pontos não avaliáveis antes de contar consecutivos
(todos os pontos desta saída são avaliáveis). O REFUTA do moinho agrupado não é o veredito da H-031 — escrito na Fila.

**Divergência:** nenhuma.

Nota: [[KB-0188-a-concentracao-do-maior-comprador-nao-separa-o-retorno]] · bloco: [[Fila de Hipoteses]] (H-031).
