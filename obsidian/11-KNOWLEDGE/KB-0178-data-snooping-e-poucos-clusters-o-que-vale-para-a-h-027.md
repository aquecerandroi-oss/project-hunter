---
tags: [knowledge, leitura, estatistica, data-snooping, reality-check, spa, multiplicidade, bootstrap, clusters, hipotese]
tema: "data snooping e inferência — Reality Check de White, SPA de Hansen, o limiar t > 3 de Harvey, Liu & Zhu, o Sharpe deflacionado de Bailey & López de Prado, e o problema de poucos clusters (Cameron, Gelbach & Miller); o que de fato se aplica a uma hipótese única pré-registrada como a H-027"
fonte: "White, 'A Reality Check for Data Snooping' (Econometrica 68(5), 2000 — só o resumo, OpenAlex); Hansen, 'A Test for Superior Predictive Ability' (J. Business & Economic Statistics 23(4), 2005 — só o resumo); Harvey, Liu & Zhu, '…and the Cross-Section of Expected Returns' (RFS 29(1), 2016 — só o resumo); Bailey & López de Prado, 'The Deflated Sharpe Ratio' (J. Portfolio Management 40(5), 2014 — só o resumo); Cameron, Gelbach & Miller, 'Bootstrap-Based Improvements for Inference with Clustered Errors' (Review of Economics and Statistics 90(3), 2008 — só o resumo); Sullivan, Timmermann & White 1999 e Deprez & Frömmel 2024 (já lidos, KB-0167 e KB-0174)"
fonte_url: https://doi.org/10.1111/1468-0262.00152 · https://doi.org/10.1198/073500105000000063 · https://doi.org/10.1093/rfs/hhv059 · https://doi.org/10.3905/jpm.2014.40.5.094 · https://doi.org/10.1162/rest.90.3.414
lido_em: 2026-10-01
evidencia: "estudos revisados, todos só pelo resumo (White; Hansen; Harvey et al.; Bailey & López de Prado; Cameron et al.), mais dois já lidos na base; nenhuma medição nossa"
hipotese_testavel: não
astra: "discorda em parte — revisada junto da síntese KB-0179; as correções que atingem esta nota foram aceitas (ver KB-0179 §Segunda opinião)"
status: vivo
owner: sexta-feira
updated: 2026-10-01
confiança: estudo revisado
tipo: leitura
hipotese: H-027
variavel: razao_mm20d (contexto; nenhuma medição aqui)
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: "nenhum; alimenta a leitura do resultado da H-027 em KB-0179"
classe_de_perda: —
mercado: cripto
---

# KB-0178 — Data snooping e poucos clusters: o que vale para a H-027

> **Leitura curada, sem medição nossa.** As ferramentas de data snooping (Reality Check, SPA, Sharpe deflacionado)
> respondem a "a **melhor** de muitas regras bate o benchmark?". A H-027 não escolhe a melhor: pré-registra uma
> janela, uma variável e duas estratégias com Holm. O risco que sobra é de outra natureza: (a) a **escolha
> coletiva** da janela de 20 dias pela literatura e pela base (a regra famosa é sobrevivente) e (b) **inferência
> com poucos clusters** (~23 dias e, pela emenda da H-027, 16 mercados), a faixa (5–30) em que, pelo resumo de
> Cameron, Gelbach & Miller, testes usuais por cluster podem rejeitar demais.

## O que afirma (claim × evidência)

1. **White 2000 (resumo).** Reusar o mesmo dado para escolher e testar um modelo faz resultados de sorte parecerem
   mérito; o Reality Check testa a hipótese nula de que o **melhor** modelo de uma busca não tem superioridade
   preditiva sobre um benchmark.
2. **Hansen 2005 (resumo).** O SPA é mais poderoso e menos sensível a alternativas ruins ou irrelevantes que o
   Reality Check: estatística studentizada e distribuição nula dependente da amostra.
3. **Harvey, Liu & Zhu 2016 (resumo).** Com centenas de fatores testados, os critérios usuais de significância não
   fazem sentido; um fator novo deveria passar de t > 3,0; a maioria dos achados publicados em finanças
   provavelmente é falsa.
