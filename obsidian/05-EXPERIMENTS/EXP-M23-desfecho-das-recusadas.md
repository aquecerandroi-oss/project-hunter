---
tags: [experimento, meme, portao, recusa, contrafactual, medicao, m4, r69]
status: pre-registrado (nada implementado; nada real)
owner: sexta-feira
updated: 2026-09-23
origem: R69 (23/09/2026) — nenhuma das 13 variáveis de decisão separa, nem em absoluto (R65/R66/R67) nem em percentil dentro da coorte (R69). O que falta não é mais um limiar: é o outro lado da tabela 2×2.
previsao: se o portão seleciona, o desfecho médio das RECUSADAS é pior que o das ADMITIDAS por uma margem que paga o custo; se o portão apenas aposta menos vezes, os dois desfechos são indistinguíveis os dois desfechos são indistinguíveis — e só então, por teste de não-inferioridade com margem e limite de cauda, um critério pode ser candidato a remoção
tipo: pesquisa
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: —
mercado: meme
---

# EXP-M23 — Qual é o desfecho das moedas que RECUSAMOS?

## O quadrado vazio

Todos os estudos da mesa (R58…R69) medem só a coluna "entrámos":

| | deu certo | deu errado |
|---|---|---|
| **entrámos** | 23 alvos (R65) | 64 perdas (R65) |
| **recusámos** | **vazio** | **vazio** |

Há **41 905 recusas** gravadas em `meme_gate_refusals_by_mint` (desde 17/09/2026, **3 593 mints** distintos): `snipers_above_max` 15 290, `progress_above_max` 7 933, `e2b_top_buyer_unknown` 3 408, `holders_below_min` 3 171, `symbol_clone` 2 048, `creator_is_net_seller` 1 043, `sells_ratio_above_max` 1 031, `creator_serial` 964, `snipers_below_min` 950, `top10_unknown` 838, `creator_repeat_dumper` 598. **Nenhuma tem desfecho medido.**

> **Enquanto o quadrado inferior estiver vazio, não é possível distinguir um portão que SELECIONA de um portão que apenas aposta MENOS VEZES.** Um portão que recusa ao acaso tem exatamente a mesma aparência nos nossos dados atuais.

Isto é **medição, não ajuste de botão**. Não propõe mudar nenhum parâmetro da mesa.

## Hipótese

**H0 (a hipótese nula que temos de conseguir rejeitar):** o retorno líquido por SOL de uma aposta de papel numa moeda **recusada** é indistinguível do de uma moeda **admitida**, no mesmo instante e sob a mesma política de saída.

**H1:** as recusadas têm retorno médio pior por uma margem ≥ **0,045 por SOL** (o custo de ida-e-volta com o aluguel da ATA recuperado, 2,23 %, mais margem) — isto é, o portão acrescenta valor mensurável.

E, por critério de recusa: **quais dos 11 critérios** separam.

**Atenção à armadilha que a Astra apanhou no primeiro rascunho deste pré-registo:** *ausência de significância não é equivalência*. Um p alto **não autoriza remover** um critério — sobretudo um que proteja contra perdas raras que a amostra não chega a observar. Para propor a retirada de um critério é preciso um **teste de não-inferioridade** declarado antes:
- margem de não-inferioridade **δ = 0,02 por SOL** (retorno das recusadas por esse critério não pode ser pior que o das admitidas por mais de δ, com IC 95 % unilateral inteiramente acima de −δ);
- **e** limite de cauda: a fração de apostas com `ret ≤ −0,5` no grupo recusado não pode exceder a do grupo admitido em mais de **5 pp**;
- **e** a análise foca em quem **passaria todo o resto do portão** e só tropeou nesse critério (por isso gravam-se **todos** os motivos de recusa, não só o primeiro).

## Desenho congelado (mudar qualquer item é versão nova)

