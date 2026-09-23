## 1. Cobertura

| recorte | linhas | porta fluxo_e_holders | bloco `flow` | progresso | as três lidas |
|---|---:|---:|---:|---:|---:|
| posições reais | 93 | 93 | 93 | 93 | 93 (100.0%) |
| papel | 1219 | 1219 | 1219 | 1219 | 1219 (100.0%) |
| uma por mint (população) | 587 | 587 | 587 | 587 | 587 (100.0%) |

Séries: {'meme_features_15s_v1': 402, 'meme_event_gate_v1': 185}
Teto `max_sells_to_buys` da porta (uma por mint): {'0.6': 502, '1': 85}

| braço | teto razão | n | razão ≥ 0,6 | fluxo < 2 | progresso < 25 | **equilíbrio** |
|---|---:|---:|---:|---:|---:|---:|
| flow_v2/1 | 0.6 | 100 | 0 | 3 | 23 | **0** |
| flow_v2/2 | 0.6 | 280 | 6 | 12 | 12 | **0** |
| flow_v2/3 | 0.6 | 47 | 0 | 5 | 1 | **0** |
| flow_v2/5 | 0.6 | 2 | 0 | 0 | 0 | **0** |
| flow_v2/6 | 0.6 | 29 | 0 | 4 | 12 | **0** |
| flow_v2/8 | 1 | 29 | 29 | 4 | 6 | **0** |
| flow_v2/9 | 0.6 | 12 | 0 | 1 | 2 | **0** |
| operator/5 | 0.6 | 14 | 0 | 0 | 7 | **0** |
| operator/5 | 1 | 56 | 14 | 7 | 2 | **1** |
| operator/6 | 0.6 | 18 | 0 | 4 | 6 | **0** |

**Decisões com `equilibrio = verdadeiro` (uma por mint): 1 de 587** (todas as linhas: 2 de 1312). Censuradas depois de escolher uma por mint: 0.

## 2. Moinho

# H-013 — moeda em equilíbrio (resto × equilíbrio) — NÃO CONFIRMA

> Origem: perda real SHORT 23/09/2026 17:39 BRT (−18,7 %)  ·  impressão digital do pré-registo: `886db52395f9`
> Limiar congelado: **0.5**  ·  efeito mínimo relevante (MRE): **+0.0500**

## Pré-registo (escrito antes de correr)

- **Previsão:** decisões com `equilibrio = verdadeiro` rendem menos −0,05 por SOL que as demais, e concentram a fração de perdas ≥ 15 % em até 3 s de posição (saída imediata pelo recuo)
- **Refutação:** limite inferior do IC 95 % (bootstrap por mint) acima de −0,01 por SOL; ou menos de 20 decisões com `equilibrio = verdadeiro` (poucas demais para julgar — registrar como limite de dado); ou os três limiares escolhidos não formam patamar quando cada um é deslocado ±1 degrau
- **Regra de decisão:** CONFIRMA com D>0 (resto−equilíbrio, espelho do bloco), IC inferior>0, p<0,05, D≥MRE 0,05, braço selecionado lucrativo em nível. Planalto do moinho DESLIGADO porque a variável é booleana (degrau real); o patamar pré-registado é verificado fora do moinho, deslocando cada limiar ±1 degrau (0,1 / 1 SOL / 5 pp).
- **Política de limiar:** fixos, congelados no pré-registo: 0,6 / 2 SOL por min / 25 %
- **Congelado em:** 2026-09-23

## Os números

| # | o quê | valor |
|---|---|---|
| 1 | população usada (de 587 linhas lidas) | **587** em 587 clusters |
| 2 | selecionados / resto no limiar congelado | 586 / 1 |
| 3 | média do desfecho: selecionados / resto | -0.0409 / -0.1870 |
| 4 | **D = média(selecionados) − média(resto)** | **+0.1461** |
| 5 | IC 95 % de D (bootstrap de cluster por `mint`) | [+0.1104, +0.1838]  P(D≤0) = 0.000 |
| 6 | IC 95 % de D (bootstrap de blocos) | [+0.1109, +0.1807] em 176 blocos |
| 7 | p de permutação (estratificada por `dia`) | 0.6653 |
| 8 | dinheiro somado na população (Decimal) | `-1.3017349493` |

