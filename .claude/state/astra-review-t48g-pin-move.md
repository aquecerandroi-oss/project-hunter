**RESUMO**

**Aprovo tecnicamente o pino T4.8g nas condições informadas: zero posições, escopo esgotado e `launch_lane` desligada.** Não encontrei MUST-FIX no diff que bloqueie esse aceite restrito. Isso não aprova reabrir compras. Status: **DONE_WITH_CONCERNS**.

**ARQUIVOS**

Revisados os cinco arquivos indicados e os caminhos de guarda, compra e saída. Nenhum arquivo criado ou modificado; nenhum commit.

**TESTES**

Conferências realizadas nesta revisão:

- `git apply --reverse --check .claude/state/tmp/t48g_pin_move.patch`: saída vazia, sucesso.
- Contagem de `program_identity.py`: **340 linhas**.
- Decodificação independente dos cabeçalhos das fixtures: pump **454596459**, PumpSwap **454596406**, taxas **454596501**; prefixo de autoridade **6348fb82** nos três.

Não executei pytest, lint, pyright, Postgres ou consultas à VPS. Os **2191 passed**, o **1 passed** de Postgres e o estado operacional são evidências fornecidas por você.

**MUST-FIX**

**Nenhum para mover o pino mantendo as entradas presas.**

Permanece o MUST-FIX **antes de reabrir compras**: reservar o crescimento da curva. Cenário concreto: compra próxima do teto do escopo, em curva antiga, acrescenta **76.200 lamports** ao débito e ultrapassa a reserva autorizada. `buy_reserve_sol` contempla rede, prioridade e ATA; a reserva do escopo soma isso ao limite da compra. [scope.py:96](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/scope.py:96), [entries.py:226](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/entries.py:226).

**NICE-TO-HAVE**

Corrigir a frase **“Cashback buy/sell are proven by simulation only”**: ela pode ser lida como cobertura da venda cashback **na curva**, expressamente ausente no artefato. Melhor: “compra cashback na curva e venda cashback na PumpSwap simuladas; venda cashback na curva não coberta”. É imprecisão documental, sem regressão operacional demonstrada. [program_identity.py:198](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_identity.py:198), [prova:12](C:/dev/project-hunter/packages/exchange-adapters/tests/fixtures/pumpfun/t48g_simulation_proof_mainnet.json:12).

**O QUE EU FARIA DIFERENTE**

Não usaria **“só falharia por falta de ~76.200 lamports + taxa”** como conclusão comprovada:

- O nosso `min_sol_output` deriva do provento **após taxas de protocolo e criador**, com slippage; não é simplesmente o `sol_amount` bruto. Isso tampouco demonstra como o programa atualizado trata uma realocação durante a venda. [quote.py:296](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/quote.py:296).
- `treasury_sol_floor=0,30` é um limiar para tentar recomposição, não uma reserva garantida no instante da venda. A tentativa depende de condições e pode não ocorrer. [treasury.py:90](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/treasury.py:90).

A hipótese de cobrança separada do aluguel é plausível; **a exclusividade desse modo de falha continua não demonstrada**.

**CONCORDO COM**

**1. A lacuna de venda em 151 B não bloqueia este pino.** Não encontrei cenário concreto em que **essa alteração** piore uma saída existente: a venda continua construindo e submetendo sem receber o gate de identidade das entradas. Uma incompatibilidade do programa atual afetaria também a saída com o pino antigo. [exits.py:259](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exits.py:259), [exits.py:300](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exits.py:300).

Seu argumento compra→crescimento→venda em 166 B é sustentado **nos casos medidos**. Não o transformaria em regra universal para toda curva não-cashback: a venda simulada em 166 B é HR/Token-2022, e o artefato também declara venda SPL clássico não coberta. A compra cashback observada permaneceu em 151 B. Isso delimita o aceite de futuras compras, sem bloquear o pino restrito. [prova:95](C:/dev/project-hunter/packages/exchange-adapters/tests/fixtures/pumpfun/t48g_simulation_proof_mainnet.json:95), [prova:110](C:/dev/project-hunter/packages/exchange-adapters/tests/fixtures/pumpfun/t48g_simulation_proof_mainnet.json:110), [prova:125](C:/dev/project-hunter/packages/exchange-adapters/tests/fixtures/pumpfun/t48g_simulation_proof_mainnet.json:125).

**2. A guarda dos três programas permanece intacta, após detectar a divergência.** Comparação estrita, registro pegajoso e recusa antes da assinatura continuam presentes. [program_watch.py:109](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_watch.py:109), [program_check.py:80](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/program_check.py:80), [program_check.py:190](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/program_check.py:190).

A ressalva é temporal: o `pre_sign_gate` relê **o estado em memória**, não a cadeia. Um upgrade entre a última leitura e a assinatura ainda pode escapar até a próxima detecção. Essa limitação já existia; o patch não a introduz. [signing_gate.py:19](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/signing_gate.py:19).

**3. Slots, histórico, mensagem T4.8h e fixtures estão coerentes.** T4.8f vira `PREVIOUS`, T4.8d permanece no histórico e T4.8g vira a expectativa atual. A ressalva encontrada é a redação sobre cashback acima. [program_identity.py:160](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_identity.py:160), [program_identity.py:181](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_identity.py:181), [program_watch.py:55](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/program_watch.py:55).

Aceito o verde Postgres informado como fechamento da pendência **da curva**; a variante PumpSwap continua pendente para reabertura, conforme o aceite anterior. [t48f-pin-move.md:24](C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/t48f-pin-move.md:24).

**OBSIDIAN**

- **T4.8g-upgrade-08-10** — registrar aprovação restrita, lacuna 151 B e limite temporal da guarda.
- **t48f-pin-move** — acrescentar o verde Postgres da curva informado hoje; manter pendente PumpSwap.
- **Exchange Adapters** — atualizar os três pinos e distinguir as coberturas cashback.
- **Open Bugs** — manter a reserva de crescimento como bloqueio para reabrir compras.