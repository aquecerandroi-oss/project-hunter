---
tags: [experimento, meme, concentracao, maior-comprador, creator-dump, saida, gemeo, h-031b, m4]
status: pré-registrado — conjunto de papel `absorb_semdump_v0/1` preparado na migração `0069_meme_absorb_semdump_arm`, ainda não aplicada; nada real
owner: quant-engineer
updated: 2026-10-07
origem: rota (2) do Defensor sobre a H-031 (07/10/2026) — o conjunto gêmeo de papel sem a saída `creator_dump`; aprovado pelo Everton em 07/10/2026 ("Ligar o gêmeo")
previsao: "I = média Δ(alto) − média Δ(baixo) ≥ +0,05 por SOL, com Δ = r(absorb_v0/2) − r(absorb_semdump_v0/1) no mesmo mint e F = largest_net_buyer.share_of_real_sol > 0,35 no braço alto"
exp: EXP-M27
strategy: "meme/pumpfun - gêmeo do absorb_v0/2 sem a saída creator_dump (H-031b)"
version: "absorb_semdump_v0/1 research_only (migração 0069_meme_absorb_semdump_arm)"
result: nao-iniciado
evaluable: 0
days: 0
tipo: pesquisa
hipotese: H-031b
variavel: F = derived.largest_net_buyer.share_of_real_sol da fita da decisão de absorb_v0/2 (alto > 0,35); manipulação = exit_on_creator_dump false no gêmeo
populacao: primeira aposta do mint admitida por absorb_v0/2 e por absorb_semdump_v0/1 na mesma (mint, features_end_time), propostas depois de T0
efeito: —
ic: —
veredito: —
proximo_passo: revisão de banco da 0069 feita (APPROVE, H-031b-db-review); aplicar o patch sequenciado de lab_models antes; deploy do código, depois a 0069 sem a 0070; deploy do Everton = T0
classe_de_perda: golpe_do_criador
mercado: meme
---

# EXP-M27 — O gêmeo sem `creator_dump` (H-031b)

## Hipótese (congelada)

A concentração do maior comprador no instante da decisão prevê perda **quando a saída `creator_dump` deixa de
absorvê-la**: o que a saída rende por aposta (Δ) é maior no braço de fatia alta (F > 0,35) do que no baixo, em pelo
menos +0,05 por SOL. Texto decisório completo, emenda 1 incluída: [[Fila de Hipoteses]] (bloco **H-031b**).

## Por que existe

- A [[Fila de Hipoteses|H-031]] (R88, [[KB-0188-a-concentracao-do-maior-comprador-nao-separa-o-retorno]]) terminou
  NÃO CONFIRMA: a fatia não separa o retorno do papel, mas a saída `creator_dump` foi 2,11× mais frequente no braço
  alto. "A saída esconde a diferença" ficou possível e não demonstrada.
- O [[Defensor]] propôs três rotas em coorte nova; esta é a (2), "a mais útil, porque fecha a rota 'no real seria
  diferente'". O [[Advogado de Jesus]] achou que `exit_on_creator_dump` não estava gravado em nenhuma aposta (0 de
  1 680): o parâmetro só existia no padrão `True` de `ExitRules`, nenhum conjunto podia desligá-lo.
- **Decisão do Everton, 07/10/2026: "Ligar o gêmeo".** Só papel, nenhum dinheiro.

## Braço (congelado — mudar qualquer item é braço novo e EXP nova)

- **Conjunto:** `absorb_semdump_v0/1` (`01994d00-6c1a-7000-8000-000000000022`), `kind = research_only`,
  `exp_ref = EXP-M27`, migração `0069_meme_absorb_semdump_arm` (`docs/DATABASE.md` §72).
- **Documento:** o `params` **vivo** de `absorb_v0/2` ([[EXP-M22-absorcao-de-venda]]) na hora da migração, **mais**
  `"exit_on_creator_dump": false` e nada mais — mesma porta (absorção vista), mesma ficha 0,07 SOL, mesmos tetos
  (3 posições, perda diária 0,20 SOL, carteira 2,0 SOL), mesmas saídas tirando o `creator_dump`: alvo 1,15×, trailing
  10 % armado na entrada, `line_broken`, `max_loss` 50 %, 300 s. `code_ref` igual ao do original. O teste
  `test_migration_0069` prova `gêmeo − exit_on_creator_dump = original`, chave a chave, e que o gêmeo carrega pelo
  caminho do robô com a saída desligada. **No deploy, registrar aqui o `md5(params::text)` dos dois conjuntos, o
  `created_at` do gêmeo (= T0) e o commit da imagem do `meme-worker`.**
- **A migração recusa:** `absorb_v0/2` ausente ou aposentado; fora do relógio `15s`; com a chave presente e diferente
  de `true`; e qualquer outro conteúdo sob o nome congelado depois da cópia. A linha do original fica travada
  (`FOR NO KEY UPDATE`, [[H-031b-db-review]]) durante a migração: um `--set-param` que chega antes faz a migração
  esperar e julgar o documento editado; um que chega depois espera e grava depois, e separa coortes (o `md5` do deploy
  é o que mostra). As inserções do worker que referenciam `absorb_v0/2` não esperam pela trava.