Censura: 0 linhas sem desfecho, 0 sem a variável, 0 recusadas pela guarda anti-antecipação. Ausente nunca virou zero.

## VEREDITO: NÃO CONFIRMA

- amostra insuficiente: 586/1 contra o mínimo 20 por lado — sem potência, o que não é refutação.

## Curva de limiares — planalto ou pico?

Diagnóstico: **ausente** (0 limiares avaliáveis; maior corrida positiva 0 (0 com IC acima de zero)).

| limiar | n sel/resto | D | IC 95 % |
|---|---|---|---|
| 0.5 | 586/1 | — | amostra insuficiente |

## Baldes por tercis (descritivo, não decide nada)

| balde | n | média | mediana |
|---|---|---|---|
| -0 | 586 | -0.0409 | -0.0740 |
| 0-inf | 1 | -0.1870 | -0.1870 |

## A ressalva que mais importa

a guarda não correu (dispensa declarada: as três grandezas são lidas de meme_proposals.reasons, gravadas pela porta no instante da decisão; não há fita reconstruída nem coluna de instante a guardar) — causalidade é afirmação do operador, não do moinho

Outras ressalvas:

- sem fatia de teste reservada: o resultado é dentro da amostra

## Suposições numéricas declaradas

- desfecho = pnl_sol / tamanho sob a saída de cada braço; custo já no pnl
- uma decisão por mint: real > papel, depois a mais antiga (regra do R73)

Estatística em `float` (contrastes de retorno); dinheiro publicado em `Decimal`. Tempo em UTC.

> Nada aqui autoriza dinheiro real. Um CONFIRMA é candidato a **braço de papel pré-registado**, nunca parâmetro de mesa.


> **Leitura obrigatória (achado da Astra):** com 1 caso de um lado, o IC e o `P(D≤0)` acima NÃO são interpretáveis — nas réplicas que sobrevivem o SHORT está sempre lá com o mesmo retorno e as outras são descartadas. Não citar como evidência. O veredito do moinho (amostra insuficiente) é o que vale.

## 3. Patamar — cada limiar deslocado ±1 degrau (grelha 3×3×3)

D_bloco = média(equilíbrio) − média(resto). Os 7 pontos da regra (centro + 6 vizinhos de um eixo só) marcados com ●.

| razão ≥ | fluxo < | progresso < | ● | n equilíbrio | n resto | média eq | média resto | D_bloco | IC 95 % (mint) |
|---:|---:|---:|:-:|---:|---:|---:|---:|---:|---|
| 0.5 | 1 | 20 |  | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.5 | 1 | 25 |  | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.5 | 1 | 30 |  | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.5 | 2 | 20 |  | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.5 | 2 | 25 | ● | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.5 | 2 | 30 |  | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.5 | 3 | 20 |  | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.5 | 3 | 25 |  | 3 | 584 | +0.1779 | -0.0422 | +0.2201 | sem potência (< 20 por lado) |
| 0.5 | 3 | 30 |  | 4 | 583 | +0.2074 | -0.0428 | +0.2502 | sem potência (< 20 por lado) |
| 0.6 | 1 | 20 |  | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.6 | 1 | 25 | ● | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.6 | 1 | 30 |  | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.6 | 2 | 20 | ● | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.6 | 2 | 25 | ● | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.6 | 2 | 30 | ● | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.6 | 3 | 20 |  | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.6 | 3 | 25 | ● | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.6 | 3 | 30 |  | 2 | 585 | +0.0545 | -0.0414 | +0.0959 | sem potência (< 20 por lado) |
| 0.7 | 1 | 20 |  | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.7 | 1 | 25 |  | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.7 | 1 | 30 |  | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.7 | 2 | 20 |  | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.7 | 2 | 25 | ● | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.7 | 2 | 30 |  | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.7 | 3 | 20 |  | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.7 | 3 | 25 |  | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |
| 0.7 | 3 | 30 |  | 1 | 586 | -0.1870 | -0.0409 | -0.1461 | sem potência (< 20 por lado) |

