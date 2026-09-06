## RESUMO

**H1 vale como diagnóstico do movimento de preço, mas não mede slippage real. H2 é testável, com restrições. E há duas correções importantes na premissa: nossa entrada já ocorre depois do pico de 10 segundos; temos suporte a fluxo agregado de 1 minuto.**

Revisão como `quant-engineer`, em modo OPINIÃO.

**1. H1: o que podemos medir com velas de 1 minuto?**

Para uma marca `T`, usando a vela `[T,T+60s)`, podemos medir:

| Medida | O que permite afirmar |
|---|---|
| `10.000 × (C/O − 1)` | Deslocamento entre primeiro e último negócio do minuto |
| `10.000 × (H/O − 1)` e `10.000 × (L/O − 1)` | Extremos negociados relativos à abertura |
| `10.000 × (O[T+60]/O[T] − 1)` | Diferença entre referências de entrada separadas por um minuto |
| Volume, quantidade de negócios e amplitude | Intensidade agregada do minuto, sem localizar o pico dentro dele |

**Não permitem identificar** preço aos 10 segundos, sequência dos extremos, bid/ask no instante da ordem, profundidade disponível, impacto do nosso tamanho ou preço executável após determinada latência. Nem permitem extrair exatamente os 60 segundos posteriores a uma decisão às `12:00:11`.

Nosso preço hipotético é `open × 1,0006`: **6 bps por lado**, compostos por metade do spread total mais slippage; a taxa entra separadamente. Isso está explícito em [pricing.py:35](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:35) e [pricing.py:47](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:47).

Logo:

- `H/O − 1 > 6 bps` **não prova** slippage superior a 6 bps: pode ser movimento posterior à entrada.
- Preço sintético dentro de `[L,H]` **não prova** execução possível para nosso tamanho.
- Preço sintético acima de `H` mostra uma hipótese mais adversa que os negócios observados naquele minuto; **não calibra o custo real**.

Eu reformularia H1 para: **“Quanto o preço se desloca entre referência, abertura elegível e minuto seguinte, e quão sensível é o resultado aos custos assumidos?”**

Para estudar os 10 segundos, precisamos de trades ou agregados nessa resolução. Para estimar custo executável, também precisamos de cotações/profundidade, tamanho e latência; trades isolados não bastam.

**2. H2: timing, limite de 120 segundos e persistência**

A avaliação usa fechamentos de 15 minutos, mas `decision_at` é lido do relógio **depois da avaliação**, em [decide.py:162](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:162). A abertura escolhida é estritamente posterior a esse instante, em [plan.py:48](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/plan.py:48).

Exemplos derivados dessa regra, com referência `12:00:00`:

| `decision_at` | Entrada atual | H2: atual + 1 minuto | Limite |
|---|---|---|---|
| 12:00:11 | 12:01:00 | 12:02:00 | 120 s: permitido |
| 12:01:11 | 12:02:00 | 12:03:00 | 180 s: recusado |

O limite conta **desde `source_bar_close`**, e só recusa valores superiores a 120, em [plan.py:94](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/plan.py:94).

**Portanto, a entrada atual não coincide com o pico de `12:00:00–12:00:10`.** Se “segunda barra após a marca” significa a vela que abre às `12:01`, isso já corresponde ao primeiro exemplo atual. H2 precisa significar inequivocamente **uma barra adicional à abertura atualmente elegível**.

Atrasar é compatível com persistência anterior à abertura, desde que a alternativa seja escolhida e congelada antecipadamente. O caminho atual verifica a confirmação após o commit e recusa confirmação atrasada em [confirm.py:76](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/confirm.py:76). **Não vale observar o minuto e depois escolher qual abertura teria sido melhor.**

**3. O achado de 4–12 horas serve para nosso horizonte?**

