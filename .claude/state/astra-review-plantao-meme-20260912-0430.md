**RESUMO**

Eu testaria **M-P3 (`symbol_dup_24h`) primeiro entre as cinco hipóteses**, depois do **D-P25, que verifica o instrumento**. A duplicação pode ser conhecida na criação, tem definição simples e não depende de reconstruir graduação ou sete dias de histórico de criadores. **12 WOFI entre graduadas justifica investigar; não demonstra poder preditivo**, porque a amostra já seleciona sucesso. O D-P25 continua sendo a primeira porta acordada na memória: verificar descoberta **e acompanhamento**, separadamente. [KB-0091:80](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0091-pump-fun-as-taxas-base-e-seus-denominadores.md:80)

Minha ordem seria: **D-P25 → M-P3**; M-P2 como painel de denominadores desde o início; M-P4 como instrumento de desfechos; depois M-P1, quando houver tempos confiáveis, e M-P5, quando houver histórico suficiente. Papel assumido: `quant-engineer`. Parecer concluído com ressalvas; nenhuma hipótese demonstrou edge.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Li o rascunho, a nota do dia, a memória relacionada, o plano e os modelos/normalizador disponíveis da T4.2.

**TESTES**

Não executei suites: esta é uma revisão de medição, sem implementação. Recalculei os agregados dos JSONs locais com PowerShell (`Get-Content -Raw … | ConvertFrom-Json`, agrupamento e filtros). Saída real:

```text
GETs: 26
rows: 150
unique_mints: 150
below_tenth_ath: 105
WOFI: 12
with_mayhem_state: 40
Benz: idade na leitura = 209 segundos
Anthropic: idade na leitura = 216 segundos
```

Isso confirma as contagens, **não a validade econômica dos preços nem os timestamps dos eventos**. Consultei também documentação oficial; não fiz novas chamadas à frontend API.

**MUST-FIX**

1. **Não transformar os relógios disponíveis em tempo de graduação.** Os 71,9 minutos são criação→`last_trade`; não medem conclusão. Para as duas moedas novas, a leitura sustenta limites superiores de aproximadamente **3,48 e 3,60 minutos**, se criação e estado reportados estiverem corretos — não duas graduações comprovadas em ≤3,5 minutos. Cenário de falha: atualização em lote às 02:33 faz uma moeda antiga parecer recém-negociada e muda artificialmente a associação entre velocidade e retenção. [Rascunho:25](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0233-lane1.md:25), [rascunho:29](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0233-lane1.md:29)

   A T4.2 **já define `completed_at` como primeira observação de conclusão**, não instante on-chain. Preservaria essa semântica; registraria separadamente eventual horário comprovado do evento, fonte, assinatura/slot e finalidade. Com polling, o instante fica entre a última observação incompleta e a primeira completa; descoberta já completa produz limite, não duração exata. `migrated_at` permanece separado. [meme.py:167](C:/dev/project-hunter/packages/core/hunter_core/db/models/meme.py:167)

2. **Resolver a divergência de `observed_at` antes do replay.** O modelo descreve horário da fonte; o normalizador REST preenche tanto `observed_at` quanto `received_at` com `now`. Cenário: resposta de cache antiga recebe dois relógios atuais e aparenta atraso zero. [meme_series.py:91](C:/dev/project-hunter/packages/core/hunter_core/db/models/meme_series.py:91), [normalize.py:197](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/normalize.py:197)

   Recomendo distinguir **horário reportado pela fonte**, **horário da nossa observação/recepção** e **disponibilidade da feature**. Se a fonte não fornece horário confiável, declarar desconhecido; `updated_at` também não prova trade. No replay, só entram dados recebidos e features disponíveis até a decisão. A criação via WS também usa recepção local hoje, portanto subtrair os dois campos não produz automaticamente duração on-chain. [normalize.py:113](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/normalize.py:113)

3. **Não usar mcap da curva como preço do pool.** A coluna gerada da T4.2 calcula reservas **virtuais** × supply; o normalizador faz essa conta mesmo quando `complete=true`. Cenário: depois da migração, reservas terminais congeladas fabricam preço estável e escondem o colapso real. [notes-T4.2:63](C:/dev/project-hunter/.claude/state/notes-T4.2.md:63), [normalize.py:205](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/normalize.py:205)

   Para M-P1/M-P4, proponho uma série explicitamente identificada por **pool, mint base/quote, decimais, reservas efetivas, fonte, slot/finalidade e relógios**. Guardar preço marginal e estimativa de saída para tamanho fixado como medidas diferentes. Sem leitor do pool, retorno pós-migração fica **nulo com motivo**. O contrato atual declara trades sem produtor; tabela existente não significa trajetória disponível. [notes-T4.2:72](C:/dev/project-hunter/.claude/state/notes-T4.2.md:72)

4. **Corrigir os denominadores antes de comparar Mayhem.** `23/50` das mais novas e `40/150` das graduadas não estimam probabilidades comparáveis: janelas, idade, seleção e disponibilidade do estado diferem. Tampouco ausência de `mayhem_state` comprova não-Mayhem. Cenário: graduações tardias ficam fora da leitura e parecem desvantagem do modo. [Rascunho:22](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0233-lane1.md:22), [rascunho:35](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0233-lane1.md:35)

   A soma auto+manual confirma a decomposição do overview e invalida seu uso como universo geral. Mas **“≈5%, limite inferior” também deve sair**: denominador extrapolado de 210 segundos e paginação incompleta não garantem esse limite. [Rascunho:63](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0233-lane1.md:63)

