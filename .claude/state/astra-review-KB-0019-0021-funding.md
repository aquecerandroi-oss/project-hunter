## RESUMO

**As três notas têm valor, mas precisam de correções antes de entrar no backlog.** A KB-0020 identifica uma omissão real, porém descreve incorretamente o caminho executado neste checkout. A KB-0021 troca uma medida por outra com justificativa forte demais.

**`funding_change_8h` não produz valor no fluxo padrão local examinado. Isso não prova “100% `warmup` em produção”.** Há um bloqueio anterior: o histórico do scanner nasce vazio e não encontrei chamada ao carregador. Sem consultar a versão implantada e seus dados, a conclusão deve ficar restrita ao código local.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit. Não li `.env`.

## TESTES

Não executei pytest nem SQL nesta revisão somente de leitura. Fiz rastreamento estático das definições, escritores, carregadores e consumidores.

A busca:

```text
rg -n 'load_deriv_history|\.deriv_history' services packages infra -g '*.py' -g '!test*'
```

encontrou a definição/exportação do carregador e a leitura de `self.deriv_history` pelo scanner, **nenhuma chamada ao carregador**. Isso é evidência do checkout, não telemetria de produção.

## MUST-FIX

### KB-0019 — O que a nossa `funding_rate` mede de fato

**1. Código: o diagnóstico central está correto, mas a promessa de instrumentação está incompleta.**

`write_funding` escreve taxa, tipo e horário no mesmo grupo; o decoder transporta esses campos; `FundingRate.compute` devolve a taxa sem interpretar tipo ou fase. O detector usa `funding_rate`, nas duas caudas. Evidências: [hot_state.py:308](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:308), [hotstate.py:276](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/hotstate.py:276), [deriv.py:74](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/deriv.py:74), [detectors.py:177](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/detectors.py:177).

Duas ressalvas:

- **Não é simplesmente o último valor que chegou.** A escrita rejeita timestamps menores ou iguais ao existente. Um settlement recuperado depois de uma estimativa mais recente pode não substituir o hash. [hot_state.py:83](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:83)
- **A idade já participa da qualidade.** `funding_ts` alimenta a proveniência e o orçamento de frescor; o que falta é interpretação de tipo/fase, não todo tratamento temporal. [quality.py:220](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/quality.py:220)

**Correção obrigatória:** “Tudo já está no `MarketContext`; custa uma linha por campo” confunde o contexto do scanner com o caminho dos sinais do Lab. O construtor do `strategy-worker` monta seu contexto com candles e elegibilidade, sem passar funding. [context.py:75](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/context.py:75)

**Cenário de falha:** acrescentar campos ao envelope sem ligar a leitura causal produz apenas ausências; buscar o hash atual ao reprocessar uma decisão antiga pode introduzir informação posterior.

**2. Hipótese: a primeira etapa é uma auditoria válida; a refutação da segunda não funciona.**

Distribuição uniforme de tempo até funding **não implica ausência de informação**. Uma variável uniformemente distribuída pode explicar fortemente outra.

Eu exigiria:

- Denominador: todos os sinais da população congelada, incluindo funding ausente, vencido e tipo desconhecido.
- Mistura: `N_estimated/N_total`, `N_realized/N_total`, `N_missing/N_total`.
- Comparação fora da amostra: baseline por hora versus baseline acrescida de tipo, intervalo e fase.
- Critério prévio de ganho mínimo e incerteza. Resultado impreciso é inconclusivo.

**Cenário de falha:** descartar uma variável útil apenas porque as decisões se distribuem uniformemente ao longo do ciclo.

**3. Premium e acoplamento: falta distinguir tempo restante de fase.**

`next_funding_time − as_of` fornece tempo restante. Sem a duração do intervalo, não fornece fase normalizada: 30 minutos restantes têm sentidos diferentes em ciclos de uma e oito horas. O `DerivSnapshot` tem o próximo horário, mas não um campo de duração do intervalo. [context.py:124](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:124)