- **Braço:** `refused_probe_v0/1`, modo `research_only`. **Não gera proposta executável, não toca no risco, não toca em dinheiro real.** Só aposta de papel.
- **População:** toda moeda que, num tique, recebe **pelo menos uma recusa** do portão da mesa e **não** é admitida por nenhum braço nesse mesmo tique.
- **Amostragem:** aleatória, **semente congelada**, **probabilidade de inclusão conhecida e gravada em cada aposta** (10 % base; motivos raros sobreamostrados até 50 %, com **ponderação pelo inverso da probabilidade** na análise). Um mint entra **uma vez** (a primeira oportunidade elegível, escolhida **antes** de conhecer o desfecho). Alvo: ~50–80 mints/dia.
- **Todos os motivos de recusa são gravados**, não só o primeiro — sem isso não dá para isolar "só tropeou neste critério". Motivos com < 30 mints/semana ficam declarados **não testáveis**, não substituídos.
- **Simetria obrigatória:** mesmo simulador, mesmos custos, mesma latência e mesmo acompanhamento para admitidas e recusadas. **Censura e impossibilidade de execução são resultados explícitos**, não exclusões silenciosas.
- **Parâmetros de saída:** **os da mesa real** — 0,07 SOL nominal, alvo 1,15×, `max_hold` 300 s, trailing 10 % armado na entrada, saída por evento ligada. (É a ressalva nº 1 do R67: o `flow_v2` testa sob a saída errada.)
- **Braço de controlo, em paralelo e no mesmo período:** as apostas **admitidas** com os mesmos parâmetros. Sem controlo contemporâneo o teste não vale — o regime de mercado move os dois lados.
- **Desfecho primário:** `ret = pnl_sol / size_sol`.
- **Desfecho secundário (descritivo):** fração que toca 1,15× dentro dos 300 s.
- **Inferência:** uma aposta por mint; **bootstrap em blocos de 60 min** (10 000); permutação estratificada por dia; **Benjamini-Hochberg a 10 % sobre a família congelada** = 1 contraste global + 11 contrastes por motivo de recusa = **12 hipóteses**. Benjamini-Yekutieli como referência conservadora.
- **Guarda anti-antecipação:** as features gravadas na aposta são as do instante da recusa (`as_of ≤ t`, `computed_at ≤ t`, `tape_as_of ≤ as_of`), com o mesmo teste de invariância ao futuro do R69 (`.claude/state/r69/test_cohort.py`).
- **Parada:** 14 dias corridos de mesa ativa **ou** 700 mints recusados medidos, o que vier primeiro. Sem olhar o resultado antes.

## Previsão registada antes de correr

Escrevo o que espero, para poder estar errado por escrito:
**espero H0** — que as recusadas tenham retorno indistinguível das admitidas. Motivo: as 13 variáveis que compõem o portão já foram testadas em absoluto (R65: p mínimo 0,046 contra limiar BH 0,0077; R66: p mínimo 0,073) e em percentil de coorte (R69: p mínimo 0,014 contra limiar 0,0059, e o único IC que excluía zero era um pico que troca de sinal fora de amostra), e nenhuma separou. Um portão feito de critérios que não separam provavelmente também não separa.

**Se eu estiver certo**, o valor do experimento não é um filtro novo: é abrir caminho para **remover critérios que passem o teste de não-inferioridade**, o que aumenta o número de apostas por dia sem piorar o retorno esperado — e mais apostas por dia é o que a meta diária (KB-0149 §0) precisa, porque hoje a variância diária vem de 7–15 operações. **Se nenhum critério passar o teste de não-inferioridade, o resultado é "não sabemos" — e isso também é um resultado.**

## Regras de refutação (escritas antes)

1. **Abandonar o experimento** se, ao fim de 7 dias, o braço produzir **< 20 mints medidos/dia** — amostra insuficiente para decidir qualquer coisa.
2. **Abandonar o experimento** se mais de **30 %** das apostas ficarem `indeterminate` (sem fita nem fotos suficientes): estaríamos a medir a cobertura, não o mercado.
3. **Não concluir nada por motivo de recusa com < 150 mints.** Declarar "não testável".
4. **Não promover nenhuma remoção de critério** por um p alto. Só pelo **teste de não-inferioridade** acima, com o limite de cauda, e com BH sobre os 12.
5. **Não interpretar "recusadas iguais às admitidas" como licença para desligar o portão inteiro de uma vez.** Remoção é um critério de cada vez, com 3 dias de sombra e o braço de controlo a correr.

## Cenários de falha deste desenho

