---
tags: [knowledge, meme, mesa-real, identidade, social, twitter, criador, golpe, hipotese, metodo, m4]
tema: moedas que reciclam o mesmo link de X/Twitter de outras moedas das 24 h anteriores rendem menos no ponto, mas o contraste não é identificável, não têm mais golpe do criador, e o efeito some quando se usa só o que a base sabia na decisão; a coleta do link parou em 25/09
fonte: R80 (`.claude/state/notes-R80.md`) — H-020 da Fila de Hipóteses
fonte_url:
lido_em: 2026-09-26
evidencia: medição própria — 612 decisões legíveis da porta fluxo_e_holders (12–26/09/2026, uma por mint, 66 reais e 546 de papel), 442 727 moedas no universo de busca (124 374 com link), bootstrap por mint 10 000, permutação por dia, Holm, moinho `run_hypothesis`, contrafactual contábil em 161 posições reais; 28 testes sintéticos
hipotese_testavel: sim
astra: concorda
status: vivo
owner: sexta-feira
updated: 2026-09-26
confiança: "?"
tipo: pesquisa
hipotese: H-020
variavel: reuso_social (outras moedas das 24 h anteriores à decisão com o mesmo link de X/Twitter, normalizado; só created_at < decisão)
populacao: 612 decisões legíveis de 871 resolvidas da porta fluxo_e_holders (12-26/09, 66 reais + 546 papel), 173 com reuso >= 1
efeito: D (reuso>=1 - reuso 0) = -0,0525 por SOL
ic: [-0,1229, +0,0161]
veredito: nao_confirma
proximo_passo: reparar a coleta do link (parada desde 25/09 17:13Z) e capturá-lo na criação com instante próprio; só então coorte nova, pré-registrada, com as 24 h anteriores cobertas no instante da decisão
classe_de_perda: golpe_do_criador
mercado: meme
---

# KB-0160 — O link de X/Twitter reciclado não avisa o golpe

> **H-020 (identidade social reciclada): `NÃO CONFIRMA`.** O rótulo segue o protocolo com a errata do R76,
> adotada antes de olhar desfechos. A cláusula (a) original, lida ao pé da letra, daria REFUTA. Mas o intervalo
> contém tanto o zero como o efeito previsto (−0,05), por isso não exclui nada.
> Estudo em `.claude/state/notes-R80.md` · código e saídas em `.claude/state/r80/` · pré-registo em
> [[Fila de Hipoteses]] § H-020.

## O que afirma

1. **No ponto, a tese acerta a direção e o tamanho, mas o contraste não é identificável.** Contam-se as moedas
   cujo link de X/Twitter já aparecia noutras moedas criadas nas 24 h anteriores.
   - Essas rendem −5,6 % por SOL; as restantes rendem −0,3 %.
   - A diferença é D −0,0525, com IC [−0,123, +0,016] e p 0,18. Com Holm fica p 0,37.
2. **O mecanismo previsto não aparece.** A tese dizia que reciclar o "cartão de visita" era coisa de lançador em
   série e que, por isso, estas moedas teriam pelo menos o dobro de `golpe_do_criador`. A taxa é igual nos dois
   grupos: 32,9 % contra 32,3 %. Com dois ou mais reusos é até menor: 26 % contra 33 %.
3. **O efeito depende de *quando* a identidade foi lida.** Contando só o que a base já sabia no instante da
   decisão, a diferença desaparece: +0,009 [−0,077, +0,094]. Um filtro que a mesa conseguisse executar hoje não
   teria o que filtrar.
4. **A coleta do link está parada.** A leitura REST da pump.fun é a única fonte do link e está parada desde
   **25/09 17:13:16Z**. Desde essa hora nenhuma moeda nova tem identidade.

## Onde foi mostrado

**Dado.** O link está em `meme_tokens.twitter`, que só a leitura REST `/coins/{mint}` grava (T4.26).
- As colunas são de escrita única. Quando `social_observed_at` está NULL, a moeda **não foi observada**. Isso é
  diferente de uma moeda observada sem link.
- A coluna `twitter_reuse_count` é a contagem do indexador. Não serve para esta variável: muda com o tempo, conta
  numa janela que não é a nossa e é lida depois da decisão.
- `meme_risk_snapshots.raw` guarda apenas `hasTwitter`, sem o URL.
- O link é, na prática, metadado da criação:
  - o indexador muda `hasTwitter` em 6 das 10 588 moedas;
  - o REST e o indexador discordam em 15 de 6 802.

**Normalização do link:**
- perfil → handle em minúsculas;
- post → id do status, qualquer que seja o handle da URL;
- comunidade → id;
- outros → texto com a query preservada.

**Cobertura.** A fração de moedas criadas com identidade observada varia muito por dia:

| dia | cobertura |
|---|---|
| 17/09 | 95 % |
| 18–22/09 | 83–93 % |
| 23/09 | 70 % |
| 24/09 | 67 % |
| 25/09 | 46 % |
| 26/09 | 0 % |

**População.** 1.ª decisão por mint da porta `fluxo_e_holders/*`: pista de eventos e de 15 s, reais e papel, de
12/09 a 26/09.
- 871 decisões resolvidas.
- **612 legíveis (70,3 %).** Legível quer dizer que a própria moeda foi observada **e** que ≥ 60 % das moedas das
  24 h anteriores também foram.
- **173 com reuso ≥ 1.**
- Nenhuma das duas cláusulas de dado dispara.

**O que o reuso mistura.** As chaves mais repetidas no universo são de três tipos:
- lançadores em série (`jessicalucluvh` 443 moedas, `buttbrainer` 413);
- um serviço de repasse de taxa (`usepaid` 383);
- posts virais e `elonmusk` (208).