A documentação também exige precisão: a compressão automática ocorre quando a **taxa liquidada** atinge o limite; tocar o limite durante sua formação não basta. A fórmula geral ajusta pela duração do intervalo. [Binance — funding](https://www.binance.com/en/support/faq/detail/360033525031).

**4. Retiraria:** “oito horas antes é quase ruído”, “custa uma linha por campo” e a refutação baseada em uniformidade. Não há medição apresentada que sustente essas frases.

### KB-0020 — `funding_change_8h` nunca calcula

**1. Código: existem dois bloqueios, e a nota só identifica o segundo.**

| Situação | Resultado sustentado pelo código |
|---|---|
| Scanner iniciado pelo fluxo padrão local | Histórico vazio → `missing_input` |
| Histórico preenchido exclusivamente por `load_deriv_history` | Só contém OI; com funding atual presente → `warmup` |
| Histórico fornecido com funding próximo do alvo | A calculadora pode produzir a diferença |

A inicialização não fornece histórico; o campo nasce como dicionário vazio, e `advance` usa `[]` quando não encontra o mercado. `_history_entry` transforma vazio em entrada ausente. [main.py:80](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/main.py:80), [scanner.py:77](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/scanner.py:77), [scanner.py:136](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/scanner.py:136), [context.py:151](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/context.py:151).

O carregador realmente seleciona apenas OI; `DerivObservation.funding_rate` fica `None`. `_reference` elimina essas observações. [repo.py:78](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/repo.py:78), [context.py:145](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:145), [deriv.py:42](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/deriv.py:42).

Entretanto, `FundingChange` retorna `missing_input` antes dessa busca quando falta snapshot, taxa atual ou histórico. Se recebe referência válida, calcula normalmente. [deriv.py:156](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/deriv.py:156).

**Cenário de falha:** corrigir apenas o SQL do carregador deixa a feature indisponível porque ninguém o chama. O mesmo histórico vazio também bloqueia `open_interest_change_*`. [deriv.py:105](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/deriv.py:105)

**2. Hipótese: trocar “100% warmup” por uma previsão condicionada.**

Denominador: vetores do produtor, versão e janela declarados que deveriam conter a feature. Contar separadamente:

- Chave ausente.
- Valor presente.
- Valor ausente por motivo.
- Ausência de vetores no período.

Um valor computado na mesma versão e caminho refuta a previsão de indisponibilidade. Banco vazio não confirma nada.

**Retirar a suposta refutação por OI indisponível.** Dois defeitos podem coexistir; ausência de OI não desfaz a omissão de funding. Neste checkout, há inclusive evidência de causa compartilhada anterior.

**3. A alternativa `market_snapshots` não está pronta para a correção proposta.**

A tabela possui funding amostrado, mas **não possui `funding_kind` nem timestamps individuais de origem**. Embora exista a coluna `next_funding_time`, o escritor examinado não a preenche. `DerivObservation` também não carrega tipo. [market_data.py:73](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:73), [sampling.py:202](C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:202), [context.py:145](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:145).

**Cenário de falha:** carregar essa tabela e “registrar junto o tipo” exige informação que não foi preservada. Não é possível recuperá-la com segurança consultando o tipo atual.

Mesmo `estimated − estimated` pode comparar intervalos e fases diferentes. A subtração é matematicamente válida, mas sua interpretação como mudança de posicionamento exige controlar esses estados.

**4. Retiraria:** “para sempre”, “ninguém tinha percebido”, “só a consulta decide” e “uma consulta adicional por mercado por varredura” como custo inevitável. O carregamento pode ser agrupado e incremental; ainda não há implementação nem medição desse custo.

A tolerância de ±48 minutos está corretamente identificada. Ela permite referências entre 7h12 e 8h48 atrás do corte, mas a idade da leitura atual também importa. [deriv.py:135](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/deriv.py:135)

### KB-0021 — Funding como preço de posicionamento

**1. Código: os campos existem, mas falta sustentação temporal para tratá-los como um par sincronizado.**

`market_snapshots.price` vem de `ticker.last`; `index_price`, do hash de derivativos. São lidos em pipeline sem transação. O timestamp persistido é arredondado para o início do minuto após a leitura. [sampling.py:184](C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:184), [sampling.py:202](C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:202).

**Cenário de falha:** uma leitura às 12:00:40 recebe chave 12:00:00. Juntá-la a uma decisão das 12:00:05 pelo timestamp do minuto pode usar informação futura. Além disso, ticker e índice podem representar instantes distintos, mesmo passando individualmente pelo filtro de frescor. [sampling.py:83](C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:83)

**2. Hipótese: exploratória, mas a refutação promete demais.**

Expectancy “indistinguível” entre extremos pode significar pouca amostra, ruído, relação não monotônica ou composição diferente de mercados. Não autoriza encerrar toda a linha “funding/base como regime”.

Definiria:

- Cobertura sobre todos os sinais elegíveis.
- Expectancy por decil sobre entradas com outcome líquido avaliável, incluindo expirados; pendentes, censurados e custos indisponíveis separados.
- Estratégia, versão e horizonte fixados.
- Cortes dos decis congelados antes da validação e incerteza considerando dependência temporal e entre mercados.
- Refutação restrita à especificação testada, mediante equivalência dentro de uma margem econômica previamente definida.

**Cenário de falha:** descartar o tema inteiro porque os extremos não diferem numa amostra pequena ou porque o efeito está nos decis intermediários.

**3. A proposta de premium se sustenta como medida distinta, não como medida independente.**

A mediana não é uma soma. No regime padrão, `mark = index × (1 + funding × fase)` **somente quando esse candidato é selecionado**. O segundo candidato usa base suavizada do livro; o terceiro usa preço do contrato. Logo, não procede afirmar que `mark − index` é mecanicamente funding “em boa parte do tempo” sem medir qual candidato prevalece. [Binance — Mark Price](https://www.binance.com/en-IN/support/faq/detail/360033525071).

Minha conclusão: **manteria ambas como medidas distintas**, sem presumir ganho incremental. `last/index − 1` evita inserir explicitamente aquela fórmula, mas não é o Premium Index da Binance, calculado a partir de preços de impacto do livro. [Binance — funding](https://www.binance.com/en/support/faq/detail/360033525031).

Outros acoplamentos relevantes:

- Funding influencia incentivos de arbitragem e negociação; último preço não fica economicamente independente.
- Índice compartilhado pode gerar movimento comum nos dois prêmios.
- Última negociação sofre efeito de spread, lado agressor e baixa frequência de negócios.
- Mark influencia liquidações, que podem alterar fluxo e preço negociado. [Binance — Mark Price](https://www.binance.com/en-IN/support/faq/detail/360033525071).
- Taxas por intervalos diferentes e mudanças na fase podem aparentar mudança de pressão sem uma comparação homogênea.

**4. Retiraria as conclusões econômicas categóricas.**

“Há mais gente pagando para ficar comprada” não é uma contagem inferível do funding: contratos abertos têm os dois lados; número de participantes e intensidade de demanda não são equivalentes.

Também substituiria “estado não é previsão” por **“estado não constitui, sozinho, evidência de capacidade preditiva no nosso horizonte”**. O próprio BIS investiga e relata poder preditivo do carry para quedas futuras, sem que isso valide nosso uso em quatro horas. [BIS — Crypto carry](https://www.bis.org/publications/working-paper-1087-crypto-carry).

Retiraria ainda:

- “Não serve”, aplicado a `mark − index`.
- “Prêmio honesto” e “desequilíbrio de fato”.
- “Resolução de 1 minuto contra 8 horas do funding”: confunde amostragem com liquidação; nosso parser recebe a taxa no stream `markPrice@1s`. [streams.py:261](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:261)
- “Sem custos na maior parte das análises”, enquanto sustentado apenas por leitura de resumos. He et al. explicitamente estudam limites com custos. [Fundamentals of Perpetual Futures](https://arxiv.org/abs/2212.06888).

## NICE-TO-HAVE

- **KB-0019:** distinguir idade do evento de liquidação de idade de recebimento; documentar horário vencido e intervalo desconhecido.
- **KB-0020:** registrar timestamp da referência escolhida e distância efetiva ao alvo.
- **KB-0021:** usar nome explícito como `last_index_basis_fraction`; comparar com midpoint como diagnóstico de ruído, sem assumir superioridade. Tratar preço ausente e índice não positivo, além de índice nulo.

## O QUE EU FARIA DIFERENTE

Escreveria os núcleos assim:

- **KB-0019:** “A feature conserva a taxa publicada, mas não interpreta tipo nem fase. Precisamos medir esses estados no caminho efetivo dos sinais, com proveniência causal.”
- **KB-0020:** “O fluxo local não alimenta histórico de derivativos; o carregador disponível também omite funding. São dois bloqueios distintos, ainda sem confirmação operacional.”
- **KB-0021:** “Funding e bases descrevem aspectos relacionados do mercado. Compararemos medidas sincronizadas para investigar informação incremental, sem atribuir independência ou previsão por construção.”

## CONCORDO COM

Separar estimativa de liquidação; observar antes de alterar decisões; não inventar alinhamento entre séries; distinguir diferença absoluta de funding de variação relativa de OI; e não transferir resultados de arbitragem para uma estratégia direcional de quatro horas.

## OBSIDIAN

- **KB-0019 — O que a nossa funding_rate mede de fato:** corrigir caminho de instrumentação, fase versus tempo restante e critério de refutação.
- **KB-0020 — funding_change_8h nunca calcula:** registrar os dois bloqueios, retirar “100% warmup” e separar checkout de produção.
- **KB-0021 — Funding como preço de posicionamento:** moderar causalidade, preservar medidas distintas e acrescentar sincronização e denominadores.
- **Features / Workers / Open Bugs:** documentar histórico não alimentado e impacto também nas variações de OI.
- **Market Collector:** registrar metadados não preservados nos snapshots e limite causal do timestamp por minuto.
- **Strategy Backlog:** manter as propostas como instrumentação e pesquisa exploratória, sem edge presumida.