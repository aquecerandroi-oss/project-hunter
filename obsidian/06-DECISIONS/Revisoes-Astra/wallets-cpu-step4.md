---
tags: [revisao-astra, meme, carteiras, h-030, motor-puro, desempenho, cpu, monotonia, equivalencia]
date: 2026-10-09
updated: 2026-10-09
status: registro
owner: quant-engineer
decided_on: 2026-10-09
by: astra
tarefa: passo 4 do plano de CPU do motor de carteiras 1c-bis — o stop de cada cópia virou uma comparação de inteiros contra um limiar por evento, exato onde a venda líquida arredondada é provadamente monotônica nos átomos
veredito: desenho aprovado com 2 must-fix (safe negativo; "todos param" sem transição), absorvidos antes do teste verde; diff REQUEST_CHANGES com 2 must-fix de teste (dois mutantes sobreviviam: `<=`→`<` no limiar e o salto de bloco sem a guarda de min_safe), fechados com testes dirigidos; ela confirmou de forma independente o conserto da pool marcada `complete`; rodada 2 APPROVE (invariantes do galope conferidos em 93 665 combinações); nenhuma divergência de equivalência encontrada no código final
---

# Revisão da Astra: CPU do motor de carteiras, passo 4 (H-030)

Plano acordado em [[wallets-cpu]] (decisão conjunta da rodada 2). Passos anteriores: [[wallets-cpu-step2]] e [[wallets-cpu-step3]]. Densidade real que motivou o passo: [[KB-0187-a-densidade-por-mint-mora-em-poucas-pools]]. Brutos: `.claude/state/astra-review-wallets-cpu-step4-design.md` (prova e desenho) e `.claude/state/astra-review-wallets-cpu-step4.md` (diff). Medições e prova em [[wallets-cpu]], seção "Passo 4".

## Rodada 0 (prova e desenho): a prova fecha na região; 2 must-fix

Ela leu a prova contra o código (`pricing.py`, `curve.py`, `numeric.py`) e a reproduziu em memória:

- **Curva:** com `sol·atoms < 10²⁸` e `token + atoms < 10²⁸`, as conversões, o produto e a soma são exatos; o quociente é o arredondamento correto de um racional estritamente crescente, logo não decrescente. O `× 10⁹` só acrescenta zeros; `ROUND_FLOOR` e `Decimal(int)` são exatos; o contexto não depende do ambiente (ela testou com precisão ambiente 2). A recusa de reserva virtual esgotada fica excluída com `0 ≤ real < sol`.
- **Piso:** `inteiro ≤ piso Decimal ⇔ inteiro ≤ ⌊piso⌋` vale também para piso negativo. Usar `int()` (truncamento) seria errado (`-0.1` viraria 0).
- **Fora da região** ela reproduziu o meu contraexemplo, com uma correção: a queda é em `a + 2` e a venda volta a subir em `a + 4`.

| # | Achado (cenário dela) | O que entrou |
|---|---|---|
| 1 | `sol = 2, token = 10²⁸, real = 1` é aceito por `Reserves` e a fórmula dava `safe = −1` | `max(0, …)` em `monotone_atoms`, com o caso dela no teste |
| 2 | Pool `Q = 2, T = 1, S = 2`, taxa 0, piso 1: toda venda rende 1 lamport; o inverso dividiria por zero e o certificado `net(c) ≤ F < net(c+1)` não existe | O palpite devolve "ilimitado" quando o teto ou `Q` não passam do piso; o galope distingue "sem transição" e devolve `safe` sem cotar `safe + 1`. Teste com o caso dela |

Ela também respondeu às perguntas de desenho:

- o índice por (fita, piso Decimal) não colide entre políticas (`atoms` é argumento da consulta; `Decimal('1.0')` e `Decimal('1.00')` compartilharem a chave é correto);
- construir os resumos de bloco antecipadamente é aceitável, **executar o fallback antecipadamente não**: um evento recusável fora da janela da cópia nunca pode levantar;
- preferiu **não** começar pelo emulador inteiro do Decimal: inverso inteiro e certificação pelo cotador atual. Ela avisou que blocos de 64 não mudam a ordem da varredura por cópia (≈ N/64 blocos).

## Rodada 1 (diff): REQUEST_CHANGES por duas lacunas de teste

Ela rodou os testes novos e o golden (23 passed). Fez sondagens em memória: palpites forçados e sondas sempre em `[0, safe]` (150 casos), blocos parciais, inícios no meio do bloco, `atoms ≤ 0` e acima da sentinela (1 680 casos), e o pickle de uma `MintTape` (leva o cache, que fica independente e aponta para os fills desserializados; o transporte atual não serializa fitas).

