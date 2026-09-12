## RESUMO

**Testaria M-D11 primeiro, depois M-D2; manteria a coleta de M-D9/M-P34 e deixaria M-P37 para depois desses instrumentos.** Papel: **quant-engineer**. Parecer: **DONE_WITH_CONCERNS**, somente leitura.

M-D11 corrige uma perda concreta de informação: `enabled` está documentado antes do upgrade, mas o normalizador o transforma em `unknown` e o CHECK não o admite. Isso compromete justamente a observação inicial que M-P37 pretende usar. Referências: [PUMPFUN.md:380](C:/dev/project-hunter/docs/PUMPFUN.md:380), [mayhem_labels.py:21](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/mayhem_labels.py:21), [meme.py:77](C:/dev/project-hunter/packages/core/hunter_core/db/models/meme.py:77).

**M-D2 continua sendo a prioridade seguinte porque valida os desfechos de várias hipóteses.** A nova discrepância entre REST e board reforça a necessidade de reconciliação; não demonstra que o board perde 29% das migrações reais. M-D9 ganhou vocabulário, mas nenhum positivo real; M-P37 ganhou motivação exploratória, não evidência preditiva.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

## TESTES

Recontagem somente leitura dos JSONs com PowerShell (`ConvertFrom-Json`, `Group-Object`):

```text
HTTP 200: 30
frontend-api-v3.pump.fun: 20
advanced-indexer.pump.fun: 6
pump.fun: 4

list_rows=270 unique_mints=237 enabled=0
ausente=151 active=23 completed=26 paused=70
detail_rows=10 enabled=0
```

Não executei pytest, lint ou migrações; não houve implementação. Não refiz as consultas públicas: o parecer trata dos registros históricos fornecidos.

## MUST-FIX

1. **M-D11 — preservar o rótulo sem confundir estado com qualidade da observação.**  
   Admitir `enabled` exige alinhar normalizador, contratos e CHECKs das tabelas envolvidas. Manter separadamente rótulo bruto, fonte e motivo de indisponibilidade/conflito; preservar também o tratamento tolerante para futuros rótulos desconhecidos. Corrigir a atribuição histórica da docstring.  
   **Cenário:** ampliar apenas o CHECK mantém `enabled → unknown` no normalizador; ampliar apenas o normalizador pode reintroduzir rejeição pelo banco. A regra atual está em [mayhem_labels.py:28](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/mayhem_labels.py:28); a semântica de discordância consta em [meme.py:49](C:/dev/project-hunter/packages/core/hunter_core/db/models/meme.py:49).

2. **M-D11/M-P37 — não prometer uma feature que o decoder não entrega.**  
   `MayhemStateAccount` expõe janela, mint, fluxos líquidos e `tail`; **não expõe estado, razões ou instante da primeira transação**. O próprio layout deixa a cauda sem interpretação. Referências: [mayhem_state.py:50](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/mayhem_state.py:50), [mayhem_state.py:180](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/mayhem_state.py:180).  
   M-D11 deve validar essa correspondência primeiro. Até lá, nomear a feature como **estado observado na REST**, com versão e procedência. Identificar primeira transação exige histórico de transações atribuído ao agente e cobertura desde a criação.  
   **Cenário:** interpretar fluxo líquido zero como “ainda não operou” perde compras e vendas que se compensaram; interpretar um byte não validado como `paused` fabrica o alvo.

3. **M-D11 — separar duração do rótulo, espera pela primeira operação e atraso de publicação.**  
   São três medidas diferentes. Guardar `request_started`, `received_at`, horário da fonte quando disponível, endpoint, slot/commitment e versão pertinente. DERP e baby mostram **observações divergentes separadas por 28 s e 8 s**, não tempos exatos de transição. Mesmo o intervalo só delimita a mudança se a atualidade das fontes estiver validada.  
   Coletar transições por fonte, incluindo retornos, saltos observados e lacunas; não impor antecipadamente uma cadeia irreversível. Primeiro registro já `active` deixa o início desconhecido; acompanhamento encerrado ainda `enabled` deixa a duração incompleta.  
   **Cenário:** lista em cache seguida de detalhe atualizado parece uma transição rápida embora a mudança tenha ocorrido antes da primeira consulta. O rascunho transforma essa sequência em transição em [lane1.md:106](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-1740-lane1.md:106).

4. **M-P37 — fixar o marco de previsão e impedir previsão de resultado passado.**  
   Recomendo `L = criação on-chain + 5 min`, usando exclusivamente dados **recebidos até L**, com defasagem máxima pré-fixada. Descobertas tardias e snapshots vencidos ficam explicitamente indisponíveis. Incluir `enabled`, estado desconhecido e razões ausentes; manter modo `auto/manual` separado.  
   Preservar `creator_prior_mints_1h` conforme M-P26, congelado na descoberta da criação; uma contagem recalculada aos cinco minutos precisa de outro nome. Referência: [Hipóteses:122](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:122).  
   **Cenário:** uma moeda conclui aos 40 s e entra como sucesso previsto pelo estado aos cinco minutos. Publicar esse grupo como “já concluídas em L”; testar conclusão futura em `(L, criação + 24 h]` nas ainda não concluídas, mantendo a contagem da coorte inteira.

