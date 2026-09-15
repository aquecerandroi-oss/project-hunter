## RESUMO

**DONE_WITH_CONCERNS — quant-engineer, OPINIÃO.** Li o rascunho inteiro. **Testaria M-D16 primeiro, como adenda operacional a M-D15.** O carimbo macro entra em paralelo como evidência; M-P45 fica como célula exploratória, ainda em painel.

Há um avanço concreto: **a instrução já tem nome na IDL capturada: `admin_cto`**, com argumentos opcionais `is_holder_reward`, `creator_fee_bps` e `new_creator`; a conta `admin_set_creator_authority` é signatária. Existe também `AdminCtoEvent`, incluindo `mint`, `is_holder_reward` e `pool_updated`. Isso orienta a investigação, **mas não comprova nenhuma conversão específica**. [IDL T4.8c, linha 1](C:/dev/project-hunter/packages/exchange-adapters/tests/fixtures/pumpfun/t48c_idl_pump_onchain_raw.json:1).

### Ordem no funil

| Proposta | Encaminhamento |
|---|---|
| **M-D16** | Primeiro: resolve a identificação temporal da exposição que sustenta M-P34/M-P39/M-P41. **Adenda a M-D15**, sem hipótese independente de edge. |
| **macro_event / M-P43** | Registrar agora como painel, com procedência e incerteza. O dia motivador é exploratório; não é confirmação prospectiva. |
| **M-P45** | Registrar anúncios desde já; **célula exploratória vinculada a M-P29/M-P3**, preservando os contratos dos pais. Cinco anúncios não promovem automaticamente a teste conclusivo. |

Para **M-D16**:

- **Contrato:** distinguir estado econômico na cadeia de informação disponível ao Radar; identificar programa/versão, mint, conta, assinatura, índices de instrução, slot, finalidade e `received_at`.
- **Replay:** reconstruir casos comprovados de criação HR e conversão; demonstrar que descoberta tardia não altera exposição congelada em L.
- **Estresse:** CTO só de taxa/criador, chamadas repetidas, transações falhas, migração, histórico incompleto e atrasos por fonte.
- **Prospectivo:** medir cobertura e atraso, incluindo moedas cuja transação nunca foi localizada. A coleta de M-P34 continua junto.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

## TESTES

Não executei suites: revisão documental em modo OPINIÃO.

Inspeções PowerShell dos JSONs retornaram:

```text
instruction_count=47
requests=61
200  54
429   1
403   4
404   2
```

A tentativa adicional de leitura web do commit e do XML do Senado não trouxe conteúdo utilizável. **Não resolvi a contagem oficial nem localizei transações de conversão.**

## MUST-FIX

1. **Não tratar todo `admin_cto` como conversão.** A instrução também altera taxa/criador; o evento não contém o estado HR anterior. Exigir transação bem-sucedida e evidência de transição `false→true` na conta pertinente. **Falha:** mudança de taxa numa HR antiga vira uma falsa conversão. [IDL, linha 1](C:/dev/project-hunter/packages/exchange-adapters/tests/fixtures/pumpfun/t48c_idl_pump_onchain_raw.json:1).

2. **Corrigir as classes e a suposta refutação de M-D15.** `first_seen_true` sozinho significa **“HR observada; origem desconhecida”**, não “convertida?”. M-D15 diz que transição observada não comprova o instante, não que a cadeia jamais possa comprová-lo. Manter `event_at` separado de `received_at`; comparar tempos compatíveis, sem subtrair timestamp de slot. **Falha:** classificar como convertida uma moeda nascida HR ou retroagir informação recebida depois de L. [M-D15, linha 152](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:152).

3. **Restringir a afirmação sobre taxas e explicitar a contradição custom.** Os 0,30% são creator fee documentado para curva SOL/USDC, não percentual universal nem rendimento do holder. O README permite mudar creator fee custom via CTO: isso conflita com a imprensa dizendo “imutável”. **Falha:** aplicar custo errado após migração/custom ou projetar pagamentos sem comprovação. [Rascunho, linhas 18 e 36](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1807-lane2.md:18).

4. **Manter o placar do Senado como disputado, inclusive no registro estruturado.** Guardar as duas contagens por fonte; resultado reportado concordante = `cloture_failed`. O intervalo vem de atualizações jornalísticas, não de relógio oficial. **Falha:** o painel imprime 49–50 como confirmado ou usa publicação como instante exato do evento. [Rascunho, linha 27](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1807-lane2.md:27). O voto regulatório também fica em família própria, sem aumentar a amostra de payroll/CPI/FOMC de [H-P2, linha 21](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:21).

