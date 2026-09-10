---
tags: [knowledge, nota, plantao, liquidez, covariancia, mean-reversion, redundancia, m3]
tema: o papel de liquidez de uma estratégia é o sinal de uma covariância computável só do histórico (Aldridge 2026) — e o que isso pode e não pode dizer sobre as versões da `mean_reversion`
fonte: Irene Aldridge, "Liquidity-Based Audit of Algorithmic Trading Strategies", arXiv 2606.29018v2 (v1 27/06/2026, v2 13/08/2026, 32 p.) — HTML completo lido três vezes no plantão T3.64, run 5 (faixa 1)
fonte_url: https://arxiv.org/html/2606.29018v2 · https://arxiv.org/abs/2606.29018
lido_em: 2026-09-10
evidencia: teoria (teoremas com hipóteses sobre o processo e a política) + calibração em CRSP diário 2016–2025 (21 183 373 ações-dia); nada de cripto no texto; nenhuma medição própria; correções da Astra sobre a definição de c_t e π e sobre o alcance do corolário N²
hipotese_testavel: sim — D-P13 (diagnóstico descritivo, depois de D-P15 e D-P14): Cov(c_t, π_t) por versão × mercado nos 90 dias, com c_t causal e π na grade completa; sem expectativa de sinal pré-registrada
astra: concorda
status: arquivada
owner: sexta-feira
updated: 2026-09-10
confiança: "?"
---

# Auditoria de liquidez: o sinal de uma covariância (Aldridge, arXiv 2606.29018v2)

> Nota crítica de teoria externa com protocolo ainda não testado — **não** é um classificador validado
> no Hunter nem sustentação empírica de perda N² (Astra, 2026-09-10). Rascunho com todas as URLs e horas:
> `.claude/state/plantao/2026-09-10-0730-lane1.md`. `confiança` fica `?` porque a evidência é teoria +
> calibração em ações diárias, sem cripto e sem medição nossa.

## O que afirma

