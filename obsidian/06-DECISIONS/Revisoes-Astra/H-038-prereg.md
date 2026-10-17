---
tags: [revisao-astra, b3, win, mercado-tradicional, pre-registro, h-038, modulo-puro]
date: 2026-10-17
updated: 2026-10-17
status: registro
owner: quant-engineer
decided_on: 2026-10-17
by: astra
tarefa: "W0-1 (congelar H-038/H-038r na Fila) e W0-S/W0-F (módulo puro da regra e cartão do dia) do plano docs/plans/MERCADO-TRADICIONAL.md"
veredito: "pré-registro — rodada 1: 3 must-fix (consulta final, denominadores de cobertura, exceção retrospectiva), todos aceitos; rodada 2: os 3 fechados, 1 must-fix novo (F ausente escapava do portão retrospectivo), aplicado como ela escreveu; congelado às 17:56:30Z. Código — rodada 1: 5 must-fix (recebimento de F, formato numérico, fuso do --agora, impedimento/sem reentrada, contexto Decimal do stop), todos corrigidos com teste; rodada 2: fechados, nenhum novo"
---

# Revisão da Astra — pré-registro da H-038 e o módulo da regra

**Pedido:** revisar o rascunho do plano §1.3 antes de congelá-lo na [[Fila de Hipoteses]] como
[[Fila de Hipoteses#H-038 — Momento intradiário de mercado no WIN, coorte prospectiva (o sinal da 1.ª meia hora do Ibovespa prevê o WIN entre C−30 e C?)|H-038]]
(prospectiva) e H-038r (retrospectiva), e depois o código do módulo puro e do cartão do dia. Origem:
[[KB-0176-momento-intradiario-condicionado-o-vizinho-mais-perto]], decisão
[[2026-10-17-pausar-memes-e-cripto-ir-para-mercado-tradicional]] e [[Dialogos/mercado-tradicional|diálogo mercado-tradicional]].
Fontes brutas: `.claude/state/astra-review-H-038-prereg.md`, `-r2.md` e
`.claude/state/astra-review-b3-intraday-momentum-module.md` e `-r2.md`; cópia congelada e manifesto em `.claude/state/h038/`.

**Congelamento:** 2026-10-17 17:56:30Z, antes do primeiro pregão (19/10) e antes de qualquer exportação do MT5.
`prereg_frozen.md` sha256 `ded4e5153d054a1814e97213f7fcd21b88b3d24859ccaf56ba78779cbada1a6c` (no `manifest.txt`). O
bloco anexado à Fila é byte a byte essa cópia.

## Pré-registro, rodada 1 — 3 must-fix, todos aceitos

1. **Consulta final não fixada.** "Rótulo só com ≥ 750" era um piso, não um horizonte: aos 750 sai NÃO CONFIRMA, aos
   780 melhora e se rotula. → **duas consultas e só duas**, pela contagem de calendário N_cal (pregões da B3 desde
   19/10/2026 sem encurtados nem vencimento do WIN — não depende de dado nem de retorno): futilidade em N_cal = 125 e
   final em N_cal = **825** (≈ 785 ÷ 0,95, para o poder de ~785 operações caber com até 5 % de perdas de cobertura),
   cada uma 30 dias depois do pregão que fecha a contagem; sem prolongamento.
2. **Denominador de cobertura.** Com F/I exigidos na população, faltar leitura em 20 % dos dias sumia da conta e o
   teste mostrava cobertura perfeita. → funil publicado sobre N_cal, e "sem sinal" (F ou I ausente, inválido ou
   depois de O+90) > 5 % de N_cal → LIMITE. Os "125 elegíveis" do plano ficaram declarados como contagem de calendário.
3. **Exceção retrospectiva.** Herdar "recebido até O+90" na H-038r obrigaria a inventar disponibilidade histórica.
   → a H-038r reconstrói o sinal pelo tempo do evento, **não** fabrica `received_at`, não aplica O+90, ressalva
   publicada.

Ela **concordou** com as escolhas que o plano não fixava: stop calculado sobre a entrada já deslizada; r1 = 0 fora da
média; série (ii) prospectiva só com fonte negócio a negócio provada (aceitando LIMITE); tarifas atuais no histórico
como cenário declarado; holdout não reverte REFUTA. Corrigiu-me num ponto: pregão encurtado e vencimento excluídos já
estavam no plano §1.2, não eram decisão minha. **Poder:** os números (EP 0,89 bp; P(limite superior < 1,5 | 0) ≈ 39 %;
P(média ≥ 1,5 | 2,5) ≈ 87 %; ~1 285 com σ = 32 bp) conferem **como análise fixa simplificada**; o poder do procedimento
completo não foi calculado — escrito assim no bloco.

## Pré-registro, rodada 2 — fechados; 1 must-fix novo, aplicado

**F ausente escapava do portão retrospectivo:** o funil tirava os dias sem F, mas o portão de 5 % olhava só a barra de
O+30; com F faltando em 400 de 2 000 dias o teste podia confirmar. → portão sobre a união "sem barra em O+30 **ou** sem
F", cada pregão uma vez, e o mesmo "sem sinal" no funil e no portão. Nice-to-have aceito: futilidade com **zero**
desfechos → encerrada sem rótulo, motivo "instrumento". Não houve rodada 3: a correção foi aplicada como ela a
escreveu.

## Decisões de implementação (sem revisão própria; listadas para a revisão do código)

- **Contrato próprio** (`hunter_indicators/b3/contract.py`): o `Decision` do Lab é só LONG e exige alvo.
- **O stop não está no sinal das 10:30**, porque depende do preço da entrada (16:30): o `Signal` leva a fração e
  `stop_price(entrada)` devolve o nível arredondado ao tick por lado.
- **Pregão encurtado, vencimento do WIN e impedimento** são exclusões da sessão (dado do calendário), decididas antes
  de qualquer leitura.
- **Registro durável do cartão:** não há tabela B3 no Postgres (W0-4 espera a aprovação do desenho W0-2) e
  `infra/research` não tem banco local; o cartão imprime **uma linha `H038|…|sha256=…`** para o Everton colar para a
  Sexta-feira, que a grava no diário. Nenhum arquivo local.
- **BRT fixo em UTC−3** (sem horário de verão desde 2019), sem depender de `tzdata` no pacote.
- **Lições do caminho:** `-Decimal(x)` arredonda ao contexto ambiente (28 dígitos) — r1 agora sai já em 28 dígitos
  num contexto explícito, e `r1(a, b) == −r1(b, a)` vale exatamente; num pipe do Windows o stdout é cp1252 e o "−"
  (U+2212) derrubava o cartão — o script troca o stdout para UTF-8 (teste próprio).

## Código — revisão da Astra

**Rodada 1 — "não aprovaria o cartão ainda": 5 must-fix, todos aceitos e corrigidos com teste que falhou antes.**

1. **Recebimento de F inventado.** O cartão perguntava só a hora da leitura das 10:30 e a usava também para o
   fechamento anterior: F obtido às 11:40 com `--lido-as 10:42` dava COMPRA. → `--fechamento-lido-as` obrigatório;
   F vencido depois de O+90 vira SEM OPERAÇÃO (`received_after_deadline`).
2. **Formato numérico podia inverter a direção.** `131,300.00` virava 131,3 e `+131.300` escapava da recusa. → só
   quatro formas aceitas por expressão inteira (`130456`, `130456.78`, `130456,78`, `130.456,78`), `130.456`
   recusado como ambíguo; mais duas **guardas de digitação do CLI** (não da regra): |I ÷ F − 1| > 20 % (o último
   nível do circuit breaker da B3) e |WIN ÷ I − 1| > 10 % → erro "confira".
3. **`--agora` descartava o fuso** (`13:00Z` virava 13:00 BRT). → fuso explícito respeitado, sem fuso = BRT, nas
   três horas.
4. **Impedimento e "sem reentrada" ausentes do cartão.** → `--impedimento` exclui o pregão (registrado na linha);
   o cartão diz "Stop tocado: acabou o dia — sem reentrada" e o que fazer com leilão/interrupção na janela; rodapé
   "Vale a primeira linha do dia".
5. **O stop dependia da precisão `Decimal` do chamador** (compra a 207 005: 205 965 com 28 dígitos, 205 970 com 6).
   → `stop_level` num `Context(prec=34)` próprio e r1 em contextos explícitos; testes com precisão 6 e 5.

Nice-to-have aceito: o docstring de `IndexReading` diz que passar só barra **final** é dever do chamador (o módulo
só confere o instante). Ela também conferiu os cinco feriados no calendário da B3 e o 16/12 pela regra do WIN; não
reconfirmou o PDF do ofício (eu li o Anexo 2: à vista 10:00–17:55, call até 18:00 a partir de 03/11).

**Rodada 2:** os cinco fechados por inspeção, **nenhum must-fix novo**. Ela não rodou testes nesta rodada; a
suíte verde é a que eu rodei (100 testes novos, ver o relatório da tarefa).

## Relacionado

[[Fila de Hipoteses]] · [[KB-0176-momento-intradiario-condicionado-o-vizinho-mais-perto]] ·
[[KB-0194-day-trade-no-mini-indice-quase-ninguem-vive-disso]] · [[KB-0149-o-que-a-mesa-real-ensinou]] ·
[[Dialogos/mercado-tradicional|diálogo mercado-tradicional]] · [[2026-10-17-pausar-memes-e-cripto-ir-para-mercado-tradicional]]