Serve como **motivação de pesquisa**, não como validação da momentum. O artigo mede desequilíbrio dos primeiros **10 segundos**; a análise de horizontes usa regressões na amostra completa, distinta do teste fora da amostra dos retornos de 10 segundos. Aos 4 h, a decomposição aponta predominância do componente de fluxo defasado, não autoriza atribuir o efeito genericamente aos indicadores técnicos. [Artigo, §§6.1–6.2](https://arxiv.org/html/2607.09426v1#S6)

Além disso, retorno acumulado em 4 h não é o mesmo resultado de uma operação com stop, alvo e invalidação antecipada. Nosso horizonte conta da entrada, em [progress.py:74](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/progress.py:74), e os toques podem encerrar antes, em [walker.py:145](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:145).

**Mas não estamos totalmente sem fluxo:** `candles` contempla `volume` e `taker_buy_volume`, e o coletor os persiste, em [market_data.py:55](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:55) e [persist_rows.py:124](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:124). Se preenchidos e válidos:

`desequilíbrio_1m = 2 × taker_buy_volume / volume − 1`

Isso permite uma hipótese própria sobre o **primeiro minuto**. Não reconstrói o desequilíbrio de 10 segundos. Não consultei o banco para confirmar cobertura. E usar esse minuto como filtro exige esperar sua conclusão e disponibilidade: não podemos inserir esse dado retroativamente na decisão original.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

## TESTES

Não executados: revisão estática e consulta ao artigo, sem simulação nem consulta ao banco. Nenhum resultado empírico novo é afirmado.

## MUST-FIX

Correções necessárias **na nota e no protocolo proposto**, sem apontar um defeito novo de implementação:

- **Corrigir a coincidência temporal.** Cenário: comparar entrada às `T` contra `T+60` e apresentar como baseline versus H2, quando o baseline começa em `T+60`. Estaríamos comparando políticas diferentes das descritas.
- **Não chamar excursão de slippage medido.** Cenário: preço sobe 15 bps depois de uma execução barata; classificar esses 15 bps como custo leva a uma calibração falsa.
- **Não excluir silenciosamente recusas de H2.** Cenário: o atraso adicional ultrapassa 120 s ou perde a geometria; comparar apenas operações sobreviventes pode favorecer artificialmente a variante.

## NICE-TO-HAVE

Separar a análise por ativo, hora UTC, marcas `00/15/30/45`, fase efetiva de entrada e liquidez. Mais volume e volatilidade no artigo não demonstram, por si, spread maior ou execução pior.

## O QUE EU FARIA DIFERENTE

**4. Minha sequência concreta seria:**

1. **Auditar o timing registrado:** distribuição de `decision_at − source_bar_close`, `entry_bar_open − source_bar_close`, confirmação e recusas.
2. **Executar H1 descritiva:** medir `[T,T+60)`, a vela da entrada efetivamente planejada e a diferença até a abertura seguinte. Publicar medianas, caudas e cobertura; separar movimento referência→entrada dos 6 bps adicionados.
3. **Comparar uma única H2:** `abertura_baseline + 60s`, mantendo 120 s, parâmetros e níveis congelados. Recalcular geometria, saídas e funding. O horizonte continua 4 h desde cada entrada.
4. **Reportar preço e resultado separadamente:** diferença pareada de preço; resultado em bps e R; todas as recusas e censuras. R sozinho pode enganar porque seu denominador muda com a entrada.
5. **Tratar retrospectiva como exploração:** reservar período futuro, controlar dependência entre ativos por blocos temporais e registrar a política de execução como variante própria. Não substituir o protocolo vigente.

Não mudaria os 6 bps com base apenas neste artigo ou no OHLC. Primeiro faria sensibilidade; calibração exigiria observação de execução.

## CONCORDO COM

Concordo em priorizar medição e testar atraso sem presumir melhora. O artigo justifica investigar execução, mas seu ganho bruto de aproximadamente 0,5 bp em 10 segundos não sustenta uma estratégia isolada após custos. [Artigo, §5.3](https://arxiv.org/html/2607.09426v1#S5)

## OBSIDIAN

- **KB-0009 — O efeito do quarto de hora:** registrar limites do OHLC, timing correto e diferença entre evidência de 10 segundos e hipótese de 1 minuto.
- **Momentum Agent:** explicitar referência temporal versus `decision_at`, com exemplo `12:00:11 → 12:01:00`.
- **EXP-0001-momentum-v1:** acrescentar proposta de diagnóstico, preservando o protocolo congelado.
- **Market Collector:** documentar disponibilidade potencial e cobertura a verificar de `taker_buy_volume`.
- **Strategy Backlog:** registrar H2 como candidata única de execução, sujeita ao limite de 120 s e validação futura.