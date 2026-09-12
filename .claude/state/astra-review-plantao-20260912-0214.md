**RESUMO**

Eu testaria **D-P25 primeiro, H-P29 depois e H-P30 por último**. Papel adotado: `quant-engineer`, em modo OPINIÃO.

D-P25 determina se conseguimos observar a população e seus desfechos. H-P29 oferece uma hipótese simples, mas precisa de régua econômica corrigida. H-P30 exige identidade por operação, histórico completo e correções importantes no contraste e nos relógios.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

Há código inicial: `NormalizedMemeTrade` declara **não ter produtor no T4.1** e seus campos ainda não incluem índice de operação — [models.py:160](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/models.py:160). Portanto, não trataria a disponibilidade desses trades como pré-requisito já cumprido.

**TESTES**

Não executei testes de aplicação, SQL nem a reprodução de Kaplan–Meier. Consultei arquivos e fontes primárias. A revisão independente não ocorreu: a ferramenta de agentes retornou `no thread with id`.

Conferências aritméticas em memória, saída real:

```text
4338 / 655770 × 100 = 0.6615124205132896
1 / (0.9875²)       = 1.025476686428457
```

O primeiro cálculo revela uma inconsistência no próprio Tarantelli: as contagens publicadas correspondem a **0,662%**, não 0,63%. Não escolheria silenciosamente qual número corrigir. [Artigo, §IV](https://arxiv.org/html/2602.14860v1#S4)

**MUST-FIX**

**1. D-P25: medir atraso e exigir 99% de cobertura ainda não basta.**

Começaria com dois trabalhos distintos:

- **Agora, no dataset público:** reproduzir contagens, duplicatas, conflitos de desfecho e distribuição de durações; depois executar a KM publicada como reprodução do instrumento.
- **No coletor Hunter:** medir separadamente descoberta de criações, acompanhamento da curva, conclusão, migração e cobertura dos trades.

Kamat documenta perda de acompanhamento ao sair da página dos 50 mais novos, além de mints registrados primeiro como graduados e depois como timeout. Isso impede interpretar o timeout como observação negativa confiável até 24 h. HR de Telegram tampouco é multiplicador causal de probabilidade. [Artigo corrigido](https://arxiv.org/html/2607.02823v3) · [Dataset e corrigenda](https://zenodo.org/records/21923106)

**Cenário de falha:** recebemos todas as criações com atraso de um segundo, mas deixamos de acompanhá-las aos seis minutos. O p95 de descoberta é excelente; todas as graduações posteriores desaparecem.

Minha especificação para D-P25:

- Amostra independente de **slots finalizados**, reconciliando criações e eventos de conclusão/migração; amostrar somente `complete=true` na mesma API não mede criações ausentes.
- Cobertura por idade, dia, Mayhem, fonte e regra de seleção; separar chegada original de recuperação posterior.
- Para cada horizonte: sucessos comprovados, negativos comprovados e desconhecidos.
- Se a referência independente também for incompleta, publicar **concordância entre fontes**, sem chamar isso de cobertura absoluta.

**Outro cenário:** perder seletivamente 1% das criações permite perder todos os graduados quando a taxa real é 0,2%. Portanto, **99% é um indicador operacional, não garantia de precisão estatística**. O aceite deve considerar quanto os desconhecidos podem alterar o contraste.

Rodar KM não recupera informação ausente: sem último acompanhamento válido e hipótese defensável sobre censura, ela reproduz a cegueira com uma curva elegante.

**2. H-P29: a régua é aplicável à ideia de comprar na curva e segurar, mas somente sob suas hipóteses idealizadas.**

Tarantelli considera entrada na primeira passagem pelo nível, preço marginal, venda na graduação e perda integral quando não há graduação. Ignora custos nessa conta. Os **92,22%** referem-se aos **184.282 tokens com pelo menos 30 swaps**; o detector usa escala robusta baseada em MAD. Não representam probabilidade de perda total para qualquer lançamento. [Artigo, §§VI e VIII](https://arxiv.org/html/2602.14860v1)

Minha derivação para o nosso protocolo seria:

\[
E[\mathrm{PnL}]=pS+(1-p)F-I
\]

onde \(I\) é o desembolso integral, \(S\) o recebimento líquido condicionado ao sucesso e \(F\) a recuperação líquida no outro desfecho. Para \(S>F\):

\[
p>\frac{I-F}{S-F}.
\]

A parábola surge quando \(F=0\), não há custos nem impacto, e a razão entre preços marginais é \((x_g/x)^2\).

As correções necessárias:

- **Unidade:** `vSol` é reserva virtual total, não apenas SOL real depositado. **Falha:** usar SOL real no numerador subestima o preço de entrada e o breakeven.
- **Parâmetros por mecanismo:** não universalizar `115`. O plano já exige conclusão por estado e distingue conclusão de migração — [T4-MEME-RADAR.md:100](/C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:100).
- **Custos nas duas pontas:** sob a simplificação de 1,25% em cada ponta, o limiar sem impacto é multiplicado por **1,0254767**; não se subtrai 1,25 ponto percentual da probabilidade. A taxa efetiva de saída depende do pool/instante — [plano:113](/C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:113).
- **Tamanho e saída executável:** calcular quantidade comprada pela curva e recebimento pela reserva disponível na saída. **Falha:** a célula supera a parábola marginal, mas a venda da posição move o preço e elimina o ganho.
- **Conclusão não garante liquidação naquele preço:** há uma instrução separada de migração. **Falha:** marcar lucro no fechamento da curva quando ainda não existe saída disponível no pool. [Contrato oficial](https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/docs/PUMP_PROGRAM_README.md)

**O dump pré-graduação não deve virar um desconto adicional de 92%.** Se a estratégia realmente segura até graduar, quedas intermediárias já influenciam a probabilidade de chegar lá. Aplicar outro fator de “sobrevivência ao dump” contaria parte do risco duas vezes. Se introduzirmos stop, prazo ou saída por liquidez, mudamos a estratégia e precisamos estimar seus pagamentos próprios.

Eu reescreveria H-P29 em duas perguntas: **há associação entre contagem de trades e graduação?** E **alguma política congelada de entrada/tamanho/saída tem expectativa líquida positiva?**

Para a primeira: uma observação por mint na primeira passagem de cada nível, contagem acumulada até ali, idade registrada e cobertura desde a criação. Snapshot de minuto não garante essa reconstrução.

**Falha concreta:** o token cruza o nível e reverte dentro do minuto; o snapshot perde a passagem. Ou começamos a assinar trades só quando ele progride e o classificamos artificialmente como “poucos trades”. O plano prevê justamente assinatura seletiva — [plano:359](/C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:359).

**3. H-P30: “WT1>0 na primeira hora dobra a graduação” não é o resultado publicado.**

O artigo compara **2,0% com WT1 versus 0,90% sem WT1**. Na tabela por intensidade, **1–5 ocorrências dão 0,50%; 6–25 dão 0,65%**. O agregado não demonstra vantagem para qualquer ocorrência positiva, muito menos na primeira hora. A amostragem é de **1% das moedas**, seguida de suas transações, com exclusões dos casos enormes. [Meme Coin Factories, §§III–IV](https://arxiv.org/html/2609.10246v1)

**Falha:** os poucos tokens com centenas de operações carregam a associação agregada; nosso braço `WT1>0` é dominado por uma ou duas ocorrências e apresenta resultado inverso.

Também corrigiria a justificativa MELT: **84,13% é o rótulo “alto risco”, incluindo anotação manual**. A tabela de preço mostra aproximadamente **72,95% abaixo de 0,4 em 20 minutos**; não sustenta “84,13% abaixo de 0,3”. [MELT, §3.5](https://arxiv.org/html/2602.13480v2#S3.SS5)

Mesmo uma queda comprovada nesses 20 minutos não determina retorno **entre 24 h e 7 d**. **Falha:** o preço desaba antes de 24 h e recupera parcialmente depois; o retorno 24 h→7 d é positivo apesar do colapso inicial.

Minha proposta:

- Para graduação prospectiva, usar marco de **uma hora**, entre tokens ainda não concluídos, com exposição WT1 disponível até esse marco. Graduações anteriores ficam em análise separada.
- Para retorno pós-migração, declarar que a população é **condicionada à migração**. Não é o mesmo denominador de todas as criações.
- Fixar os dois relógios: `created_at` para exposição/graduação; `migrated_at` para esse retorno.
- Se admitirmos migração até o sétimo dia, retorno sete dias depois exige acompanhamento até **14 dias após a criação**.
- “Não melhora” precisa de margem de relevância predefinida e intervalo suficientemente estreito. Resultado não significativo não prova ausência de melhora.

**Falha temporal:** moeda gradua aos quatro minutos; usamos WT1 observado até uma hora para dizer que previmos sua graduação.

**4. WT1 não exige matematicamente índice na PK; deduplicação fiel de trades exige identidade da ocorrência.**

Corrijo a formulação absoluta do meu parecer anterior.

É possível calcular o **indicador binário por transação** decodificando uma transação completa, finalizada e bem-sucedida, e persistir uma linha por `signature` com resultado e versão do detector. Nesse desenho, não precisamos persistir cada trade para responder apenas “esta transação contém WT1?”.

Mas **`signature + (mint, side, amount)` não basta como chave geral de `meme_trades`**:

- Falta a autoridade econômica. WT1 exige o **mesmo endereço**, quantidade de tokens e curva. **Falha:** A compra 100 e B vende 100 na mesma transação; a tupla proposta produz falso positivo. [Definição WT1](https://arxiv.org/html/2609.10246v1#S4.SS1)
- Mesmo acrescentando wallet, conteúdo igual não identifica ocorrência. **Falha:** A compra 100 duas vezes e vende 100 uma vez; duas compras legítimas colapsam numa linha. Volume, contagem e estado reconstruído ficam errados, embora um indicador existencial possa continuar positivo.
- CPI e log podem descrever o mesmo fill. **Falha oposta:** contar as duas representações duplica a operação.

Para armazenamento de trades, manteria **identificador canônico por operação**, derivado de assinatura e posição estável na transação — índice externo, posição interna/evento conforme o decoder. Pode estar em `UNIQUE`, não obrigatoriamente na PK física. Precisa reconciliar WS e backfill e preservar quantidades em unidades-base.

O defeito concreto continua no desenho `(signature, ts)` — [plano:177](/C:/dev/project-hunter/docs/plans/T4-MEME-RADAR.md:177). A necessidade correta é **unicidade da ocorrência**, não uma coluna específica por dogma.

**5. H-P27: 24 h e 7 d por criação são necessários, mas não suficientes.**

A redação atual mistura `complete=true` com migração e equipara calma a `risk-on` — [Hipóteses-do-plantão.md:73](/C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:73).

Eu a substituiria conceitualmente por:

> **H-P27 — associação prospectiva entre volatilidade antecedente do BTC e conclusão da curva.** Para todos os mints elegíveis criados em uma janela prospectiva congelada, medir conclusão até 24 h e 168 h após a criação. Comparar baixa versus alta volatilidade do BTC, calculada exclusivamente com dados disponíveis antes da criação, com definição e limiares congelados. Migração efetiva é desfecho separado. A hipótese direcional é graduação maior sob baixa volatilidade; não implica causalidade nem identifica `risk-on`.

Complementos indispensáveis:

- Coortes por dia UTC, com **os mesmos dias completamente maturados para ambos os horizontes** na comparação principal.
- Denominador de criações reconciliado pela D-P25. Com \(N\) criações, \(S\) sucessos e \(U\) desfechos desconhecidos, publicar limites \([S/N,(S+U)/N]\).
- Separar mecanismo, Mayhem e quote; comparar com composição padronizada previamente definida. Se não houver sobreposição suficiente entre regimes e mecanismos, declarar que não conseguimos separar seus efeitos.
- Incerteza por blocos temporais, preservando dependência entre tokens e horizontes; ajustar os dois testes. Considerar persistência adicional introduzida pela volatilidade de 30 dias.
- “Sem diferença” exige precisão ou margem de equivalência; sessenta dias não garantem quantidade suficiente de episódios independentes de regime.

**Cenários de falha:** usar o fechamento do próprio dia para classificar moedas nascidas de madrugada introduz futuro; um lançamento de Mayhem coincidente com BTC calmo imita efeito de regime; congestionamento em dias agitados perde graduações e fabrica associação negativa.

E **graduações ocorridas hoje / criações de hoje não é graduação em 24 h da coorte de hoje**. A tabela histórica precisa distinguir período de coleta, seguimento individual e razão de fluxos diários — [rascunho:115](/C:/dev/project-hunter/.claude/state/plantao/2026-09-12-0214-lane1.md:115).

**NICE-TO-HAVE**

Manter contagem bruta de trades, contagem sem WT1 e atividade atribuída ao Mayhem lado a lado. Não chamar o restante automaticamente de “orgânico”: outras formas de coordenação continuam possíveis.

**O QUE EU FARIA DIFERENTE**

Congelaria primeiro a auditoria D-P25. Depois, poucas células H-P29 predefinidas e uma janela futura reservada. `n≥200` e Wilson por célula não resolvem dependência nem a seleção da melhor entre muitas células.

H-P30 entraria como associação por intensidade e idade, abandonando a promessa inicial de “dobrar”.

**CONCORDO COM**

Graduação e retorno são desfechos diferentes; market cap não comprova liquidez; ausências não viram zero; Mayhem precisa de atribuição por operação. A prioridade é produzir evidência observável antes de escolher um sinal.

**OBSIDIAN**

- **Fila de hipóteses do plantão de mercado** — registrar D-P25 e corrigir relógios, denominadores e critérios de conclusão de H-P27/H-P29/H-P30.
- **Market Collector** — acrescentar descoberta versus acompanhamento, referência independente e identidade por operação.
- **Correlação com o BTC — e a “meme season” que a nossa janela não contém** — separar volatilidade antecedente, apetite de risco e mudança de mecanismo.
- **Nova revisão: Plantão 2026-09-12 — run 13, faixa 1** — preservar as correções de Tarantelli, WT1 e MELT, com fontes e cenários de falha.