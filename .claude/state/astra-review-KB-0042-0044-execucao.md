**RESUMO**

As três notas precisam de correções antes de aprovação:

- **KB-0042:** a limitação do `open` é real; a decomposição que “fecha” em 6 bps é falsa.
- **KB-0043:** manteria o diagnóstico de um minuto, mas retiraria sua interpretação como teste de seleção adversa.
- **KB-0044:** existe outro produtor: **o refresh REST já escreve volume no ticker**. O problema é a disputa entre escritores, não ausência de produtor.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão em modo OPINIÃO.

**TESTES**

Não executei pytest nem consultas ao banco. As contagens históricas são as publicadas nas notas, não medições reproduzidas nesta revisão.

Conferi os caminhos de código e executei contas com `[decimal]` no PowerShell:

```text
open=99,99 → fill sintético=100,049994 → custo contra mid=4,9994 bps
open=100,01 → fill sintético=100,070006 → custo contra mid=7,0006 bps
open seguinte igual ao inicial → retorno contra P_entry=-5,996402… bps
```

Li o preprint original da KB-0043. Os links da Binance redirecionaram para uma página genérica; não os considero validação documental dos detalhes.

**MUST-FIX**

**KB-0042 — O `open` não é preço executável**

**1. Corrigir a identidade e cortar a soma de 6 bps.** Em [KB-0042:25](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0042-o-open-nao-e-preco-executavel.md:25), o primeiro termo é `preço executável − mid`; o segundo é definido como `preço executável − open`. Eles se sobrepõem. Depois, a tabela troca o segundo por `open − mid`.

Para uma compra, definindo `O=open`, `M=mid`, `A=melhor ask` e `V=VWAP` de um tamanho fixo, todos no mesmo instante:

```text
V − O = (A − M) + (V − A) − (O − M)
          meio spread   arrasto     referência
```

Para expressar essa identidade em bps, use o mesmo denominador em todos os termos. O custo percentual contra `O` exige ainda converter o denominador.

O código calcula apenas `spread/2 + slippage` e aplica o resultado ao `open`; **não estima nem transforma um erro de referência em valor absoluto**. Portanto, “o Lab cobra o erro sempre adversamente” não descreve o algoritmo. Ele aplica um acréscimo adverso enquanto o erro assinado já está embutido na referência. [pricing.py:35](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:35), [pricing.py:47](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:47).

**Cenário:** mid 100, bid 99,99, ask 100,01, ordem pequena. Se `open=ask`, atravessar imediatamente custa zero adicional contra esse `open`; se `open=bid`, custa aproximadamente 2 bps. O Lab acrescenta 6 nos dois casos, produzindo aproximadamente **7 ou 5 bps contra o mid**. Não converteu o erro de referência sempre para o lado adverso.

A [tabela:48](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0042-o-open-nao-e-preco-executavel.md:48) também falha porque:

- `3,47 − 1,15` não estima o arrasto mediano: mistura amostras e **diferença de medianas não é mediana da diferença**.
- No modelo simples de negócio no melhor bid/ask, `open−mid` vale aproximadamente **±meio spread**, não ±spread inteiro.
- Sinal desconhecido não implica distribuição simétrica.
- Negócios que consomem níveis podem ocorrer além do melhor preço pré-negócio; um spread não é limite universal.

**Cortaria integralmente a soma e a conclusão “bem escolhida por acaso ou por instinto”.** A ressalva posterior de populações diferentes não salva uma identidade errada.

**2. Retirar os critérios que diagnosticam viés ou atraso sem identificá-los.** [KB-0042:75](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0042-o-open-nao-e-preco-executavel.md:75).

Mediana zero e IQR estreito não demonstram ausência de viés médio. **Cenário:** 80% dos erros são zero e 20% são +10 bps: mediana e IQR zero, média +2 bps.

Também `open` fora de `[bid,ask]` não prova atraso do instrumento. **Cenário:** a primeira compra consome o ask; o book imediatamente posterior já tem preços diferentes, mesmo com recepção rápida. É necessário distinguir book anterior/posterior ao negócio, timestamps e sequência. “Próximo da abertura” não resolve isso.

---

**KB-0043 — Seleção adversa**

