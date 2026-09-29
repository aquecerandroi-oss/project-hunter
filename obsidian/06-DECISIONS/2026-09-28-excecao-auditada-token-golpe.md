---
tags: [decisao, carteira, risco, meme-executor]
status: decidida
owner: sexta-feira
updated: 2026-09-28
decided_on: 2026-09-28
by: Everton
---

# Token-golpe congelado: exceção auditada por mint (28/09/2026)

**Contexto.** A checagem `wallet_unrecognized_holdings` passou a ler a carteira de verdade ([[Wallet-unrecognized-holdings]]). O guardião de risco achou na carteira um token de phishing congelado pelo emissor (`DgY9Z8xPG1346Ydrq98ASAZcVdyrurT4tCQ7TDapHcJg`, "FOMPOSIT.TOP CLAIM YOUR REWARD 1000 USDC", chegou em 23/09). Ninguém consegue movê-lo, queimá-lo nem fechar a conta, e com a checagem ligada todas as entradas parariam ([[Open Bugs]]).

**Opções apresentadas:** (1) exceção registrada por mint, auditada; (2) ignorar automaticamente contas congeladas por terceiros; (3) não ligar a checagem ainda.

**Decisão do Everton (28/09):** **opção 1 — exceção registrada.**

**O que isso significa (contrato para quem implementar):**
- A exceção mora no Postgres (nunca em arquivo ou `.env`), por carteira + programa + mint, com evidência, motivo, responsável e data; só entra por uma ferramenta auditada (`audit_logs`), com `--note` apontando para uma nota do Obsidian, como as outras mudanças de risco (regra em `.claude/rules/obsidian-first.md`).
- A exceção **nunca** autoriza comprar, vender ou interagir com o token; só tira o mint da lista de "estranhos".
- Qualquer outro mint estranho continua travando as entradas.
- O heartbeat e o registro de cada admissão mostram à parte os mints dispensados por exceção.
- Por que não a opção 2: uma compra manual num token que o emissor congele depois ficaria escondida (argumento da Astra aceito pelo guardião).

## Relacionado

[[Wallet-unrecognized-holdings]] · [[KB-0165-staking-do-sol-parado]] · [[Open Bugs]] · [[2026-09-28]]

## Execução

- **30/09/2026:** código no ar no deploy `a72296a0` (o primeiro deploy, `190a9ecb`, subiu sem as flags de perfil e não atualizou o executor — lição em `.claude/memory/deploy-vps-comando-completo.md`). Na primeira leitura a carteira já **não tinha** a conta do token-golpe: fechada pelo terceiro que detinha a autoridade de fechamento. `wallet_unrecognized_count=0`; nenhuma exceção cadastrada. Listagem das contas vazias (ensaio de `close_empty_token_accounts`, 17:2xZ): 82 contas, 80 fecháveis, **0,120815 SOL líquidos** a recuperar em 11 lotes; a USDC da tesouraria e a posição UNI da `spot/1` ficam.