5. **M-P37 — definir retenção sem selecionar sobreviventes.**  
   Coorte original: todas as criações Mayhem acompanhadas, com regra de descoberta fixa. Conclusão comprovada e migração são eventos separados. Retenção deve herdar M-P18b: `P(migração + 24 h) / P(referência inicial da pool)`, condicionada **a todas as migradas validadas dessa coorte**, incluindo as que desaparecerem. Fixar pool, orientação, quote, referência e tolerâncias antes da coleta. Referência: [Hipóteses:113](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:113).  
   **Cenário:** excluir pool sem preço às 24 h faz o braço com mais mortes parecer reter melhor. Separar ausência comprovada de saída, falha de coleta e horizonte ainda imaturo; publicar elegíveis, avaliáveis e desconhecidos por braço. Aalen–Johansen serve para eventos concorrentes definidos; não resolve automaticamente perda informativa de coleta nem estima a razão de preços.

6. **M-P37 — congelar a régua de ganho incremental.**  
   Comparar base versus base + estado/razões **nos mesmos mints e cortes temporais**, controlando modo, quote e versão. Reservas precisam de unidade correta; não misturar valores de quotes diferentes como SOL. Pré-fixar métrica primária — por exemplo, melhora de Brier para conclusão futura —, ganho mínimo relevante, calibração e confirmação temporal posterior. Usar incerteza por dia e sensibilidade por criador; células raras permanecem inconclusivas.  
   **Cenário:** dois criadores dominam a amostra e aparecem em treino e teste aleatórios; o ganho atribuído ao estado é memorização de criador. “≥100 e ≥30 dias” é piso, não potência. Falta de significância não demonstra redundância; isso exige margem de equivalência e precisão suficiente.

7. **Corrigir denominadores antes de registrar a evidência.**  
   As fontes enumeradas somam **70 + 140 + 60 = 270**, mais dez detalhes: **280 observações**, com repetição de mints. Os próprios totais por estado somam 270, embora o texto diga 300. Também são vinte chamadas frontend, não dezessete. Referências: [lane1.md:4](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-1740-lane1.md:4), [lane1.md:108](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-1740-lane1.md:108).  
   **Cenário:** usar 310 como ensaios independentes produz falsa precisão sobre raridade de `enabled`. Recontar separadamente o denominador de cashback.

## NICE-TO-HAVE

O que considero sobre-interpretação:

- **“`enabled` é curto, por isso apareceu zero vezes.”** O bundle descreve preparação; duração e explicação do zero continuam hipóteses.
- **“O estado é função das reservas.”** É uma hipótese de redundância razoável, mas modo, janela, histórico e decisão do agente podem acrescentar informação.
- **“Vocabulário completo” / “a página vai exibir a taxa”.** Há templates no bundle; falta provar renderização e correspondência on-chain. `holders` e `holders + taxa` são a mesma classe econômica, com taxa opcional; as quatro classes incluem `desconhecido`. Referência: [extrato:231](C:/dev/project-hunter/.claude/state/plantao-meme/raw-lane17/30_coinpage_i18n_extract_25xPUK.json:231).
- **“Zero positivos em cinco horas.”** Nas APIs sem o campo, a exposição é **não mensurável**. Nas três páginas, foram três observações `creator`.
- **“Replicação independente”, “fração estável”, “mesmo slot”.** Há repetição descritiva intradia, discrepância entre recortes e proxy por segundos. Pós-upgrade por horário de graduação também não implica criação pós-upgrade. O contraste post/perfil condicionado a `complete ∩ board` não testa M-P17.

## O QUE EU FARIA DIFERENTE

**Recomendo uma KB nova:** “pump.fun — rótulos observados do site, REST e limites da correspondência on-chain”.

Ela se justifica porque o problema de vocabulário e proveniência atravessa o upgrade e inclui rótulo comprovadamente anterior. Organizaria por campo/fonte/data, separando **template do bundle**, **valor numa moeda**, **semântica validada** e **inferência**. Evitaria chamar de máquina de estados completa.

Na KB-0094, apenas um adendo curto com a correção cronológica e o vínculo à nova nota. M-D9 recebe o vocabulário; M-P34 continua aguardando exposição on-chain válida.

## CONCORDO COM

Preservar `enabled`, separar estado de modo, exigir positivos reais para M-D9, validar conclusão antes de testar vantagem e avaliar M-P37 pelo ganho incremental. Nenhum desses achados, sozinho, justifica filtro de entrada.

## OBSIDIAN

- **Hipóteses do plantão** — registrar M-D11/M-P37 com fonte disponível, marcos, desfechos, censura e régua acima.
- **Plantão MEME — 2026-09-12** — corrigir denominadores e distinguir repetição descritiva de confirmação prospectiva.
- **KB-0094 — pump.fun: o upgrade de 12/09/2026** — acrescentar que `enabled` antecede o upgrade e vincular a nova KB.
- **Nova KB: rótulos observados do site, REST e limites on-chain** — consolidar vocabulário datado sem atribuir ao decoder semântica ainda não validada.