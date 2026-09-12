## RESUMO

**Eu testaria M-D12 primeiro entre as propostas novas, com linha própria.** M-D9 valida o rótulo de exposição; M-P34 testa sua associação com desfechos; M-D12 verifica se houve distribuição, quanto e quando. São perguntas diferentes. Isso não altera a precedência dos diagnósticos de integridade já registrados.

**M-P38 merece linha exploratória própria, após corrigir o protocolo.** M-P28 descreve estrutura transacional na criação; M-P19v2 mede fees/tips nos primeiros minutos da criação; M-P38 mede desequilíbrio de contagens **após migração**. Não é redundância demonstrada. O teste deve ser de **ganho incremental**, e os sete WOFI ficam apenas como motivação retrospectiva. Referências: [fila:114](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:114), [fila:125](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:125).

O anúncio alimenta **M-D8**, sem hipótese nova. Sua cronologia é útil; a alegação de uma “ordem de vigilância medida” excede a evidência.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Parecer em OPINIÃO, sob o papel `quant-engineer`, com leitura integral do rascunho.

## TESTES

Não executei testes de software. Recalculei os agregados em PowerShell, lendo os JSONs arquivados com `ConvertFrom-Json`; saída:

```text
SUM mc=4743451076 liq=14337577,68 buys=270659 sells=6241
B/S=43,367890 mc/liq=330,840480
holders_reported=20
top10_pct=10,2834903106137
top20_pct=20,5669805696369
```

O cálculo do snowflake retornou `2026-09-12T16:59:36.0890000+00:00`, concordante ao segundo com `created_at`.

## MUST-FIX

**1. Retirar “tudo além disso é imprensa”: há conteúdo primário omitido.**

O arquivo arquivado no run 14 já documenta contato com a equipe CTO para converter moedas existentes e que a conversão permanece. Também descreve endereço controlado pela pump.fun como destinatário da taxa. Isso não comprova um formulário específico, critérios de aprovação ou uma única carteira distribuidora. [Docs arquivados:32](C:/dev/project-hunter/.claude/state/plantao-meme/raw-lane14/09_gh_docs_HOLDER_REWARDS_README.md.txt:32), [docs arquivados:118](C:/dev/project-hunter/.claude/state/plantao-meme/raw-lane14/09_gh_docs_HOLDER_REWARDS_README.md.txt:118). A [documentação primária consultada](https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/docs/HOLDER_REWARDS_README.md) mantém essas descrições.

**Falha:** M-D12 começa classificando como “sem fonte primária” algo que a própria coleta já documentou.

Redação: “Cadência, limiar e formulário específico permanecem sem validação primária localizada; conversão permanente e intermediação pela equipe estão documentadas.”

**2. US$ 20 em holdings não é pagamento mínimo.**

A proposta compara “valor mínimo por destinatário” ao suposto limiar de elegibilidade. [Rascunho:234](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-1834-lane2.md:234).

**Falha:** alguém com US$ 100 em tokens recebe US$ 0,05; o protocolo declara falsamente refutado um piso de US$ 20 em holdings.

São necessárias posições **no instante de elegibilidade**, preço/oráculo e regra de agregação por proprietário. Sem conhecer esse instante e a política externa, o limiar permanece **não mensurável**. Pagamentos observados acima do limiar também não o confirmam: faltam elegíveis não pagos e controles abaixo dele.

**3. M-D12 precisa reconciliar caixa por ativo, sem taxa constante nem dupla contagem.**

Registrar:

- `chain`, mint completo, programa/versão, conta distribuidora;
- assinatura, índice da instrução interna/externa, sucesso, slot, commitment, horário do bloco e `received_at`;
- destinatários efetivos, autoridade e fee payer separados;
- mint do ativo efetivamente transferido, quantidade bruta e decimais — `quote_mint` em coluna distinta.

Usar a identidade **saldo inicial + créditos − distribuições − outras saídas = saldo final**, por conta/ativo e intervalo. Não somar novamente campos que reportam a mesma taxa; os docs descrevem campos antigos e novos coexistindo. [Docs arquivados:100](C:/dev/project-hunter/.claude/state/plantao-meme/raw-lane14/09_gh_docs_HOLDER_REWARDS_README.md.txt:100).

**Falha:** saldo anterior pago hoje faz distribuído/acumulado diário superar 100%; assumir 0,30% em todo par produz um déficit fictício.

Cadência exige **moeda-horas com cobertura**, contagens por janela e intervalos incompletos nas extremidades. “Compatível no período observado” é melhor que “confirmado” para uma regra operacional geral. Queima de PUMP e existência de formulário precisam de investigações próprias; não são resolvidas por essa instrução.

**4. M-P38 tem corte correto, mas ainda não está fechada contra look-ahead.**

`received_at ≤ L` é necessário. Também precisam estar disponíveis até L a comprovação da migração, decodificação, enriquecimentos e **todos os controles**. Uma migração descoberta depois de L não admite decisão retroativa. [Rascunho:238](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-1834-lane2.md:238).

Fixar:

- População prospectiva de migrações da coorte original; nunca top-50 posterior.
- Pool e orientação base/quote determinados antes do teste.
- Compras/vendas por assinatura distinta **por mint/pool**; transações com ambos os lados em categoria explícita.
- `S=0, B>0`: razão indefinida, com indicador “sem vendas”; `B=S=0`: “sem atividade”; cobertura insuficiente: desconhecido.
- B, S e total publicados junto da razão. 43/1 e 43.000/1.000 têm a mesma razão e precisão muito diferente.