1. **Regret = soma de covariâncias.** Para uma política π̂_t que responde ao vetor c_t ("asset return
   innovations or factor realizations"), o regret acumulado é Regret^(T)(Π) = Σ_t Cov(c_t, π̂_t(c_t))
   (Teorema 3.6). Daí: "the sign of a single, easily computed statistic classifies the strategy's
   liquidity role exactly. This requires only the observed trajectory {(c_t, π̂_t(c_t))} and no knowledge
   of B, the strategy's signal, or its optimization problem". Cov > 0 = consumidora de liquidez; Cov < 0 =
   provedora. No *black-box audit* o custo do estimador cai de O(T·K·nd) para O(T·nd).
2. **Equilíbrio de liquidez e N².** Com N estratégias, a condição L = Σ_i Cov(c_t, π̂_{i,t}) = 0
   (Corolário 7.20); a violação dá "welfare loss scaling as N² in the strategy-correlation coefficient".
   O HTML não devolveu a fórmula fechada — só a frase; o corolário acrescenta hipóteses de correlação,
   equilíbrio e impacto que **não** são as do teorema 3.6.
3. **Calibração (ações, diário).** CRSP 2016–2025: AR(1) de −0,054 a −0,029 nos anos normais; COVID (2020)
   spread implícito de 0,90 % para 2,52 %/dia; 2022 "AR(1) autocorrelation collapses to near-zero"
   (ρ̂ = −0,0036). §10.5 lista cinco confundidores que inflam |ρ̂| (tamanho, bid-ask bounce, aglomeração
   de vol, momentum cross-section × série, provisão de liquidez); o spread implícito explica R² = 0,138
   do spread cotado.
4. **O que o texto não diz.** Não menciona cripto, Bitcoin nem perpétuos. Não há "três regimes"
   (reversão / pico de fragilidade / colapso) — isso era paráfrase de buscador registada no run 3; o
   §10 tem três **episódios** (baseline, COVID, choque de juros) e "regime" só aparece como *trending*
   (ρ > 0) vs *mean-reverting* (ρ < 0).

## Onde foi mostrado

Ações americanas, retornos diários, 2016–2025; sem custos de transação explícitos na calibração; a
"fragilidade" é lida do AR(1) do painel, não de uma estratégia real. Nada intradiário, nada de
perpétuos, nada de funding.

## Como mediríamos aqui

Sobre `agent_signals`/`signal_outcomes` dos 90 dias do replay (EXP-0025), por versão × mercado, com as
correções da Astra como parte do protocolo:

- **c_t = r_t − Ê[r_t | F_{t−1}]**, com o estimador fixado e ajustado só ao passado (média móvel causal
  declarada antes; **não** "retorno menos média do dia" — a média do dia completo usa futuro e a
  acumulada não é inovação). Alinhar c_t com a decisão tomada **depois** da barra fechada; o retorno
  posterior responde a outra pergunta (desempenho).
- **π_t ∈ {0, 1}** como proxy descritiva numa **grade completa** de barras elegíveis (inclusive sem
  posição; indisponibilidade não vira zero); separar posição mantida de mudança de posição (Δπ). Só
  entradas dão π constante e Cov = 0.
- Reportar sinal, magnitude e IC por blocos de dia, por versão e mercado; **sem expectativa de sinal
  pré-registrada**: a regra combina desconto à média com fechamento acima do meio da barra
  (`mean_reversion_v1.py:224`) e pode comprar barra positiva de recuperação — Cov > 0 nessa escala não
  refuta reversão, e Cov < 0 não prova execução provedora (comprar agressivamente uma queda também dá
  sinal negativo).

## Hipótese testável no Lab

Não é hipótese de edge; é o diagnóstico **D-P13** em [[Hipoteses-do-plantao]], exploratório e por
último na ordem da Astra (D-P15 contabilidade de funding → D-P14 fronteira de custo → D-P13). A
redundância entre versões (4,33 por aposta em [[KB-0083-uma-hora-de-34-r-deriva-e-impulso]]) **não** se
mede com o N² desta nota: N cópias da mesma aposta dão soma N·R e variância N²·Var(R) sem impacto
nenhum — confundir isso com perda superlinear fabricaria confirmação. Fica com a H-P13 (cap por ocupação
sob o mesmo orçamento agregado de risco); "R agregado contra número de versões na barra" é associação.

## Por que pode falhar

Hipóteses do teorema (processo e média da política) não verificadas no nosso dado; c_t mal definido vira
look-ahead; π só nas entradas dá covariância nula por construção; barras de 15 m em perpétuos com
funding e pedágio (`custo_R = 0,0020/(stop_atr × ATR%)`, [[KB-0076-por-que-perdemos-2026-09-08]]) não
são o ambiente calibrado; os cinco confundidores do §10.5 valem aqui também.

## Segunda opinião (Astra)

`astra-review-plantao-20260910-0730.md` (2026-09-10 11:47–11:51 BRT): concorda que a nota **mereça
existir** como crítica de teoria externa e protocolo não testado; must-fix incorporados acima (c_t causal,
grade completa de π e Δπ, retirar Cov < 0 obrigatório, retirar "N² explica a KB-0083"); pede tocar a
KB-0083 para distinguir duplicação de exposição, variância e impacto — fora do escopo do plantão.

## Relacionados

[[Strategy Backlog]] · [[KB-0083-uma-hora-de-34-r-deriva-e-impulso]] ·
[[KB-0086-ic-positivo-nao-paga-o-pedagio-btc-perp-5-min]] ·
[[KB-0082-reversao-de-15-minutos-o-sinal-e-o-fluxo]] · [[KB-0076-por-que-perdemos-2026-09-08]] ·
[[Plantao/2026-09-10]] · [[Hipoteses-do-plantao]] · [[11-KNOWLEDGE/Index|Conhecimento]]
