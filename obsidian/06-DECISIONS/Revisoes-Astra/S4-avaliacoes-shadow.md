---
tags: [astra, revisao, shadow-lab, experimentos]
updated: 2026-09-06
---

# Revisão da Astra — as primeiras avaliações datadas do Shadow Lab (S4, 2026-09-06)

Transcrição integral em `.claude/state/astra-review-S4-obsidian.md`. Perguntei sobre cinco coisas
concretas: denominadores e nomes das métricas, se o SQL colado reproduz mesmo os números colados,
se a semântica `as_of` × `read_at` era honesta, se a leitura "v1 × v2 não é comparação de variantes"
estava explícita, e se faltava alguma contagem de cobertura do item 9 da
[[Dialogos/SHADOW|decisão conjunta]].

**Resultado: cinco must-fix, todos aceitos e aplicados antes de publicar as páginas.** Nenhuma
avaliação foi publicada com os defeitos e depois corrigida.

## Os cinco achados

1. **PF de `volume_anomaly` v2 é zero, não nulo.** Eu tinha escrito "nulo com motivo (Σ positivos
   vazio)". Está errado: o denominador **existe** (−7,688202 em perdas), e a soma dos ganhos de um
   conjunto vazio é **zero**, não desconhecida. `SUM(...) FILTER (...)` devolve `NULL` sobre conjunto
   vazio — isso é comportamento do SQL, não uma afirmação sobre o mundo. **Cenário de falha:** uma
   população inteiramente perdedora apareceria como "PF indisponível", escondendo o pior resultado
   possível atrás de uma lacuna. Corrigido com `COALESCE` no numerador; o item 9 exige nulo quando
   faltam **perdas**, não quando faltam ganhos. A regra ficou escrita em [[Strategy Performance]].
2. **O SQL não impunha a coorte declarada.** As consultas não filtravam
   `supporting_features->>'cohort' = 'prospective'` nem `purpose = 'research_only'`. Não houve
   contaminação nesta extração (197 de 197 sinais são `prospective` e `research_only`), mas o SQL da
   página **é o protocolo reutilizável**: no primeiro plantão depois de existir um `replay:<run_id>`,
   prospectivo e retrospectivo entrariam juntos em silêncio. Filtros aplicados nas três consultas.
3. **Faltava a população de horizonte maturado**, exigida pelo item 9. Eu selecionava avaliáveis só
   por `terminal AND r_multiple IS NOT NULL`. **Cenário:** encerramentos rápidos entram na média
   enquanto os lentos continuam `active`, e a composição muda sozinha com o tempo de observação.
   Acrescentei `expires_at <= now()` como contagem à parte — e foi ela que revelou o achado mais
   duro da leitura: **0 dos 57** acompanhamentos avaliáveis do [[EXP-0001-momentum-v1]] tiveram as
   4 h de horizonte disponíveis (no [[EXP-0002-volume-anomaly-v1]], 35 de 72, porque o horizonte é
   de 2 h).
4. **`read_at` documentava a leitura sem permitir reproduzi-la**, e as duas consultas não
   compartilhavam snapshot. **Cenário:** um acompanhamento termina entre a consulta de cobertura e a
   de métricas, as duas recebem o mesmo carimbo editorial e descrevem mundos diferentes. Passei a
   rodar tudo em `BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY`, e a ressalva ficou
   dura: a leitura **não é reconstruível** depois, porque não há histórico de estados preservado.
5. **A cobertura estava declarada como completa com evidência parcial.** `LIKE 'late%'` não prova
   que todos os casos sejam `late:delay` — agora o agrupamento é pelo motivo exato. E o heartbeat
   `hb:strategy:shadow` não é cobertura do experimento: é um contador **operacional**, acumulado em
   memória desde a inicialização do worker, somando as duas estratégias e as quatro versões, sem
   quebra por motivo. **Cenário:** o leitor atribui as mesmas 400 avaliações indisponíveis a cada
   estratégia. Reescrito como agregado operacional, com a cobertura histórica por motivo declarada
   **indisponível** e registrada em [[Open Bugs]].

## Nice-to-have aceitos

- O resumo do índice somava só as coortes v1 (48 + 66); os totais por experimento são **57** e
  **72**. Corrigido em [[Experiments Index]].
- Trocar precisão inferencial não calculada por descrição honesta: "tamanho amostral efetivo perto de
  um" virou "dependência entre observações simultâneas **não estimada**", e "indistinguível de zero"
  virou "evidência insuficiente para concluir".
- A soma escalar de R **não** depende de ordem; retirei a menção a "ordenados por `exit_ts`", que
  sugeria uma trajetória que o SQL não produz.

## Onde discordei

Ela propôs manter as avaliações originais e **acrescentar uma errata datada**. Não aceitei: a regra
de "nunca reescrever" protege avaliação **publicada** — nada disto tinha sido commitado, e uma
errata sobre um texto que ninguém leu seria encenação, não rastreabilidade. Corrigi antes de
publicar e registrei a revisão inteira aqui, que é o rastro que importa.

## Onde ela concordou (e por quê importa)

- `signal_outcomes.signal_id` é chave primária, então o `JOIN` é 1:1 e não multiplica linhas.
- Censurados **contam como entradas**: a censura preserva a entrada já ocorrida, então os 67 de
  `momentum` v1 incluem os 2 censurados. Está dito nas páginas.
- `expired`/`invalidated` **devem** entrar nos encerrados avaliáveis quando o `R_net` é conhecido —
  é o que separa *taxa de lucro líquido* de *taxa de alvo entre toques resolvidos*.
- A sucessão v1 → v2 está corretamente descrita como técnica, não como variante de pesquisa. Com uma
  ressalva dela que absorvi: `params_hash` igual, **sozinho**, não provaria código igual — a
  justificativa depende também da proveniência registrada no `changelog` das linhas de
  `strategy_versions`.

## Relacionadas

[[EXP-0001-momentum-v1]] · [[EXP-0002-volume-anomaly-v1]] · [[Experiments Index]] · [[Strategy Performance]] · [[Open Bugs]] · [[Dialogos/SHADOW]] · [[Mente da Sexta-feira]]