- **Papel por construção:** `research_only` — o executor só seleciona `kind = 'operator'` (o teste da `0069` roda a
  consulta do executor contra uma proposta do gêmeo e ela não volta).
- **Toda aposta grava a chave.** Desde esta mudança, `meme_paper_bets.params` traz `exit_on_creator_dump` (`true` ou
  `false`) em toda aposta nova; aposta anterior sem a chave correu com `true` (nenhum caminho podia mudá-lo). A chave é
  palavra do conjunto: a decisão do operador não a muda. Uma string (`"false"`) é recusada, nunca lida como `True`.
- **Mesa:** as apostas do gêmeo são subtraídas por id do `creator_prior_dump_count` da mesa (`lab_repo_pedigree`); o
  gêmeo fixa mints no rastreador como qualquer conjunto (sem fotos, a cauda depois do `creator_dump` do original
  sumiria). Interferência residual declarada na emenda 1, item (8) da H-031b.

## Como o par nasce

- Os dois conjuntos são `15s` e julgados na mesma avaliação da pista de eventos: cada proposta de `absorb_v0/2` tem
  ao lado uma proposta do gêmeo com o mesmo `(mint, features_end_time)`.
- Os dois lados entram na mesma foto e só divergem quando o original sai por `creator_dump` — pela foto
  (`creator_net_seller`) ou pela vigia da cadeia (`creator_sold_seen_at`, `lab_bets`). O gêmeo então segue até a
  próxima saída que dispararia.
- **Onde o par falta (contado, nunca preenchido):** tetos de cada carteira (o gêmeo segura mais quando há
  `creator_dump`), perda diária, preenchimento recusado. Por isso a conclusão vale para "a primeira aposta do mint
  admitida pelas duas políticas" (emenda 1, item 1).

## Pré-requisitos antes do deploy (ordem)

1. **Dois deploys, nesta ordem.** Primeiro o código que lê e grava a chave (`lab_params` + o patch sequenciado de
   `lab_models.py`: `RuleSetSpec.exit_on_creator_dump` + uma linha em `effective_params`), já rodando no `meme-worker`;
   **depois**, noutro deploy, a `0069`. O `compose.sh` aplica a migração antes de trocar os serviços: no mesmo deploy,
   o worker antigo poderia abrir apostas do gêmeo com a saída ligada (e a retomada lê o `params` gravado). O teste da
   migração falha se o código não ler a chave, mas não protege essa janela; por isso a emenda 2 da H-031b exclui da
   coorte toda aposta do gêmeo sem `"exit_on_creator_dump": false` no `params`.
2. A `0069` é linearizada com a `0069_meme_mature_chart_arms` (não commitada, do EXP-M26) — hoje as duas descem da
   `0068`. **Feito em 07/10** ([[H-031b-db-review]]): a gêmea fica `0069`; a semente do EXP-M26 virou
   `0070_meme_mature_chart_arms`, sobre ela, e **não entra no commit implantável da gêmea** (o `compose.sh` roda
   `upgrade head`; com o arquivo na árvore os três braços entrariam junto, antes do J congelar). O commit da gêmea leva
   `test_migrations.py` com `HEAD = 0069` e 27 conjuntos ativos.
3. Revisão do `database-architect` sobre a migração; deploy do Everton. **T0 = ativação** (o `created_at` da linha).
   **Revisão feita em 07/10: APPROVE** depois de três ajustes ([[H-031b-db-review]]). Falta o deploy.

## Segunda opinião (Astra)

- Pré-registro: [[H-031b-prereg]] — 6 must-fix, absorvidos na emenda 1 antes de existir o conjunto.
- Diff: [[H-031b-diff]].

## Avaliações

(nenhuma — a coorte começa em T0)

## Relacionados

[[Fila de Hipoteses]] (H-031, H-031b) · [[KB-0188-a-concentracao-do-maior-comprador-nao-separa-o-retorno]] ·
[[EXP-M22-absorcao-de-venda]] · [[EXP-M25-controle-do-recuo]] (precedente de cópia do `params` vivo) ·
[[KB-0149-o-que-a-mesa-real-ensinou]] (§6 item 4: não mexer no `creator_dump` da mesa) · [[Mapa de Estrategias]] ·
[[Experiments Index]] · [[golpe_do_criador]]

### Ativação (09/10/2026), registrada pela Sexta-feira

- **T0 = `2026-10-09 04:08:44.404694+00`**: o `created_at` da linha `absorb_semdump_v0/1` (id `01994d00-6c1a-7000-8000-000000000022`), criada pela migração `0069` no deploy do commit `a7cd4443`.
- `md5(params::text)`: original `absorb_v0/2` `8eca29255620f9f402e9582f7462ea61`; gêmeo `fe2de93889547ab3f1e87f0d12c9b81c` (`exit_on_creator_dump` = `false`).
- O código da etapa 1 já rodava desde o deploy de 08/10, então o gêmeo nunca abre aposta com a saída ligada.
- Apostas do gêmeo no momento da conferência: 0. O executor voltou a `program_mode=normal`, com o escopo esgotado (`small_test_below_min=full`) e a `launch_lane` off. Nada muda na mesa.
