---
tags: [knowledge, nota, perpetuos, funding, open-interest, qualidade-do-dado, bug]
tema: Perpétuos: funding, OI, posicionamento
fonte: Leitura do nosso código — `services/scanner-worker/hunter_scanner_worker/{main.py,scanner.py,context.py,repo.py}`, `packages/indicators/hunter_indicators/features/deriv.py`, `packages/indicators/hunter_indicators/anomalies/detectors.py`
fonte_url: (código do repositório, sem fonte externa)
lido_em: 2026-09-06
evidencia: leitura de código com arquivo e linha, conferida de forma independente pela Astra; **medição no banco não feita** (o portão de permissão desta sessão recusou `psql` na VPS e o Docker local está fora)
hipotese_testavel: sim
astra: concorda — e achou o bloqueio maior que eu tinha perdido
---

# O bloco de derivativos do M2 não é "não usado": ele não computa

## O que afirma

O brief desta rodada dizia que `funding_rate`, `funding_change_8h`,
`open_interest_change_1h/4h` e `mark`/`index` são "o único bloco de features do M2 que nenhuma
estratégia em sombra usa". A leitura do código mostra algo mais forte, e pior: **três dessas
features não conseguem produzir valor nenhum no scanner de produção**, e o detector que depende
delas **não pode disparar**.

São **dois bloqueios distintos e independentes**, empilhados. Corrigir só um não liga nada.

**Bloqueio 1 — ninguém alimenta o histórico.** `Scanner.deriv_history` é um dicionário vazio por
padrão (`scanner.py:77`) e `advance` o consulta com `.get(market.ref.market_id, [])`
(`scanner.py:136`). A única função que o preencheria, `load_deriv_history` (`repo.py:66`), **não
tem nenhuma chamada em todo o repositório fora da própria definição e do `__all__`** — verifiquei
com busca em toda a árvore `.py`. Nem `main.py` (`run_scanner`, linha 80), nem o `_warm`, nem os
laços atribuem esse campo.

Com a lista vazia, `_history_entry` (`context.py:151-158`) devolve `missing(INPUT_DERIV_HISTORY)`, e
aí `ctx.deriv_history.value is None`. As duas calculadoras verificam isso **antes** de qualquer
outra coisa:

- `OpenInterestChange.compute` (`deriv.py:105-112`) → `MISSING_INPUT`.
- `FundingChange.compute` → `MISSING_INPUT`.

Isto é: `open_interest_change_1h`, `open_interest_change_4h` e `funding_change_8h` são
`missing_input` em toda barra, em todo mercado, enquanto o campo não for atribuído. E como o
detector `OPEN_INTEREST_SPIKE` lê `open_interest_change_1h` (`detectors.py:170`), **ele nunca pode
disparar** — não está desarmado como o `LIQUIDATION_CLUSTER` e o `CROSS_EXCHANGE_DIVERGENCE`
(`detectors.py`, `_DISARMED`, com motivo legível por máquina); está armado e mudo.

**Bloqueio 2 — o carregador, quando for chamado, ignora funding.** `load_deriv_history`
(`repo.py:78-84`) seleciona apenas `OpenInterestHistory.ts, open_interest` e monta
`DerivObservation(ts=..., open_interest=row[1])`. `funding_rate` fica `None`, `_reference` filtra
essas observações fora (`deriv.py:42-56`) e `FundingChange` cairia em `WARMUP` — "ainda não, espere
mais dado", uma promessa que este caminho não cumpre.

A omissão do bloqueio 2 é **deliberada e documentada**: o docstring diz que `funding_rates` guarda
uma **liquidação**, não uma leitura amostrada, e parear as duas séries num timestamp inventaria
leituras que nunca existiram. O raciocínio está certo para aquela tabela. O que não estava escrito
em lugar nenhum é a consequência: features registradas, versionadas, listadas como disponíveis em
[[Strategy Backlog]] e em [[Features]], e inertes.

## Onde foi mostrado

No nosso código, hoje, neste checkout. **Não é uma medição operacional.** Não rodei SQL: o portão de
permissão desta sessão recusou executar `psql` na VPS e o Docker local está fora desde o turno da
tarde. Um comportamento diferente em produção — outro produtor de vetores, um caminho da API, um
backfill — derrubaria esta leitura, e é por isso que ela é uma **previsão**, não um resultado.

## Como mediríamos aqui