4. **Bailey & López de Prado 2014 (resumo).** O Sharpe deflacionado corrige dois infladores — seleção sob
   múltiplos testes e retornos não normais — e pede o **número de tentativas** de quem chegou ao resultado.
5. **Cameron, Gelbach & Miller 2008 (resumo).** Erros-padrão robustos por cluster supõem muitos clusters; com
   poucos (cinco a trinta) os testes usuais rejeitam demais; o bootstrap-t por cluster (com refinamento
   assintótico) traz rejeições de 10 % de volta aos 5 % nominais nas simulações deles.
6. **Já lidos:** Sullivan, Timmermann & White (a melhor regra de 100 anos de Dow Jones passa no Reality Check e
   morre depois de 1986; [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]]); Deprez & Frömmel (seleção por
   taxa de descobertas falsas, só ~2–3 % das regras superam o benchmark dentro da amostra;
   [[KB-0174-o-filtro-de-tendencia-corta-queda-nao-acrescenta-alta]]).

## O que se aplica à H-027 (e o que não)

| ferramenta | se aplica? | por quê |
|---|---|---|
| Reality Check / SPA | **não diretamente** | não há busca entre regras dentro da H-027; seriam a ferramenta se alguém, depois de ver, comparasse janelas de 10/20/50 dias |
| Holm sobre {momentum, volume_anomaly} | **sim** (já no registro) | é a família declarada |
| t > 3 / número de tentativas | **sim, como contexto** (não é limiar alternativo da H-027) | 20 dias foi escolhido depois de 15 min (H-005), 4 h (H-008), 24 h (H-023), 14 d semanal (H-024) e LTA diária (H-026) — ver [[Registro de Tentativas]]; um p de Holm perto de 0,05 é evidência fraca neste programa |
| Sharpe deflacionado | **não** | a H-027 não seleciona estratégia por Sharpe |
| poucos clusters (CGM) | **sim, como cautela** | o IC da H-027 é percentil de bootstrap de pares por cluster de **dia** (~23) e, pela emenda de 01/10, também de **mercado** (16), com o maior p e os dois ICs exigidos. O resumo de Cameron et al. mostra que testes assintóticos usuais podem rejeitar demais com 5–30 clusters e que o bootstrap-t por cluster melhora isso nas simulações deles — **não** demonstra que o IC percentil de pares deste desenho fica estreito; um limite inferior pouco acima de zero pede sensibilidade, não descarte |

## Como mediríamos aqui

Sem mudar o pré-registro (que esta nota não edita): como **sensibilidade descritiva**, o IC por bootstrap
selvagem por cluster (wild cluster bootstrap-t, pesos de Rademacher ou Webb), especificando nula imposta,
studentização, pesos e como o IC é obtido, na mesma escala do coeficiente; por dia e por mercado
**separadamente** (não equivale a inferência em duas vias). Dependência entre clusters e informação concentrada
em poucos clusters prejudicam também o selvagem. Se o CONFIRMA depender do bootstrap de pares e sumir no
selvagem, ler como frágil. (A Astra conferiu esses cuidados no guia aberto de Cameron & Miller, J. Human
Resources 2015, §§V–VI; eu não o li.)

## Por que pode falhar (esta leitura)

- Todas as fontes desta nota foram lidas só pelo resumo; a recomendação do bootstrap selvagem é do conhecimento
  geral da área, não um número que conferi em Cameron et al. (o resumo fala em bootstrap-t por cluster).
- O efeito de desenho (correlação entre mercados no mesmo dia) pode ser maior que o suposto no registro (~2).

## Segunda opinião (Astra)

Revisada junto da síntese — ver [[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]] §Segunda opinião.

## Relacionados

[[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]] · [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]] · [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] ·
[[KB-0177-decaimento-e-regime-o-que-a-literatura-de-cripto-mostra]] · [[Registro de Tentativas]] · [[Fila de Hipoteses]]