## 4. Previsão secundária — perdas ≥ 15 % que saem em ≤ 3 s

| grupo | n | perdas ≥ 15 % | das quais em ≤ 3 s | fração | perda rápida / n |
|---|---:|---:|---:|---:|---:|
| equilíbrio | 1 | 1 | 1 | 100.0% | 100.0% |
| resto | 586 | 215 | 2 | 0.9% | 0.3% |

## 5. EXPLORATÓRIO — condições sozinhas e aos pares (fora do veredito)

| condição | n verdadeiro | n falso | média verd. | média falso | D (verd − falso) | IC 95 % (mint) |
|---|---:|---:|---:|---:|---:|---|
| vendas÷compras ≥ 0,6 | 49 | 538 | -0.0586 | -0.0395 | -0.0191 | [-0.1091, +0.0738] |
| fluxo < 2 SOL/min | 40 | 547 | +0.0165 | -0.0453 | +0.0618 | [-0.0752, +0.2171] |
| progresso < 25 % | 71 | 516 | -0.0074 | -0.0457 | +0.0383 | [-0.0466, +0.1324] |
| vendas÷compras ≥ 0,6 E fluxo < 2 SOL/min | 10 | 577 | -0.0374 | -0.0412 | +0.0038 | sem potência (< 20 por lado) |
| vendas÷compras ≥ 0,6 E progresso < 25 % | 8 | 579 | -0.0441 | -0.0411 | -0.0031 | sem potência (< 20 por lado) |
| fluxo < 2 SOL/min E progresso < 25 % | 6 | 581 | -0.1242 | -0.0402 | -0.0839 | sem potência (< 20 por lado) |

## 6. Contrafactual — a porta recusando `equilibrio = verdadeiro`

Base: 93 posições reais (todas, não uma por mint), 29 vencedoras, PnL **-0.3498 SOL**.

| limiares | bloqueadas | vencedoras mortas | PnL removido | PnL com a regra | Δ |
|---|---:|---:|---:|---:|---:|
| 0.6 / 2 / 25 (**congelado**) | 1 | 0 [] | -0.0134 | -0.3364 | +0.0134 |
| 0.5 / 2 / 25 (vizinho) | 1 | 0 [] | -0.0134 | -0.3364 | +0.0134 |
| 0.7 / 2 / 25 (vizinho) | 1 | 0 [] | -0.0134 | -0.3364 | +0.0134 |
| 0.6 / 3 / 25 (vizinho) | 1 | 0 [] | -0.0134 | -0.3364 | +0.0134 |
| 0.6 / 1 / 25 (vizinho) | 1 | 0 [] | -0.0134 | -0.3364 | +0.0134 |
| 0.6 / 2 / 30 (vizinho) | 1 | 0 [] | -0.0134 | -0.3364 | +0.0134 |
| 0.6 / 2 / 20 (vizinho) | 1 | 0 [] | -0.0134 | -0.3364 | +0.0134 |
| 0.5 / 3 / 30 (mais largo (todos +1)) | 2 | 0 [] | -0.0207 | -0.3290 | +0.0207 |

Bloqueadas no limiar congelado:
- `SHORT` 2026-09-23 20:39:16 UTC — compras 39 × vendas 36 (razão 0.92), fluxo 0.39842381 SOL/min, progresso 13.6588 %, PnL -0.0133779380 SOL (-18.7%), posição 3.0 s, saída trailing