Consulta sobre os vetores de feature persistidos, com denominador explícito (correção da Astra: "100%
de `warmup`" era previsão errada e sem denominador). Fixando produtor, versão do conjunto de features
e janela, contar **separadamente**:

| Categoria | O que significa |
|---|---|
| chave ausente do vetor | a feature nem foi tentada nessa versão |
| valor presente | **refuta** esta nota para aquele caminho |
| ausente com motivo `missing_input` | compatível com o bloqueio 1 |
| ausente com motivo `warmup` | compatível com o bloqueio 2 |
| nenhum vetor no período | não confirma nem refuta nada |

A previsão desta nota: `missing_input` para as três features, e **zero** disparos de
`OPEN_INTEREST_SPIKE` em `anomalies` desde que o detector foi armado. O segundo é o teste mais
barato de todos e é quase uma prova por ausência — com a ressalva de que ausência de anomalia também
seria compatível com "nenhum mercado ficou anômalo", que é implausível em 200 mercados por dias, mas
não impossível.

## Hipótese testável no Lab

**Não é candidata de estratégia.** É instrumento, e a decisão entre os caminhos tem custo e não é
automática:

- **Caminho A — ligar.** Um laço que preenche `Scanner.deriv_history` a partir de
  `load_deriv_history` (bloqueio 1), com política de janela e de atualização; e, para o funding,
  uma fonte amostrada de verdade (bloqueio 2).
- **Caminho B — desarmar honestamente.** Mover `OPEN_INTEREST_SPIKE` para `_DISARMED` com motivo
  legível por máquina, como já é feito com os outros dois, e marcar as três features como
  indisponíveis em [[Features]] e em [[Strategy Backlog]]. Uma feature que não computa é pior que
  uma ausente: aparece em lista e em backlog como se fosse recurso.

**A alternativa `market_snapshots` para o funding não está pronta**, e este é o achado da Astra que
eu não tinha visto. A tabela guarda `funding_rate` por mercado e por minuto (`market_data.py:82`) —
uma série amostrada, o que `DerivObservation` quer — mas **não guarda `funding_kind`** (a coluna não
existe) e o escritor **não preenche `next_funding_time`** (`sampling.py:196-216`: o dicionário da
linha vai de `price` a `index_price` e não inclui nenhum dos dois). Sem o tipo preservado, ligar o
caminho A para funding produziria diferenças entre uma estimativa em formação e uma taxa liquidada
apresentadas como "variação de funding em 8 h", e **o tipo histórico não é recuperável** consultando
o tipo atual. Mesmo `estimated − estimated` compara fases diferentes do ciclo
([[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]]).

E a tolerância de ±48 min para um lookback de 8 h (`deriv.py:135`) precisa de justificativa ou de
redução antes de qualquer uso: ela admite referências entre 7 h 12 min e 8 h 48 min atrás do corte —
e a idade da **leitura atual** conta junto, não só a da referência.

## Por que pode falhar

- **Corrigir metade.** Consertar só o SQL do carregador deixa tudo indisponível, porque ninguém o
  chama; ligar só a chamada deixa o funding fora. Este é o cenário de falha concreto da Astra.
- **Custo no scanner: desconhecido.** Eu tinha escrito "uma consulta a mais por mercado por
  varredura" como se fosse inevitável. Não é — o carregamento pode ser agrupado e incremental. Não
  há implementação nem medição, então não há número.
- **Desregistrar tem custo de contrato.** `FeatureDefinition` é congelada por versão; tirar feature
  do conjunto v1 é mudança de contrato, não faxina.
- **A minha previsão pode cair por um caminho que não li.** Só a medição decide, e ela depende de um
  acesso que esta sessão não teve.

## Segunda opinião (Astra)

**Ela achou o bloqueio 1, que eu tinha perdido inteiro**, e com isso a nota mudou de tamanho: o
problema não é o funding em particular, é o histórico de derivativos inteiro, e leva junto as duas
features de open interest e o detector `OPEN_INTEREST_SPIKE`. Verifiquei a afirmação dela por conta
própria (busca por `load_deriv_history` em toda a árvore: zero chamadas) antes de reescrever.

Correções aceitas, todas: (1) separar os dois bloqueios; (2) trocar "100% de `warmup`" por uma
previsão condicionada com denominador e categorias; (3) retirar a refutação "se OI também estiver
indisponível o problema não é o funding" — dois defeitos podem coexistir, e neste caso a causa é
**compartilhada**, o oposto do que eu tinha escrito; (4) retirar "para sempre", "ninguém tinha
percebido", "só a consulta decide" e o custo inventado da consulta por mercado; (5) registrar que
`market_snapshots` não preserva `funding_kind` nem `next_funding_time`, o que inviabiliza a correção
como eu a tinha proposto. Nice-to-have aceito: registrar no vetor o timestamp da referência escolhida
e a distância efetiva dela até o alvo.

Divergência: nenhuma.

## Relacionados

[[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]] ·
[[KB-0021-funding-como-preco-de-posicionamento-nao-como-previsao]] ·
[[KB-0025-o-nosso-detector-de-open-interest-so-olha-para-cima]] ·
[[KB-0018-volume-relatado-e-o-denominador-que-usamos]] ·
[[Strategy Backlog]] · [[Registro de Tentativas]] · [[Features]] · [[Anomalies]] ·
[[Open Bugs]] · [[Workers]]
