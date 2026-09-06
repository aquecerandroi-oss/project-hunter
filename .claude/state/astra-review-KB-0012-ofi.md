## RESUMO

**A distinção central está correta. Eu manteria H-KB0012a e retiraria H-KB0012b da fila de execução por enquanto.** A candidata não é impossível, mas a justificativa apresentada não sustenta o filtro, e “stop imediato” ainda não define uma medida reproduzível.

Revisão como `quant-engineer`, em modo OPINIÃO.

**1. Estado versus fluxo**

Nossa feature soma **quantidades**, sem ponderar por preço, dos primeiros 20 níveis de cada lado e calcula `(bid − ask)/(bid + ask)`. Usa um único snapshot, sem diferenças temporais: [micro.py:49](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/micro.py:49), [micro.py:132](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/micro.py:132).

A descrição de OFI precisa de uma precisão: as contribuições dependem das mudanças **de preço e quantidade** no melhor bid/ask. Não basta subtrair os tamanhos das filas. Também não é necessário identificar separadamente cada cancelamento e execução: CKS calcula OFI a partir das atualizações das cotações. [CKS, §2 e §3.1](https://arxiv.org/pdf/1011.6402).

**2. Onde já misturamos os conceitos**

Não encontrei OFI implementado ou nossa feature explicitamente renomeada como OFI. A busca textual encontrou o termo na KB-0012 e uma referência à literatura em [KB-0016:32](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0016-quando-o-fluxo-importa-dependencia-de-estado.md:32).

Existe, porém, **ambiguidade de classificação e descrição**:

| Local | Evidência |
|---|---|
| [profile.py:89](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/profile.py:89) | `ORDER_FLOW` inclui `orderbook_imbalance_20`; a descrição fala em quem agride as ofertas. |
| [explanation.py:39](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/explanation.py:39) | O componente aparece como “Fluxo de ordens”. |
| [PIPELINE.md:110](C:/dev/project-hunter/docs/PIPELINE.md:110) | Agrupa imbalance, pressão e velocidade sob “Order Flow”. |
| [Order Flow Agent.md:15](<C:/dev/project-hunter/obsidian/04-AGENTS/Order Flow Agent.md:15>) | Repete esse agrupamento. |

Um componente pode combinar estado e fluxo. Isso não transforma cada entrada em fluxo nem demonstra um erro numérico; a descrição deveria explicitar a mistura.

## ARQUIVOS

Nenhum arquivo criado ou modificado por mim. Nenhum commit.

## TESTES

Não executei testes ou SQL: revisão estática, sem alterações nem avaliação de dados reais.

Executei buscas com `rg`, incluindo arquivos ocultos e excluindo `.env*`, dependências, `.git` e logs. A busca por `\bOFI\b|order.flow.imbalance` em `packages`, `services` e `apps` não retornou correspondências. Conferi também os corpos dos dois artigos.

## MUST-FIX

**1. Retirar a justificativa causal de H-KB0012b.**  
Na [KB-0012:77](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0012-ofi-nao-e-o-nosso-orderbook-imbalance.md:77), profundidade absoluta vira justificativa para um filtro de desequilíbrio relativo. A razão descarta a escala: multiplicar todas as quantidades por mil mantém o imbalance. Além disso, mais quantidade no ask não equivale a mais venda agressora.

**Cenário de falha:** o filtro aceita um book raso e equilibrado, mas rejeita outro muito profundo com predominância de asks, alegando proteção contra impacto. A regra não mede a propriedade invocada.

**2. Definir “imediato” antes de propor o teste.**  
A [KB-0012:79](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0012-ofi-nao-e-o-nosso-orderbook-imbalance.md:79) não fixa janela, denominador ou redução mínima. O Lab acompanha barras de um minuto e registra o fechamento como horário de saída intrabar: [outcomes.py:1](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/outcomes.py:1), [walker.py:104](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:104).

**Cenário de falha:** stops ocorridos aos 2 e aos 58 segundos ficam indistinguíveis; escolher depois a janela que melhorou produz uma conclusão seletiva. “A amostra ficou insuficiente” significa **inconclusivo**, não refutação.

**3. Corrigir “efeitos vivem em segundos” e “três ordens de grandeza”.**  
A generalização da [KB-0012:93](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0012-ofi-nao-e-o-nosso-orderbook-imbalance.md:93) está incorreta. CKS usa intervalos de 10 segundos e verifica agregações até 10 minutos; CCZ estuda previsão de 1 minuto e horizontes de 2–30 minutos. Isso não sustenta previsão em duas horas. [CKS, §3.1](https://arxiv.org/pdf/1011.6402), [CCZ, §4.2–4.3](https://arxiv.org/html/2112.13213v4).

**Cenário de falha:** rejeitar ou justificar uma hipótese usando uma duração que não corresponde ao estudo citado.

**4. Trocar “exige persistir deltas” por “exige observar a sequência de atualizações”.**  
A exigência da [KB-0012:63](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0012-ofi-nao-e-o-nosso-orderbook-imbalance.md:63) é excessiva. É possível calcular OFI incrementalmente com estado anterior e acumulador; reprodução histórica exige guardar informação suficiente. Nosso caminho atual guarda o snapshot top-20 em uma chave substituída: [hot_state.py:175](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:175).

**Cenário de falha:** encomendar armazenamento de deltas completos desnecessariamente ou acreditar que snapshots espaçados recuperam eventos intermediários perdidos. [CKS, §2–3](https://arxiv.org/pdf/1011.6402).

## NICE-TO-HAVE

Na KB-0012, eu cortaria ou qualificaria:

- **“R² da ordem de 70%”**: verificável; substituir por média de **65%**, com referência à tabela 2 e contexto contemporâneo. [CKS](https://arxiv.org/pdf/1011.6402).
- **“Sem prioridade preço-tempo idêntica”**: retirar sem comparação documentada dos mercados.
- **“Custo quase zero”**: retirar até verificar disponibilidade histórica e associação causal aos instantes de decisão.
- **“A diferença será efeito da coleta”**: trocar por “pode confundir efeito do book com qualidade da coleta”.
- **Exemplo 1000/1000**: esclarecer “nos snapshots observados”; igualdade de totais não caracteriza os eventos intermediários.

## O QUE EU FARIA DIFERENTE

**3. Ficaria agora somente no diagnóstico.** O horizonte padrão é 7200 s: [volume_anomaly_v1.py:77](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:77). Isso não impede, logicamente, um filtro de risco inicial; impede tratar os artigos como validação desse filtro.

H-KB0012a deveria medir cobertura, qualidade, idade e disponibilidade **até a decisão**, distinguindo ausência de histórico de feature indisponível. O envelope atual não contém book: [volume_anomaly_v1.py:198](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:198).

Só reconsideraria H-KB0012b como hipótese independente, com janela inicial mensurável, população comparável, tratamento explícito dos ausentes e confirmação futura. O limite de 30% seria uma restrição escolhida, não evidência científica.

## CONCORDO COM

Preservar a distinção estado/fluxo, separar explicação contemporânea de previsão, medir cobertura primeiro e registrar variantes antes de rodar. Não encontrei motivo para alterar a fórmula de `BookImbalance` nesta revisão.

## OBSIDIAN

- **OFI não é o nosso `orderbook_imbalance_20`** — incorporar as correções e manter somente o diagnóstico como próximo passo.
- **Strategy Backlog** — registrar H-KB0012b como não pronta para experimento.
- **Features** — explicitar estado top-20 versus fluxo temporal.
- **Order Flow Agent** — esclarecer que o componente combina métricas de estado e fluxo.