A variável pré-registrada é literal e não separa os três.

| peça | resultado |
|---|---|
| **D (reuso ≥ 1 − reuso 0)** | **−0,0525 [−0,1229, +0,0161]**, p 0,183, Holm 0,366 |
| `sem_social` (sem link − com link) | +0,055 [−0,029, +0,150], p 0,184, Holm 0,366 |
| vencedoras com reuso ≥ 1 | 56 de 220 = 25,5 % (a cláusula (c) só dispara acima de 30 %) |
| `golpe_do_criador` (perda **e** `creator_dump` ou ≥ 10 vendedores num slot) | 32,9 % × 32,3 % = **1,02×**; previsão: ≥ 2× |
| forma (reuso ≥ 2 / 3 / 5 / 10) | −0,019 / −0,046 / −0,042 / −0,137; todos os IC cruzam zero |
| perfil × post | −0,066 [−0,151, +0,022] × −0,043 [−0,155, +0,068] |
| só reais (66) | −0,056 [−0,189, +0,082] |
| só o que a base sabia em T (`known_only`, 428) | **+0,009 [−0,077, +0,094]** |
| moinho (o filtro deixa passar reuso 0) | NÃO CONFIRMA: o braço que passa **perde em nível** (−0,003); a curva é pico |

**Contrafactual contábil em 161 posições reais** (Σ −0,520 SOL). O filtro bloqueia 40 posições:
- evita −0,318 SOL de perda e mata +0,167 de ganho, **Δ +0,151 SOL**;
- mata **13 de 53 vencedoras = 24,5 %**, acima dos 20 % que a confirmação admitia: CYBER, NARKY, KODA (duas
  posições), Drillers, LVL, TANK, FLYJEV, $NUVEX, CALLS, SELVAGE, BillyH e Fomo Gnome;
- entre as bloqueadas estão **SIMFTR** e CITIZEN, dois casos de origem da H-014.

Não é uma simulação da carteira: não refaz recompras, pausas nem capital.

## Por que importa

1. **O saldo positivo do contrafactual não autoriza um filtro.**
   - O IC do contraste cruza zero.
   - O filtro mata um quarto das vencedoras reais.
   - O efeito some quando se exige o que a mesa sabia no instante (`known_only`).
2. **A observabilidade cria uma seleção.**
   - O `known_only` perde 184 decisões. Em todas, a identidade da **própria** moeda só foi lida depois da decisão;
     em 58 delas, só depois da saída.
   - Nessas 184 o contraste é −0,138 e a taxa de golpe é 49 % contra 34 %.
   - A leitura REST prioriza apostas abertas (`repo_tape.py`, `collect.py`, `tracker_pins.py`). Por isso, a
     inclusão retrospectiva pode depender da mesma trajetória que produz o desfecho.
   - Isto é **diagnóstico pós-hoc**. Não é resultado e não se promove a hipótese com estes dados.
3. **A ausência de golpe extra pesa contra a tese.** Ela não prova que o mecanismo não existe. Mas o "cartão de
   visita" reciclado não marcou, nesta amostra, as moedas que o criador despeja.

## Como mediríamos aqui

Só vale a pena voltar à ideia com **instrumentação nova** (não implementada; é o próximo passo):
1. Reparar a leitura REST, parada desde 25/09 17:13:16Z.
2. Capturar a identidade **na criação**: evento `create` do WS ou metadados do `uri`.
   - Guardar valor, fonte e instante **do próprio link**. Não servir-se do `social_observed_at` da primeira
     leitura: o `COALESCE` separado deixa gravar um link mais tarde sem mudar esse instante.
   - Distinguir "sem link" de "falha de leitura".
   - Coletar independentemente de a moeda estar numa aposta aberta.
3. Formar uma **coorte nova**, com as 24 h anteriores cobertas **no instante da decisão**, e pré-registar antes a
   variável, a regra de parada e a separação lançador × serviço × viral.

Não escolher perfil, horário ou atraso de leitura pelo melhor D deste estudo.

## Hipótese testável no Lab

Nenhuma nova a partir destes números: seria garimpo. A mesma tese só volta com a coorte prospectiva descrita acima.

## Por que pode falhar

- **Antecipação operacional.** A guarda do moinho recebeu o `created_at` das moedas contadas como proveniência.
  "0 recusadas" certifica só a regra `created_at < decisão`, não que a base conhecia o link em T. Este estudo é
  uma **associação retrospectiva** sob a premissa de metadado da criação.
- **Cobertura parcial.** Um reuso não detectado cai em B. Com seleção dependente da trajetória, a direção desse
  viés é desconhecida.
- **Mistura de mecanismos.** A variável junta lançador, serviço de taxa e notícia viral.

## Segunda opinião (Astra)

- **Desenho:** a Astra pediu cinco correções, todas aplicadas antes dos desfechos:
  - separar a proveniência do link (verificada com dado);
  - cobertura `known_only` com o mesmo corte;
  - golpe literal como medida confirmatória;
  - Holm como exigência do CONFIRMA;
  - regex de comunidade.
- **Veredito:** concorda com NÃO CONFIRMA e reproduziu as saídas. Achou o mecanismo de seleção do s1c e corrigiu
  duas redações que iam além da evidência ("atenua rumo a zero", "o mecanismo falha"). Achou também um bug
  latente na regra do golpe (B = 0), corrigido com teste; o R80 não muda. Nada foi rejeitado.

## Relacionados

[[Fila de Hipoteses]] · [[Dicionario de Variaveis]] · [[Mapa de Estrategias]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[KB-0156-o-despejo-em-bloco-nao-e-uma-rede-de-financiamento]] ·
[[KB-0159-a-desaceleracao-nao-avisa-o-topo]] · [[golpe_do_criador]]