**Falha:** vendas chegam atrasadas e um problema de ingestão vira “pressão compradora”.

**5. Separar retenção total de previsão posterior a L.**

M-P18b usa preço de referência inicial da migração. Logo, parte do desfecho já ocorreu durante os cinco minutos usados pela feature. [Fila:113](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:113).

Isso **não é automaticamente look-ahead**, mas pode produzir associação mecânica.

**Falha:** compras nos primeiros cinco minutos elevam o preço nesse intervalo; M-P38 parece prever retenção mesmo sem informação sobre o restante do dia.

Manter M-P18b como desfecho comparável e testar incrementalmente controlando o retorno migração→L. Para previsão estritamente futura, acrescentar `P(migração+24h)/P(L)`, com referência, defasagem e unidade congeladas. Morte comprovada, ausência de negociação, falha de coleta e horizonte imaturo permanecem separados; eventos anteriores a L devem aparecer no fluxo da coorte.

**6. Corrigir a faixa de mcap/liquidez e limitar as interpretações de WOFI.**

A faixa dos sete pares é **91,2–445,2×**, agregado **330,84×**, não 450–1.000×. [Rascunho:135](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-1834-lane2.md:135).

| Número | Leitura defensável |
|---|---|
| **43,37:1** | Razão entre somas de contagens reportadas em `h24`; não compradores únicos, volume líquido ou prova de bots. Pares jovens têm exposição inferior a 24h. |
| **10 × 1,03%** | Dez posições aproximadamente iguais, somando **10,28349%** do supply reportado; não dez controladores independentes nem controle comum demonstrado. |
| **159 insiders** | Valor de `graphInsidersDetected` do provedor, com quatro redes; não identidades verificadas. |
| **“correlation (20)”** | Flag cuja descrição aponta similaridade de saldos; não coeficiente de correlação ou probabilidade de fraude. |
| **LP 100% locked** | Declaração sobre LP; não garantia de saída, estabilidade de preço ou segurança. |

O bruto contém **vinte** posições próximas de 1,028349%, não apenas dez. [Rugcheck:70](C:/dev/project-hunter/.claude/state/plantao-meme/raw-lane18/32_rugcheck_wofi_top.json:70), [Rugcheck:278](C:/dev/project-hunter/.claude/state/plantao-meme/raw-lane18/32_rugcheck_wofi_top.json:278).

**Falha:** esses números viram rótulo de fraude ou filtro de entrada sem validação. A soma de capitalizações também não representa capital aportado ou valor liquidável.

**7. Trocar “ordem de vigilância medida” por “cronologia reconstruída deste evento”.**

Os horários do bloco, merge, publicação e recebimento pelo Radar são relógios distintos. O RPC foi consultado depois; o anúncio foi recuperado por ID horas após sua publicação. A nota anterior já reconhece essa distinção. [Nota do dia:1007](C:/dev/project-hunter/obsidian/02-MARKET/Meme/2026-09-12.md:1007).

**Falha:** projetar ganho operacional de 95 minutos para um monitor que nunca demonstrou detectar naquele instante.

Redação: “Neste evento, o bloco estimado antecedeu o merge, o post identificado e a reportagem. Não medimos a latência de descoberta de monitores concorrentes nem estabelecemos o primeiro aviso público.”

Trocar também “nunca”, “ninguém” e “único sinal é silêncio” por **“não encontrado nas fontes e condições consultadas”**. Vídeo não assistido, HTTP 429 e casca HTML não demonstram ausência. `orders` vazio comprova apenas ausência de registros retornados naquela consulta.

## NICE-TO-HAVE

- Publicar os sete mints e respectivos pools completos numa tabela de evidência.
- Para US$ 370 M versus US$ 452,66 M: “valores não reconciliados; período, base de valorização e denominador do supply precisam coincidir”. Não concluir erro somente pela diferença.
- Corrigir “~6,5 h após o post”: às 18:45 tinham passado aproximadamente **4h45**.

## O QUE EU FARIA DIFERENTE

M-D12 seria pré-condição de **interpretação mecanística**, sem bloquear coleta ou análise associativa de M-P34. Não selecionaria apenas moedas que efetivamente pagaram: pagamento pode depender da atividade e criar viés.

M-P38 teria previsão “**sem ganho incremental detectável**”, comparação temporal reservada e multiplicidade declarada. “Separa por bots” exige evidência independente de bots; não pode explicar qualquer resultado depois.

## CONCORDO COM

Preservar a cronologia, exigir distribuição observada, usar fita própria e tratar os WOFI como exploração. **Nenhum desses achados justifica, sozinho, filtro de entrada.**

## OBSIDIAN

- **Meme/2026-09-12** — acrescentar parecer do run 18, números corrigidos e limites de fonte/cronologia.
- **Hipoteses-do-plantao** — M-D12 própria; M-P38 exploratória com denominadores, disponibilidade, ganho incremental e censura fechados.
- **KB-0094** — registrar conversão permanente já documentada e distinguir mecanismo descrito de distribuição observada.
- **KB-0095** — acrescentar “Rewards → creator” como observação datada de VEY71…, sem convertê-la em classificação on-chain.