**1. Corrigir a perspectiva econômica e retirar a identificação causal.** [KB-0043:16](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0043-selecao-adversa-o-custo-que-so-aparece-depois-do-fill.md:16), [KB-0043:48](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0043-selecao-adversa-o-custo-que-so-aparece-depois-do-fill.md:48).

No artigo, markout positivo na direção do agressor é adverso **para a contraparte passiva**. Os autores explicitamente não equiparam “toxicidade” a informação privada. Os números citados conferem, mas 0,27/2,20 bps e 59/1.201 dólares pertencem à janela de validação de 11–20 de julho, em BTC/ETH/SOL; o universo geral é maior. [Artigo, §3 e Tabela 2](https://arxiv.org/html/2608.04373v3#S3).

A ressalva de venue está bem encaminhada, mas eu retiraria “transporta-se a ordem de grandeza relativa”. Transportam-se o conceito e o método como candidatos a pesquisa. Hyperliquid mantém um livro com prioridade preço-tempo, executado em ordem de consenso por blocos; “por bloco” não significa leilão uniforme. [Artigo, §2](https://arxiv.org/html/2608.04373v3#S2).

**Cenário:** compramos, sai uma notícia pública negativa e o mid cai. Isso não demonstra que o vendedor sabia mais. Tampouco comprar após alta prova que somos informados, identifica a contraparte como formador de mercado ou demonstra spread efetivo maior que o cotado. Cortaria essas afirmações.

**2. Manter `EXEC-H`, mudando sua pergunta e seu critério.** [KB-0043:61](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0043-selecao-adversa-o-custo-que-so-aparece-depois-do-fill.md:61).

A medida tem utilidade como **retorno entre aberturas após a entrada planejada**. Não reproduz markout entre mids, nem garante exatamente 60 segundos entre os negócios.

O principal diagnóstico deve ser contra o `open` bruto. Contra `P_entry`, um mercado perfeitamente parado já produz **−5,9964 bps**, devido ao acréscimo sintético de entrada. A segunda versão pode aparecer como sensibilidade contábil, não evidência adicional de seleção adversa. [pricing.py:47](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:47).

Dois critérios precisam sair:

- **“Negativo nos stops significa comprar topo.”** Condicionar ao resultado futuro seleciona trajetórias perdedoras. **Cenário:** entradas aleatórias num passeio sem tendência também podem mostrar retorno inicial negativo entre operações que depois atingem o stop.
- **“Mediana próxima de zero encerra seleção adversa nesta escala.”** **Cenário:** queda de 5 bps nos primeiros dez segundos e recuperação até o minuto: retorno de um minuto zero apesar da excursão inicial. Além disso, falta de significância não demonstra equivalência a zero.

Publicaria primeiro todas as entradas com horizonte observado, incluindo operações encerradas antes de um minuto; nelas, o retorno posterior é trajetória do mercado, não PnL da posição. Cortes por outcome seriam apenas descrições secundárias.

---

**KB-0044 — O que morre em dez segundos**

**1. A explicação central precisa ser substituída: o produtor REST existe.** [KB-0044:31](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0044-o-que-morre-em-dez-segundos.md:31).

O caminho completo é:

| Caminho | Evidência |
|---|---|
| Refresh busca tickers de 24 h | [universe.py:107](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:107) |
| Binance usa `/fapi/v1/ticker/24hr` | [rest.py:270](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/rest.py:270) |
| Parser preenche volumes, deixando bid/ask ausentes | [normalize.py:212](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/normalize.py:212) |
| Refresh escreve esses tickers no Redis para os monitorados | [universe.py:181](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:181) |
| WS produz ticker com bid/ask/quantidades, sem volumes | [streams.py:168](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:168) |
| Coalescer escreve o ticker WS no mesmo hash | [coalesce.py:158](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coalesce.py:158) |

Ambos possuem **o mesmo conjunto `TICKER_FIELDS`**. Campos ausentes entram na lista de remoção, e o Lua executa `HDEL`. A atualização só é aceita se seu timestamp superar o anterior. [hot_state.py:48](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:48), [hot_state.py:83](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:83), [hot_state.py:117](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:117).

**Cenário concreto:**

1. REST aceito escreve volume e remove bid/ask.
2. Um snapshot nesse intervalo pode registrar volume sem spread.
3. O próximo ticker WS aceito escreve bid/ask e remove volume.
4. Os snapshots seguintes registram spread sem volume.

Isso explica **mecanicamente** a incompatibilidade relatada e oferece uma explicação consistente para volumes raros. Não permite atribuir individualmente as seis linhas históricas sem examiná-las e conferir a versão executada.

A cadência REST padrão é 900 s, e o snapshot ainda anula campos com timestamp vencido — padrão de 10 s. Aumentar o TTL não corrige a remoção entre escritores. [settings.py:139](C:/dev/project-hunter/packages/core/hunter_core/settings.py:139), [sampling.py:102](C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:102).

**2. TTL não é janela histórica; “permanente” também está errado.** [KB-0044:22](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0044-o-que-morre-em-dez-segundos.md:22).

Cada novo book substitui o anterior com `SET`; os dez segundos são expiração desde a escrita, não dez segundos de versões recuperáveis. [hot_state.py:175](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:175).

**Cenário:** consultar dois segundos depois pode encontrar somente um book posterior, embora nenhum TTL tenha vencido. Além disso, `market_snapshots` tem retenção configurada de 30 dias, não permanente. [prune_partitions.py:96](C:/dev/project-hunter/infra/scripts/prune_partitions.py:96).

**3. `EXEC-I` não torna todas as perguntas respondíveis.** [KB-0044:83](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0044-o-que-morre-em-dez-segundos.md:83).

- Volume de um mercado não basta para reconstruir seu **decil**: falta a população de comparação ou o ranking congelado.
- Carimbo na decisão e na entrada não fornece o mid **depois** da entrada para markout.
- `EXEC-H` por candles não depende desse carimbo; cobertura baixa dele não torna aquele diagnóstico impossível.
- Registrar novamente “no envelope” precisa ser corrigido: o envelope da decisão é escrito uma vez. A observação posterior deve ser um registro separado, associado ao sinal. [envelope.py:3](C:/dev/project-hunter/packages/core/hunter_core/strategies/envelope.py:3).

**Cenário:** carimbos completos em todos os sinais, mas nenhum mid em `entrada+10s` e nenhum universo congelado: continuam indisponíveis o markout proposto e o decil histórico.

**NICE-TO-HAVE**

- KB-0042: retirar “14 bps por minuto ⇒ ~1 bp em quatro segundos”. A KB-0041 mede deslocamentos em janelas de 60–120 s; não uma velocidade linear.
- KB-0043: retirar a afirmação de poder “quase certamente” insuficiente sem cálculo. O limite editorial e o poder estatístico são coisas diferentes.
- KB-0044: publicar janela fixa e consulta da interseção `spread_pct`/volume. Há 53.128 spreads na KB-0037 contra 52.943 aqui; esclarecer se são extrações diferentes.
- KB-0044: `next_funding_time` tem uma causa distinta e direta: é escrito no hot state, mas omitido do dicionário do snapshot. [hot_state.py:308](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:308), [sampling.py:202](C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:202).

**O QUE EU FARIA DIFERENTE**

Preservaria as três notas, com escopos menores: **referências de preço**, **trajetória inicial após o sinal** e **proveniência perdida entre produtores**. Cortaria as justificativas numéricas dos 6 bps, as conclusões causais do markout e a promessa de que um único carimbo resolve tudo.

**CONCORDO COM**

O `open` não garante execução para nosso tamanho; OHLC não calibra sozinho slippage; movimento posterior não deve virar uma segunda cobrança automática; e registrar proveniência vale mesmo sem melhorar o resultado da estratégia.

**OBSIDIAN**

- **KB-0042 — O `open` não é preço executável:** substituir a soma pela identidade assinada e remover os critérios falsos de viés.
- **KB-0043 — Seleção adversa:** corrigir a perspectiva maker/taker e reformular `EXEC-H` como retorno descritivo.
- **KB-0044 — O que morre em dez segundos:** documentar REST↔WS, remoção de campos, TTL e limites do carimbo.
- **Market Collector / Open Bugs:** registrar o conflito de propriedade entre ticker REST e `bookTicker`.
- **KB-0037 — O spread assumido contra o medido:** corrigir a passagem que acrescenta movimento pós-fill ao spread pago e esclarecer as extrações.
- **Strategy Backlog:** ajustar os contratos de `EXEC-G/H/I` conforme esta revisão.