- **Seleção pela cobertura:** as moedas recusadas por `*_unknown` (4 246 recusas: `e2b_top_buyer_unknown`, `top10_unknown`) são recusadas exatamente porque temos menos dados sobre elas — e menos dados também significa maior chance de `indeterminate`. O contraste desse motivo mede, em parte, a coleta. Declarado; por isso a regra 2.
- **A amostragem de 10 % pode não ser aleatória de facto** se o tique em que a recusa cai já for correlacionado com a hora. Mitigação: a semente é congelada e a taxa é fixa por dia, não por tique.
- **O braço de controlo não é um ensaio aleatorizado.** As admitidas foram escolhidas pelo portão; as recusadas, por definição, não. A comparação é observacional e o confundimento é exatamente o que o portão mede. Isto **não** é um A/B — é a medição do quadrado vazio, e não autoriza linguagem causal.
- **Custo de infra:** 50–80 apostas de papel/dia a mais no worker, com features já calculadas. Barato, mas não zero; se a pista rápida perder tique por causa disto, **o experimento morre** (a mesa real tem precedência).

## Relacionado

[[KB-0151-a-coorte-nao-respira]] · [[KB-0149-o-que-a-mesa-real-ensinou]] · [[KB-0147-custo-e-o-prejuizo-e-buys-1m-e-a-unica-pista]] · [[EXP-M22-absorcao-de-venda]] · [[Registro de Tentativas]]

## Emenda 1 — 23/09/2026 13:2x BRT, ANTES de qualquer dado (amostragem estratificada)

**O erro que a emenda corrige (achado pelo implementador da T4.85, aritmética verificada):** o desenho congelou três coisas incompatíveis — população "≥ 1 recusa" (larga), taxa "10 % base" e alvo "50–80 mints/dia". O censo de 3 593 mints em 6 dias que justificou os 10 % vem de `meme_gate_refusals_by_mint`, tabela que **só guarda quase-falhas** (`is_trail_candidate` exige `refusal_count ≤ 1`) ≈ 600 mints/dia. A população larga é outra ordem de grandeza: ~379 000 linhas julgadas/dia ≈ **19 000 mints distintos/dia**, e 10 % disso seriam ~1 900 apostas/dia — 25 a 38× o alvo, e a própria pré-registação diz que se a pista rápida perder tique por causa do experimento, **o experimento morre**.

**Decisão (dona do pré-registo, Sexta-feira): amostragem ESTRATIFICADA, nenhuma das três opções puras.** Motivo: as duas populações respondem a perguntas diferentes e o experimento precisa das duas.

| estrato | população | taxa | esperado/dia | responde |
|---|---|---:|---:|---|
| **A — quase-falha** | recusada por **exatamente um** critério, não admitida no tique | **10 %** base, **50 %** nos motivos com < 30 mints/semana (como congelado) | ~60 | "**este critério** separa?" — é onde vive o "passaria em tudo e só tropeçou aqui", e é o único estrato válido para o teste de não-inferioridade por critério |
| **B — recusa múltipla** | recusada por **≥ 2** critérios, não admitida no tique | **0,1 %** base; **0,5 %** se o conjunto de motivos incluir algum com < 30 mints/semana | ~19 | "o portão **como um todo** seleciona ou só aposta menos vezes?" — sem este estrato a resposta global fica cega para as piores moedas, que são justamente as que falham em vários critérios |

**Total esperado ≈ 79/dia**, dentro do alvo congelado de 50–80 e do orçamento de infra.

**O que NÃO muda:** semente congelada; **probabilidade de inclusão gravada em cada aposta** (agora junto com o `estrato`), com ponderação pelo inverso na análise; um mint entra uma vez; todos os motivos gravados; parâmetros de saída da mesa real; braço de controlo contemporâneo; guarda anti-antecipação; família de 12 hipóteses com Benjamini-Hochberg; regra de parada.

**O que muda na análise:** o contraste global usa **A + B ponderados pelo inverso da probabilidade** (estimador não enviesado da população recusada inteira) e é reportado **também por estrato**; os 11 contrastes por critério usam **só o estrato A**. Se B render menos de 30 mints na janela, fica declarado **não testável** — não é substituído nem fundido em A.

**Por que não a opção "população estreita + 10 % literal":** naquela tabela há exatamente um motivo por linha, então o requisito "gravar todos os motivos" ficaria vazio e a pergunta global ("seleciona ou aposta menos?") ficaria sem resposta. **Por que não "larga + taxa baixa uniforme":** diluiria o estrato A, que é o único onde o teste por critério tem sentido, para pagar amostra de um estrato onde a resposta é quase certa.
