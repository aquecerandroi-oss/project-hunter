**RESUMO**

Manter o SOL líquido é razoável, mas a nota precisa de correções antes de ser considerada validada.

**ARQUIVOS** — Nenhum alterado.

**TESTES** — Não executados; revisão estática e consulta às fontes. Cálculo conferido: `432000 × 0,4 / 86400 = 2 dias`.

**MUST-FIX**

- **Bloqueio por LST não está garantido.** A [KB:129](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0165-staking-do-sol-parado.md:129) confunde contrato com implementação: [docs:233](C:/dev/project-hunter/docs/RISK_ENGINE_MEME.md:233) exige a trava, mas `unrecognized` assume vazio em [admission.py:261](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/admission.py:261), e nenhum dos três chamadores o preenche. **Cenário:** receber LST não dispara essa recusa; confiar nela como proteção seria incorreto. Remover também a sugestão de que bastaria uma allowlist.

- **Resgates descritos incorretamente.** Na [KB:50](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0165-staking-do-sol-parado.md:50), os **0,1% da Jito correspondem ao resgate com espera de até uma época**, não à liquidez instantânea ([FAQ oficial](https://www.jito.network/docs/jitosol/faqs/general-faqs/)). A taxa Marinade de **0,2%** confere, mas o resgate atrasado exige **mínimo de 1,0043 SOL**, superior ao saldo estudado ([FAQ oficial](https://docs.marinade.finance/marinade-protocol/faq)). **Cenário:** planejar uma retirada imediata ou uma modalidade indisponível para 0,38 SOL.

- **Época e rent:** [KB:38](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0165-staking-do-sol-parado.md:38) deveria dizer **2 dias teóricos**, não 2,5; não tratar cooldown como prazo garantido. Em [KB:164](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0165-staking-do-sol-parado.md:164), **0,0165–0,0266 SOL/ano é maior**, não menor, que o rent padrão de **0,00203928 SOL** usado em [limits.py:191](C:/dev/project-hunter/packages/risk-core/hunter_risk_meme/limits.py:191). **Cenário:** decisão de liquidez/custo baseada em comparação invertida.

**NICE-TO-HAVE** — Nenhum adicional.

**O QUE EU FARIA DIFERENTE**

Usaria **5–7% como cenário ilustrativo**, sem chamar toda a tabela de “APY atual”: confirmei 5,02% e inflação de 3,65% no [painel citado](https://www.stakingrewards.com/asset/solana/analytics), mas não os snapshots históricos dos LSTs. Divergência de APY pode decorrer de metodologia/janela.

Preservando 0,30 SOL, apenas **0,03–0,08 SOL** seriam excedentes: **0,0015–0,0056 SOL/ano**, antes dos custos de movimentação. Isso sustenta melhor a recomendação.

**CONCORDO COM**

`getBalance` lê o saldo nativo ([chain.py:136](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/chain.py:136)); LST externo não entra em `equity_sol` ([inputs.py:199](C:/dev/project-hunter/packages/risk-core/hunter_risk_meme/inputs.py:199)). A conversão também pode aparecer como perda/drawdown, não apenas reduzir caixa ([inputs.py:229](C:/dev/project-hunter/packages/risk-core/hunter_risk_meme/inputs.py:229)). Manter liquidez nessa carteira continua sendo minha recomendação.

**OBSIDIAN**

- **KB-0165 — Staking do SOL parado:** corrigir resgates, época, rent e distinguir a trava prevista da efetivamente alimentada.
- **Open Bugs:** registrar a ausência de preenchimento de `unrecognized_holdings` nos caminhos de entrada.