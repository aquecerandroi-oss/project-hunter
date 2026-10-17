---
tags: [knowledge, b3, mini-indice, win, day-trade, pessoa-fisica, contexto, mercado-tradicional]
tema: "quem faz day trade no mini-índice da B3 por conta própria quase sempre perde: entre todas as pessoas físicas que começaram em 2013–2015 e persistiram ≥ 300 dias, 97 % perderam dinheiro e 0,4 % ganharam mais que um caixa de banco; sem evidência de aprendizado"
fonte: "Chague, De-Losso & Giovannetti, 'Day trading for a living?' — FGV EESP, Textos para Discussão 525 (versão de 2020, resumo lido na RePEc); versão de 2019 no SSRN (abstract_id 3423101) e no working paper FEA/USP 2019wpecon47 (só o trecho do resumo exibido na busca; o SSRN devolve 403 a acesso automatizado)"
fonte_url: "https://ideas.repec.org/p/fgv/eesptd/525.html"
lido_em: 2026-10-17
evidencia: "estudo com o universo inteiro de pessoas físicas de um mercado (dado administrativo da B3), lido só pelo resumo; o texto completo não foi aberto nesta leitura"
hipotese_testavel: não
astra: pendente
status: vivo
owner: quant-engineer
updated: 2026-10-17
confiança: "?"
tipo: leitura
hipotese: —
variavel: —
populacao: "todas as pessoas físicas que começaram a fazer day trade em minicontratos de Ibovespa (WIN) na B3 entre 2013 e 2015 e persistiram ≥ 300 dias"
efeito: "97 % perderam dinheiro; 0,4 % ganharam mais que US$ 54/dia; o melhor indivíduo ganhou US$ 310/dia com desvio-padrão de US$ 2 560"
ic: —
veredito: —
proximo_passo: "contexto obrigatório no painel de sinais do WIN e no plano MERCADO-TRADICIONAL; nenhuma hipótese sai daqui"
classe_de_perda: —
mercado: b3
---

# KB-0194 — Day trade no mini-índice: quase ninguém vive disso

> **Contexto, não hipótese.** Registrado no dia em que o Everton decidiu operar o WIN com dinheiro real, à mão,
> a partir de 19/10/2026 ([[2026-10-17-pausar-memes-e-cripto-ir-para-mercado-tradicional]]). Esta nota existe para
> que o painel e o plano mostrem a taxa-base antes de qualquer placar nosso.

## O que afirma

Chague, De-Losso e Giovannetti (FGV EESP, TD 525, resumo da versão de 2020) observaram **todas** as pessoas físicas
que começaram a fazer day trade no mercado futuro de índice da B3 entre 2013 e 2015 e que **persistiram por pelo
menos 300 dias**:

1. **97 % perderam dinheiro.**
2. **Só 0,4 %** ganharam mais que um caixa de banco (US$ 54 por dia).
3. O **melhor** indivíduo ganhou US$ 310 por dia, com risco enorme (desvio-padrão de US$ 2 560).
4. **Não há evidência de aprendizado**: persistir não melhorou o resultado.

O resumo atribui o resultado, entre outras coisas, à competição com operadores de alta frequência (HFT). O texto do
resumo da versão de 2019 (SSRN) traz os mesmos 97 % e um segundo número (1,1 % acima de um piso de renda) que a busca
cortou; **não cito esse número** porque não li a frase inteira.

## Por que importa para nós

- É a **taxa-base** de quem faz o que o Everton vai fazer: day trade no WIN como pessoa física. O nosso prior para
  qualquer regra intradiária no WIN começa daqui, junto com o que memes e cripto ensinaram
  ([[KB-0149-o-que-a-mesa-real-ensinou]]: 0 `CONFIRMA` em todas as hipóteses de cripto e memes testadas até 17/10).
- Reforça a regra da casa: **resultado de uma semana não diz nada**; o que separa os 3 % dos 97 % não é visível em
  dias.
- Não diz que **uma regra sistemática** pré-registrada perde — o estudo mede pessoas, não regras; mas também não dá
  nenhum motivo para esperar o contrário.

## Por que pode falhar (limites desta leitura)

- Só o resumo foi lido; metodologia de custos, impostos e como o "perdeu dinheiro" foi medido ficam por conferir no
  texto completo.
- Amostra de 2013–2015; o custo de operar caiu desde então (corretagem zero com RLP; ver
  `docs/plans/MERCADO-TRADICIONAL.md`), e o estudo é anterior à grade e às tarifas atuais.
- Seleção: "persistiu ≥ 300 dias" — quem desistiu cedo não entra nessa porcentagem.

## Relacionados

[[2026-10-17-pausar-memes-e-cripto-ir-para-mercado-tradicional]] · [[KB-0149-o-que-a-mesa-real-ensinou]] ·
[[KB-0176-momento-intradiario-condicionado-o-vizinho-mais-perto]] · [[KB-0177-decaimento-e-regime-o-que-a-literatura-de-cripto-mostra]] ·
[[Dialogos/mercado-tradicional|diálogo mercado-tradicional]]