**NICE-TO-HAVE**

No Radar, mostraria lado a lado **mcap reportado**, **mcap recalculado**, **liquidez observada**, **saída estimada para tamanho fixo** e **qualidade/frescor**.

US$919 milhões, zero replies e ATH recente são **alertas de validação**, não prova de fraude nem de demanda. A igualdade `mcap_SOL × SOL/USD` valida apenas a conversão; não prova que o preço veio corretamente do pool. `inverted:true` exige validar orientação base/quote. Timestamps sincronizados são compatíveis com atualização em lote **ou atividade real**; somente eventos independentes podem distinguir. [Rascunho:51](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0233-lane1.md:51), [rascunho:57](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0233-lane1.md:57)

Assim, **105/150 é uma razão entre valores reportados pela API**. Não comprova que 70% sofreram queda executável de 90% depois de graduar: falta localizar o ATH relativamente à conclusão e validar ambas as pontas. Os 404 mostram falha das rotas testadas, não ausência de trades.

**O QUE EU FARIA DIFERENTE**

Pré-registraria M-P3 assim:

| Etapa | Protocolo proposto |
|---|---|
| **Contrato** | `symbol_dup_24h` = número de **outros mints distintos criados** nas 24 horas anteriores, conhecidos até a decisão. Excluir o próprio mint; congelar normalização do símbolo. Separar qualquer contagem de graduações anteriores em outra feature. Histórico incompleto = desconhecido, nunca zero. |
| **Replay** | Coorte de todas as criações elegíveis em janela UTC fixa; contraste inicial duplicado/não duplicado. Desfecho primário: conclusão comprovada até sete dias. Comparar dentro de dia/hora e estrato Mayhem conhecido; não escolher cortes depois de ver WOFI. |
| **Estresse** | Atrasos, perdas de descoberta, desaparecimento de tokens, falhas de pool, resultados sem os maiores criadores/símbolos e mudança de parâmetros do protocolo. Verificar se desconhecidos podem inverter o contraste. |
| **Prospectivo** | Congelar regra e repetir em criações futuras. O arquivo usado para descobrir WOFI permanece exploratório. Somente depois testar uma política de entrada/saída com custos e controle equivalente. |

A régua editorial permanece **≥100 avaliáveis e ≥30 dias**, IC95% por blocos de dia e consistência em duas de três janelas; multiplicidade corrigida se houver vários contrastes. Esses mínimos não garantem poder, sobretudo com poucas graduações. [Meme — estratégias:42](C:/dev/project-hunter/obsidian/03-TRADING/Meme/README.md:42)

**Graduação não paga a conta.** Para promoção econômica, exigir retorno líquido positivo e ganho sobre controle sob a mesma execução, incluindo impacto próprio, taxas vigentes, latência e saídas inviáveis. A documentação oficial ressalta que as taxas efetivas são determinadas pelos contratos; não usaria percentual universal de PumpSwap. [Taxas oficiais](https://pump.fun/docs/fees)

A retenção precisa preservar **todos os braços, perdedores, desaparecidos, falhas e dados necessários à auditoria**, pelo mesmo prazo, independentemente do sucesso. O plano já proíbe poda seletiva por graduação. [T4-MEME-RADAR:369](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:369)

Para conclusão até sete dias mais acompanhamento de 24 horas depois, prever até **oito dias por criação**, além de coleta, histórico anterior e auditoria. M-P5 exige sete dias anteriores; M-P3, 24 horas. Se orçamento limitar acompanhamento, amostrar na criação por regra independente do resultado.

Em cada braço publicar `N`, sucessos, negativos comprovados e desconhecidos. Para graduação, mostrar limites `[S/N, (S+U)/N]`. Para retorno faltante, não imputar zero nem apresentar média dos avaliáveis como média da coorte. M-P4 pode descrever graduadas, mas deve mostrar também `graduadas/N_criações` e sua cobertura.

**CONCORDO COM**

A prioridade de capturar conclusão, migração e preços separados está correta. Os **85,005 SOL são uma observação desta amostra**, não constante universal: o contrato local exige `complete=true` e reservas reais de tokens zeradas; a instrução de migração é separada. [Plano:100](C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:100), [programa oficial](https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_PROGRAM_README.md)

**OBSIDIAN**

- **Plantão MEME — 2026-09-12:** acrescentar correções de tempos, denominadores e interpretação de mcap/ATH.
- **Hipoteses-do-plantao:** registrar D-P25 como pré-condição e M-P3 como primeiro teste, com protocolo e retenção.
- **KB-0091 — pump.fun: taxas-base e denominadores:** reforçar censura temporal, limites por desconhecidos e separação curva/pool.
- **Meme — o que uma “estratégia” é aqui:** explicitar que associação com graduação só vira candidata após validação econômica.
- **Revisões Astra — Plantão MEME run 1:** registrar este parecer e as divergências de contrato da T4.2.