| # | Achado (cenário dela) | Conserto, com teste que falhou antes |
|---|---|---|
| 1 MEDIUM | O mutante `atoms <= limit` → `<` sobrevivia: nenhum teste batia exatamente no limiar | Pool `S = 17, T = 23`, piso 1: 3 átomos rendem exatamente 1 lamport e param; 4 não. Testado em `stopped` e `first_stop` |
| 2 MEDIUM | O salto de bloco sem a guarda `atoms ≤ min_safe` sobrevivia | 64 eventos que não param, e no índice 31 uma curva fora da região (`sol = 10²⁸`, `safe = 0`) cuja venda vale 0 e para: o correto é 31; o mutante dava 64. Mais a variante com uma recusa no mesmo lugar, que tem de levantar |

**Achado corrigido durante a revisão** (encontrado por mim na autorrevisão, confirmado por ela): uma pool com `complete=True` era tratada como curva completa (nunca para). Só a curva completa é incotável (`pricing._executable`). Ela reproduziu `stop/1010/1015` no código antigo contra `time_cap/10005/10010` no novo, antes do conserto. Teste específico.

**Nice-to-have que entraram:** comparar também a mensagem do `ValueError`; casos pequenos e fixos para início desalinhado, cauda parcial, piso fracionário negativo e `UNBOUNDED + 1`.

## O que veio depois da revisão

- **Mutação: 15 de 15 mortos** no código final, numa cópia do pacote (os dois mutantes dela, mais 13). O 15.º, "confiar no palpite" (pular as cotações que certificam o limite), sobreviveu a todos os testes até eu procurar o caso. Uma busca dirigida achou estados de curva **dentro** da região (`sol = 17` lamports, `token ≈ 1,6·10²⁶`) em que o arredondamento de 28 dígitos põe o limite real um átomo abaixo do palpite inteiro. Ficou fixado como teste: é a certificação que torna o limite exato, não a álgebra do palpite.
- Na escala de produção, palpite e limite coincidem (200 000 estados aleatórios sem divergência): o arredondamento só move a fronteira quando (token + átomos) × bruto passa de ≈ 10²⁷.

## Rodada 2 (diff): APPROVE

Bruto: `.claude/state/astra-review-wallets-cpu-step4-r2.md`. Ela rodou os três arquivos de teste novos e o golden (32 passed). Os dois mutantes da rodada 1 agora morrem (ela conferiu em memória). Ela também conferiu o `_bracket` (o galope que saiu de `stop_limit` pelo PLR0915 do tier estrito) em 93 665 combinações: todas as sondas ficam em `[0, safe]`, o invariante `líquido(lo) ≤ F < líquido(hi)` vale, e `hi = None` só aparece quando não há transição dentro da região. Nenhum must-fix pendente.

## Divergências registradas

Nenhuma sobre a regra. Sobre o caminho:

- **Segundo nível do índice:** ela o sugeriu se a busca continuar dominante. Medido: na chave de 124 000 eventos/h com o preço andando no tempo, a caminhada por blocos custou ≈ 4,3 s dos 31,6 s da chave sob cProfile, ≈ 1–2 % da hora do programa. **Não entrou**: fica como opção, com o número.
- **Núcleo inteiro do Decimal (opção 3 da proposta):** concordamos em não fazer agora. O que sobrou do custo não é a cotação do stop. A cotação Decimal ainda pesa no E-PnL (uma liquidação por posse e por fronteira), e o núcleo inteiro voltaria a fazer sentido ali.

[[wallets-cpu]] · [[wallets-cpu-step3]] · [[KB-0187-a-densidade-por-mint-mora-em-poucas-pools]] · [[wallets-1c-bis]]

## Revisão de código independente (09/10/2026, commit 5c364290)
- **APPROVE**, sem achado CRITICAL/HIGH/MEDIUM. A Astra também aprovou nessa rodada, sem must-fix.
- **Fuzz diferencial:** 21 600 casos aleatórios comparando `StopIndex.first_stop` com a varredura simples por `quote_stopped`, com **0 divergências**. São 5 343 recusas, todas com a mesma mensagem.
- **Mutante:** `atoms <= limit` trocado por `<` foi morto por 4 testes.
- **Testes:** `279 passed` (meme, `-k "stops or golden or wallets"`).
- **Custo de memória a lembrar:** o índice não tem despejo. Custa O(eventos × pisos distintos) por `MintTape`, cerca de 2 MB por piso numa mint de 124 k eventos. Hoje não pesa, porque há uma política por noite. Uma varredura de parâmetros que reutilize a mesma fita precisa levar isso em conta.
- **Corrigido junto:** o script de perfil `2026-10-06-wallets-engine-profile.py` contava `policy._stopped`, que não existe mais, e passaria a mostrar "stop quotes 0". Agora soma também `stops.quote_stopped`.