5. **Congelar M-P43 antes de classificar dias.** Resolver `OU` versus `E`, janela UTC/BRT, retorno diário versus móvel de 24 h e definição quantitativa de “máxima” dos juros. O retorno diário ainda aberto é provisório. Medir demanda com denominador e cobertura; propostas/R dependem também das regras do Lab. **Falha:** escolher a definição que inclui hoje e atribuir ao risco-off uma queda causada por coleta ou mudança de estratégia. [M-P43, linha 154](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:154).

6. **Retirar “dois clones antecipados pump.fun comprovados”.** O bruto informa `pairCreatedAt` de pares Raydium, não criação do mint nem origem pump.fun. Sem hora do lançamento, o par de **09/09 06:53 BRT** não está comprovadamente antes dele. **Falha:** admitir observações fora do universo e dar exposição antecipada a uma criação posterior. [Bruto DEX Screener](C:/dev/project-hunter/.claude/state/plantao-meme/raw-lane22/43_dexscreener_search_laptop.json:1), [rascunho, linha 68](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1807-lane2.md:68).

7. **Completar o contrato de M-P45.** Exigir anúncio recebido antes de L, normalização congelada, registro de todos os anúncios elegíveis — inclusive sem clones — e separar pré-lançamento de pós-lançamento até +24 h. Fixar horizonte de graduação, definição de retenção e tratamento de não migradas/censura. Avaliar ganho incremental sobre clones/narrativa, com dependência por anúncio, criador e dia. **Falha:** 100 clones de uma campanha parecem 100 observações independentes; ausência de significância vira “não são melhores”. Cinco anúncios/100 criações são piso de coleta, não potência. [Proposta, linha 71](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1807-lane2.md:71).

## NICE-TO-HAVE

**Leitura das seis frases:**

| Frase | Veredito |
|---|---|
| “CTO explica fone/baton” | Mecanismo compatível e documentado; atribuição por mint pendente. |
| “HR é 0,30%” | Generalização indevida; escopo descrito no must-fix 3. |
| “49–50 é a contagem” | Contagem atribuída a fontes; divergência aberta. |
| “Clones antecipados são sinal” | Motivação de pesquisa, sem evidência preditiva. |
| “Risco-off derrubou a demanda hoje” | Causalidade não demonstrada; nem a queda de demanda foi medida aqui. |
| “Taxas subindo três dias” | Descrição dos valores reportados, sem demonstrar tendência persistente, demanda orgânica ou efeito HR. |

O aviso de erro do `/pump-token` **não invalida automaticamente a DefiLlama**, mas exige verificar metodologia e dependência entre fontes antes de reconciliar valores. [Rascunho, linha 60](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1807-lane2.md:60).

Correção editorial: `_log.json` registra **54 HTTP 200**, não 52; os 14 acessos pump.fun dividem-se em **9 site + 5 frontend-api**, não 8+6. [Log](C:/dev/project-hunter/.claude/state/plantao-meme/raw-lane22/_log.json:1).

## O QUE EU FARIA DIFERENTE

**Publicaria adendo datado em KB-0097, com referência cruzada em KB-0096; não abriria outra KB.** Incluiria commit/hash, rota CTO, instrução encontrada, limites de comprovação, quatro páginas sem percentual e tabela de taxas com escopo/data. KB-0096 receberia apenas a atualização técnica pertinente à T4.8c.

Preservaria duas datas: **documento alterado em 14/09; observado pelo plantão em 15/09**. Nenhuma delas data o início do mecanismo nem a conversão de uma moeda.

## CONCORDO COM

Observações imutáveis por fonte; exposição nunca retroativa; denominador pela fita de criações; imprensa sindicada sem multiplicar confirmações; macro como painel; nenhuma promoção a sinal negociável nesta run.

## OBSIDIAN

- **Hipoteses-do-plantao** — M-D16 como adenda; M-P43 com definição congelada; M-P45 como célula exploratória em painel.
- **KB-0097 — Rewards → holders** — acrescentar rota CTO documentada, taxas contextualizadas e conversões individuais pendentes.
- **KB-0096 — is_holder_reward na REST** — referência à `admin_cto`/`AdminCtoEvent`, sem declarar conversão comprovada.
- **Meme — 2026-09-15** — registrar parecer, correções de evidência e contabilidade do log.
- **Baha — 2026-09-15** — reconciliar horários e distinguir dia motivador de confirmação prospectiva.