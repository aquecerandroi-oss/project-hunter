---
tags: [knowledge, nota, memecoins, social, onchain, flag]
tema: meme coins / dados sociais e on-chain (depende de flag)
fonte: Mancino (arXiv 2512.11850); Xiang et al. (arXiv 2512.00377); leitura do nosso código
fonte_url: https://arxiv.org/abs/2512.11850 · https://arxiv.org/abs/2512.00377
lido_em: 2026-09-06
evidencia: preprint (dois, lidos em resumo) + leitura de código
hipotese_testavel: não — é inventário do que faltaria
astra: pendente
---

# Social e on-chain — a linha que não atravessamos

## O que afirma

A parte da literatura de meme coin que eu consegui ler é **em boa medida a parte que usa dado que
não temos**: criação de token, concentração de carteiras, difusão social, wash trading
em pool de liquidez. E a nossa arquitetura tem o lugar preparado para isso — e **nada dentro dele**.

`enable_social_intelligence` é uma flag declarada em `packages/core/hunter_core/settings.py:119` com
valor padrão `False`, publicada no `/health` (`apps/api/hunter_api/health.py:85`) e exibida na tela
de sistema do frontend (`apps/web/components/system/feature-flags-table.tsx:27`) — e **sem um único
`if` que mude comportamento**. A precisão é da Astra: ela tem consumidores de **exibição**, e zero
consumidores **funcionais**. A tabela `intelligence_events` existe com colunas, índices e chaves
estrangeiras (`packages/core/hunter_core/db/models/intelligence.py:34-58`) e **não tem nem escritor
nem leitor**.

Isto é uma nota de leitura com inventário, **não** uma hipótese. Não há candidata de estratégia aqui,
e é deliberado.

## Onde foi mostrado

**O que a literatura mede, e por que não se transporta.**

- **Mancino (arXiv 2512.11850)** mede a Pump.fun na Solana no 4º trimestre de 2024: até **71,1%**
  dos tokens cunhados na cadeia, **40 a 67,4%** das transações de DEX, e **menos de 2%** dos tokens
  chegando a uma DEX principal. Todo o objeto do trabalho vive **antes** de existir perpétuo.
- **Xiang et al. (arXiv 2512.00377)** constroem o ME2F com três dimensões: **dinâmica de
  volatilidade** (a única que nós conseguimos calcular), **dominância de baleias** (exige
  distribuição de carteiras on-chain) e **amplificação por sentimento** (exige série de menções). Dois
  terços do arcabouço são inacessíveis para nós.
- Buscas por evidência aberta de menções em redes sociais como preditor de retorno em perpétuos de
  meme devolveram material de divulgação, não estudo com método declarado. **Nada disso foi citado.**

**O que existe no nosso lado.**

| Peça | Onde | Estado |
|---|---|---|
| Flag `enable_social_intelligence` | `settings.py:119` | declarada, padrão `False`, **zero consumidores funcionais** (só exibição em `/health` e na tela de sistema) |
| Flag `enable_onchain` | `settings.py:120` | idem — **nunca testada em condicional** |
| Tabela `intelligence_events` | `db/models/intelligence.py:34-58` | esquema completo (fonte, `dedupe_hash`, `occurred_at`, `asset_ids` com índice GIN, `classification` em JSONB), **sem escritor e sem leitor** |
| Tipos de fonte previstos | `domain/enums.py:645-655` | NEWS, REDDIT, X, GOOGLE_TRENDS, ONCHAIN, WHALES, LISTINGS, UNLOCKS, ANNOUNCEMENTS |
| Detector `SOCIAL_SPIKE` | enum de tipos de anomalia | **não registrado** entre os oito armados de `detectors.py` |
| Contrato documentado | `docs/DATABASE.md:445-449`, `docs/ROADMAP.md:125,128` | Fase 2 = notícias, listagens, anúncios com LLM; Fase 3 = on-chain, baleias, narrativa e social |
| Qualquer adaptador de DEX | — | **não existe.** Nenhuma menção a pump.fun, Raydium, Solana ou Dexscreener no repositório |

## Como mediríamos aqui

Não medimos. O que dá para escrever é o que **precisaria existir** para que a primeira pergunta
social virasse testável, e a lista é útil porque impede que "ligar a flag" pareça uma tarefa:

1. **Um coletor por fonte, com TRÊS carimbos de tempo, não um.** Eu tinha escrito que bastava
   guardar `occurred_at` do evento em vez do instante da nossa ingestão. **Não basta** — a Astra
   apontou o cenário exato: notícia publicada às 10h00, ingerida às 10h07, classificada às 10h08,
   entrando retrospectivamente numa decisão das 10h01. Precisa de **quando o evento ocorreu**,
   **quando ele chegou** e **quando a classificação ficou disponível**. O esquema já separa
   `occurred_at` de `ingested_at` (`db/models/intelligence.py:48-49`); o terceiro carimbo não existe,
   e informação enriquecida **nunca retroage**.
