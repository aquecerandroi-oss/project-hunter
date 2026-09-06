---
tags: [knowledge, nota, momentum]
tema: Momentum e rompimentos
fonte: Jegadeesh & Titman (1993, Journal of Finance); Moskowitz, Ooi & Pedersen (2012, Journal of Financial Economics)
fonte_url: https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1993.tb04702.x · https://www.sciencedirect.com/science/article/pii/S0304405X11002613
lido_em: 2026-09-06
evidencia: estudo revisado
hipotese_testavel: sim
astra: concorda
---

# Momentum acadêmico: o que existe e o que não se transfere para 15 minutos

## O que afirma

São duas famílias distintas que o jargão de mercado mistura. **Momentum transversal**
(Jegadeesh & Titman, 1993): ordenar ações pelo retorno passado e comprar as do topo contra as do
fundo produziu retorno positivo em horizontes de 3 a 12 meses; a configuração mais citada
(formação de 12 meses, manutenção de 3, com intervalo de uma semana) rendeu cerca de 1,5% ao mês, e
parte desse excesso se dissipa nos dois anos seguintes ao primeiro ano. **Momentum de série
temporal** (Moskowitz, Ooi & Pedersen, 2012): não compara ativos entre si — o **próprio** retorno
dos últimos 12 meses de um instrumento prediz o retorno seguinte, e isso apareceu em 58 contratos
futuros e a termo (índices, moedas, commodities, juros) ao longo de mais de 25 anos, positivo em
**todos** os contratos examinados, com reversão parcial acima de 12 meses.

## Onde foi mostrado

Ações americanas (1965–1989) no primeiro; 58 futuros líquidos, mais de 25 anos, no segundo.
Horizonte de formação e manutenção medido em **meses**. Nenhum dos dois é intradiário, nenhum é
cripto, nenhum é perpétuo, e nenhum usa barra de 15 minutos. Custos de transação são discutidos,
mas na escala de rotatividade mensal — não na escala em que uma perna de ida e volta custa dezenas
de pontos-base sobre um alvo de fração de por cento.

## Como mediríamos aqui

A `momentum_v1` decide no fechamento de 15 minutos e vive 4 horas ([[EXP-0001-momentum-v1]]). Nada
na literatura acima diz o que acontece nesse horizonte. O que dá para importar honestamente é a
**forma** do sinal de série temporal — o sinal do retorno próprio em janela maior — usado como
**filtro de admissão**, não como gatilho.

**Inventário verificado das features (M2), porque a proposta original estava errada.** Os retornos
registrados são `return_1m`, `return_5m`, `return_15m`, `return_1h`, `return_4h` (mais as variantes
`_live` de 1m/5m/15m/1h). **`return_24h` não existe** — verificado em
`packages/indicators/hunter_indicators/features/price.py:141-153`, onde os calculadores são
instanciados com `minutes` em 1, 5, 15, 60 e 240. A janela de 24 h aparece só em
`distance_from_24h_high` e `distance_from_24h_low`, que medem **posição na faixa**, não direção.

## Hipótese testável no Lab

`momentum_v3_trend_gate` — idêntica à `momentum_v1` em geometria, custos, horizonte e política de
reentrada, com **uma única** alteração: exigir `return_4h > 0` no instante da decisão
(`source_bar_close`), como condição de **admissão**.

- `default_parameters`: os mesmos de `momentum_v1`, mais `trend_gate_feature = "return_4h"`,
  `trend_gate_min = "0"`.
- Semântica congelada: o gate decide **entrar ou não**; não altera stop, alvo, invalidação nem
  rearme. O gate reprovado tem de sair como `no_entry` do episódio-base, e **não** como episódio
  que nunca existiu — senão a comparação mede duas populações diferentes.
- Alvo: expectancy líquida em R do grupo aprovado maior que a do grupo base, em população com
  horizonte maturado.
- **Refutação (versão corrigida pela Astra):** pré-registrar um ganho mínimo relevante `δ` em R
  antes de olhar o dado. Com `Δ = E_aprovados − E_base`, o IC95% por blocos de tempo decide:
  limite superior abaixo de `δ` refuta; limite inferior acima de `δ` sustenta; o resto é
  inconclusivo. Piso de amostra: ≥ 100 outcomes avaliáveis **no grupo aprovado** e ≥ 30 dias
  distintos — piso, não garantia de precisão.
- Diagnóstico obrigatório de "filtro que só encolhe a amostra": com `p` = fração aprovada,
  `E_gate − E_base = (1 − p) × (E_aprovados − E_bloqueados)`. Se as duas expectancies forem
  iguais, o gate está selecionando sem ganhar nada; se `p ≈ 1`, ele não faz nada. Por isso os
  **bloqueados também são acompanhados**, sem entrada hipotética, apenas para medir a diferença.

## Por que pode falhar

- **Importação indevida de horizonte.** A evidência é mensal; usá-la a 15 minutos é hipótese nova,
  não resultado herdado. É a razão de o gate entrar como candidato e não como "melhoria óbvia".
- **Amostra sem ganho.** O caso mais provável: o gate corta 40% dos sinais e a expectancy fica igual,
  com intervalo de confiança maior porque sobrou menos dado.
- **Look-ahead pelo dado tardio.** `return_4h` tem de ser calculado **até** `source_bar_close` e
  estar disponível na decisão; ausência é `unavailable`, nunca "retorno negativo". Sem isso, uma
  leitura posterior contamina a seleção.
- **Rearme contaminando a comparação.** Se o gate oscilar e o episódio rearmar
  (`services/strategy-worker/hunter_strategy_worker/episodes.py`), a coorte com gate ganha entradas
  extras e a diferença deixa de ser "filtragem".
- Multiplicidade: `return_1h`, `return_4h`, 7 dias e limiares diferentes são **variantes distintas**
  e contam como tentativas — ver [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]].

## Segunda opinião (Astra)

Concorda com o desenho e com testar **uma** alteração de cada vez, preservando a `v1`. Quatro
correções aceitas: (1) escrever "a transferência entre horizontes **não está demonstrada**" em vez
de "não se transfere" — nenhum dos artigos testa nem refuta 15 minutos em cripto; (2) **`return_24h`
não está no conjunto registrado** — verifiquei e ela está certa, o teto é `return_4h`; (3) a
refutação por piso de amostra é fraca, tem de haver `δ` pré-registrado e intervalo de confiança por
blocos de tempo; (4) precisão histórica: 1,49% ao mês é uma configuração específica de
Jegadeesh & Titman, e a dissipação ocorre nos dois anos **seguintes ao primeiro**, não "em dois
anos". Dois must-fix incorporados como semântica congelada do candidato: o gate é só admissão (não
mexe em saída nem em rearme) e o retorno é congelado em `source_bar_close`.

Divergência: nenhuma. Ela sugeriu começar por 24 h "pela simplicidade e pelo limiar natural zero" —
adotei `return_4h` porque é a janela mais longa que **existe**; 24 h exigiria feature nova e vira
outro candidato, com custo de implementação, não de parâmetro.

## Relacionados

[[Strategy Backlog]] · [[KB-0002-momentum-e-reversao-em-cripto]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] · [[EXP-0001-momentum-v1]] ·
[[Momentum Agent]] · [[Features]]