2. **Ligação evento → ativo** (`asset_ids`), que para meme coin é o passo mais difícil e mais sujeito
   a erro: o mesmo apelido aparece em dezenas de tokens, e o nosso universo já tem símbolos que só
   existem em chinês.
3. **Classificação versionada** com o modelo e a versão gravados em `classification`, para que uma
   troca de modelo não reescreva a história.
4. **Uma feature no `StrategyContext`.** Hoje ele carrega `candles_1m`, `funding`, `open_interest`,
   `eligible` e `eligibility_reason` — e mais nada
   (`packages/core/hunter_core/strategies/base.py:109` em diante). Qualquer sinal social exige
   **mudança de contrato**, do mesmo peso do item 19 e do item 20 do backlog.
5. **Uma linha de base sazonal.** Menções têm ciclo diário e semanal muito mais forte que preço;
   "pico de menções" sem linha de base por hora é o mesmo erro do limiar de volatilidade da
   [[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]].

E antes de tudo isso, o passo zero: `enable_social_intelligence` hoje é uma flag que **não desliga
nada**. Uma flag sem consumidor dá a impressão de que existe um recurso desligado, quando o que
existe é uma coluna. Isso é do mesmo gênero do `OPEN_INTEREST_SPIKE` "armado e mudo" da terceira
rodada ([[KB-0020-funding-change-8h-nunca-calcula]]) — e vale a mesma regra: **consertar ou
desarmar honestamente é decisão de contrato, não faxina.**

## Hipótese testável no Lab

**Nenhuma.** Esta nota não entra no [[Strategy Backlog]] como candidata e não gasta tentativa no
[[Registro de Tentativas]]. É o outro lado da linha que o brief desta rodada pediu para marcar:
**depende de dado que não temos**.

O único item que ela deixa é de higiene, e vai para as páginas de contrato, não para o backlog de
estratégia: **declarar no `/health` e na tela de sistema que `enable_social_intelligence` e
`enable_onchain` são marcadores de fase sem implementação**, para que ninguém — nem o Everton, nem
uma sessão futura minha — leia "desligada" como "pronta e desligada".

## Por que pode falhar

- **Li os dois preprints em resumo**, não integralmente. Os números de participação da Pump.fun e a
  ordenação de risco do ME2F vêm dos resumos e da página de abstract; nenhuma metodologia deles foi
  conferida por mim.
- **A ausência de consumidor da flag foi verificada por busca textual**, não por análise de fluxo.
  Se houver consumo indireto (por exemplo, por nome de configuração montado em tempo de execução),
  a busca não pegaria — mas nada nas fontes lidas sugere isso.
- **"Social prediz retorno de meme" continua sem evidência aberta que eu tenha conseguido
  verificar.** Registro isso como resultado da busca, não como conclusão: pode existir literatura
  boa que eu não achei, e há muito material de fornecedor com números sem fonte que eu recusei citar.
- **O risco de reflexividade é grande e específico deste dado.** Se uma métrica social virar
  entrada de decisão, ela vira alvo de manipulação — e a literatura de pump-and-dump que a
  [[KB-0061-pump-and-dump-o-detector-que-precisa-de-25-segundos]] resume descreve exatamente grupos
  organizados que produzem sinal social de propósito. Uma feature social sem defesa contra isso é um
  canal de ataque, não uma vantagem.

## Segunda opinião (Astra)

Revisão de 2026-09-06 (`.claude/state/astra-review-KB-0062-0065-memecoins.md`). Foi a nota menos
corrigida do bloco — ela conferiu o inventário e disse que está correto —, com três ajustes:

1. **O requisito temporal que eu propus ainda permitia look-ahead.** `occurred_at` é necessário e
   insuficiente; falta o instante em que o evento **e a classificação** ficaram disponíveis à
   estratégia, com o cenário das 10h00/10h07/10h08 escrito acima.
2. **"Zero consumidores" virou "zero consumidores funcionais"** — `/health` e o frontend leem as
   flags.
3. **Retirou "os resultados mais fortes da literatura"**: conferir que os números dos resumos batem
   com Mancino e Xiang et al. não valida transporte para perpétuos, nem me autoriza a hierarquizar a
   literatura que eu não li inteira.

## Relacionados

[[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]] ·
[[KB-0061-pump-and-dump-o-detector-que-precisa-de-25-segundos]] ·
[[KB-0020-funding-change-8h-nunca-calcula]] ·
[[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] ·
[[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] · [[Index]]
