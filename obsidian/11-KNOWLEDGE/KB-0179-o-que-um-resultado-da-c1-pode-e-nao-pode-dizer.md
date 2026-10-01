---
tags: [knowledge, leitura, sintese, cripto, tendencia, media-movel, h-027, interpretacao, hipotese]
tema: "síntese da base de evidência da C1 (H-027: razão à média de 20 dias como estado dos sinais de continuação do Lab, análise retrospectiva pré-especificada) — que resultado seria compatível com a literatura, o que pediria investigação antes de acreditar, e uma conta ilustrativa (não um teto) de quanto a deriva diária vale em R"
fonte: "síntese própria de KB-0173 a KB-0178, com KB-0164, KB-0166, KB-0167 e o pré-registro e a emenda da H-027 na Fila de Hipoteses; a conta ilustrativa usa a média diária do log-retorno do BTC de Deprez & Frömmel (Bitstamp 2013–2022: 0,263 % na legenda da tabela 2, 0,248 % na linha da tabela) e os parâmetros da momentum_v1 no código"
fonte_url: https://biblio.ugent.be/publication/01HY3C3S169G1N6QNYR55NZMFB
lido_em: 2026-10-01
evidencia: "mista — síntese de leituras (estudos revisados, resumos, preprints) e de duas medições nossas já publicadas (KB-0166, KB-0163); a conta de tamanho é aritmética ilustrativa minha com hipóteses declaradas, não medição nem limite"
hipotese_testavel: não
astra: "discorda em parte — 7 must-fix (emenda da H-027 incorporada; conta rebaixada a ilustração sem papel de teto; contraste binário ≠ β ajustado; lucro em nível ≠ superioridade sobre benchmark; alcance do resumo de Cameron et al.; sem identificação de mecanismo por tercil; extrapolações de leitura) — todos aceitos; 1 divergência parcial registrada (β ≥ ~0,15 R fica numa linha de 'investigar influência antes de acreditar')"
status: vivo
owner: sexta-feira
updated: 2026-10-01
confiança: "?"
tipo: leitura
hipotese: H-027
variavel: razao_mm20d
populacao: "coorte prospectiva do Lab emitida em [06/09/2026; 01/10/2026) (pré-registro da H-027); na prática momentum em 16 perpétuos, ~874 unidades em 23 dias — análise retrospectiva pré-especificada"
efeito: —
ic: —
veredito: —
proximo_passo: "ler o resultado da H-027 com a tabela de leitura desta nota; os diagnósticos sugeridos não mudam o rótulo e não autorizam trocar janela, cortes, covariáveis, MRE ou unidade"
classe_de_perda: —
mercado: cripto
---

# KB-0179 — O que um resultado da C1 pode e não pode dizer

> **Síntese, sem medição nova.** Pergunta: *que resultado da C1 seria compatível com a literatura, e qual seria
> suspeito?* Resposta curta: **a literatura deixa o sinal e o tamanho do efeito em aberto** — não há estudo que
> condicione sinais de 5–15 min à tendência diária. Por isso, **`NÃO CONFIRMA` com β perto de zero e IC largo é o
> resultado mais compatível** (e o mais provável dado o poder declarado no registro), **`REFUTA` e β negativo
> também são compatíveis**, e um `CONFIRMA` **não contradiz** a literatura mas é, por desenho, só "critérios
> satisfeitos nesta **análise retrospectiva**" — exige repetição em coorte futura. O que pede investigação antes de
> acreditar não é um tamanho em si, e sim um resultado que **dependa** de poucos dias, poucos mercados, pontos
> extremos ou alavancagem nas covariáveis. Uma conta ilustrativa mostra que **o canal da deriva diária**, sozinho,
> tende a valer centésimos de R; ela **não** limita o β ajustado, porque a H-027 também enxerga outros canais
> (chance de alvo antes do stop, duração, reversão).

## O que a evidência sustenta (claim × evidência)

| afirmação | evidência | estado |
|---|---|---|
| a tendência diária prevê retorno diário em cripto | Detzel (resumo), Hudson & Urquhart, Grobys, Gerritsen — [[KB-0173-tendencia-diaria-em-cripto-o-tamanho-publicado]] | forte **até 2017–2018**, bruto ou custo de equilíbrio |
| o efeito sobreviveu depois | BTC perdeu fora da amostra em 2018; 2018–19 só perdeu menos; momentum frágil depois de 2020 — [[KB-0177-decaimento-e-regime-o-que-a-literatura-de-cripto-mostra]] | fraco/misto; o único líquido pós-2020 é preprint com backtest do autor (Zarattini) |
| o filtro dá retorno a mais | Deprez & Frömmel: retorno sem diferença significativa contra comprar e segurar, ganho em risco — [[KB-0174-o-filtro-de-tendencia-corta-queda-nao-acrescenta-alta]]; nossa H-024 com IC que não exclui o MRE ([[KB-0166-evitar-as-moedas-em-queda-nao-bate-a-cesta]]) | não demonstrado (≠ demonstrado que não) |
| sinais de curto prazo funcionam melhor em tendência de alta diária | **nenhum estudo direto**; analogias: momentum transversal melhor depois de alta (Cooper), crash no repique depois de queda (Daniel & Moskowitz), momentum intradiário mais forte com volatilidade/crise (Gao, Li) — [[KB-0175-estado-de-mercado-condiciona-momentum-mas-em-que-direcao]], [[KB-0176-momento-intradiario-condicionado-o-vizinho-mais-perto]] | **sinal em aberto** |
| um teste único pré-registrado está livre de data snooping | escolha coletiva da janela; inferência com poucos clusters — [[KB-0178-data-snooping-e-poucos-clusters-o-que-vale-para-a-h-027]] | em parte |

## O que a H-027 decide (resumo do registro e da emenda — a Fila não foi editada)

Da [[Fila de Hipoteses]] § H-027, emenda de 2026-10-01 03:02Z: **dois** bootstraps (clusters de dia, ~23, e de
mercado, 16), o p de cada estratégia é o **maior** dos dois antes do Holm; `CONFIRMA` exige IC inferior > 0 nos
**dois**; `REFUTA` (por estratégia) exige IC superior < +0,05 nos **dois**; falha de identificação vira
`LIMITE (instrumento)` e **bloqueia** o `REFUTA`. Regra global: alguma estratégia confirma → CONFIRMA; **as duas**
refutam → REFUTA; as duas em limite → LIMITE DE DADO; qualquer outra combinação → NÃO CONFIRMA. Como a
`volume_anomaly` tem 66 unidades em 2 dias (contagem cega), o esperado é ela ficar em limite — e então **um REFUTA
da `momentum` dá NÃO CONFIRMA global**. É uma **análise retrospectiva pré-especificada**; um CONFIRMA deixa o
bloco `em curso` à espera de coorte futura.

## Conta ilustrativa — quanto vale o canal da deriva (não é teto)

Sob a hipótese de que a deriva diária esperada difere em Δμ entre os estados e é **constante** durante o sinal,
um sinal exposto h horas ganha, em R, aproximadamente `Δμ × (h/24) / R%`, com R% a distância entrada–stop em
fração do preço. Nominalmente 1 R = 1,5 ATR de 15 min na referência (`momentum_v1.py:86`); o código avisa que o
risco na entrada efetiva difere disso (`momentum_v1.py:7`; o denominador real é entrada − stop). Usando R% ≈
1,5 × ATR%:

| cenário ilustrativo | Δμ (%/dia) | h (h) | ATR% | ΔR |
|---|---|---|---|---|
| A | 0,1 | 1 | 2,0 | ~0,001 |
| B | 0,3 | 2 | 1,0 | ~0,017 |
| C | 0,5 | 4 | 0,5 | ~0,11 |

Escalas: a média diária do log-retorno do BTC em 2013–2022 foi 0,26 % (0,263 % na legenda da tabela 2 de Deprez &
Frömmel; 0,248 % na linha da tabela — a fonte é inconsistente; a ordem de grandeza não muda). **Isso não limita
Δμ:** com μ = pμ₊ + (1−p)μ₋, os estados podem se compensar e a diferença pode exceder a média. `h` ≤ 4 h
(`horizon_s` 14 400); duração real e distribuição de ATR% não foram medidas aqui.

**O que a conta diz e não diz.** Diz que, **se o único canal fosse a deriva**, o efeito tenderia a centésimos de
R. **Não** estima o β ajustado da H-027, nem seu limite superior, nem a probabilidade de um veredito: (i) stop e
alvo podem encurtar a exposição (reduzindo o canal da deriva) mas o estado diário também pode mudar a chance de
alvo antes do stop, a duração e a reversão, que a conta não vê; (ii) o β é a associação entre a razão
**residualizada** (depois de `distance_from_24h_low`, ATR% e `return_4h`) e o R_net residualizado — não se converte
num contraste binário sem a distribuição conjunta, e um β negativo **não** implica que a média bruta do grupo ≤ 0
seja maior; (iii) o meio-IC de ±0,12 R e o poder de 80 % para ~0,17 R são aproximações a priori do registro, não
precisão medida, e não são a probabilidade de satisfazer **todas** as cláusulas do CONFIRMA.

## Tabela de leitura

| resultado da H-027 | leitura | diagnósticos antes de acreditar (descritivos, sem mudar rótulo) |
|---|---|---|
| `NÃO CONFIRMA`, β̂ perto de zero, IC cruzando zero | **compatível — o mais provável** pelo poder declarado | os diagnósticos já previstos na emenda (concentração por dia e por mercado, β sem cada um, dispersão residual da razão, número de condição); não trocar janela, cortes ou covariáveis |
| `NÃO CONFIRMA` com β̂ negativo | **compatível** — não contradiz os estudos; o "repique depois de queda que continua no curtíssimo prazo" é **mecanismo hipotético nosso**, por analogia com Daniel & Moskowitz, não resultado demonstrado para estas entradas | não inverter a direção; se virar ideia, é hipótese nova em coorte nova |
| `REFUTA` da `momentum` | **compatível**; com a `volume_anomaly` em limite, o global é `NÃO CONFIRMA` (emenda, item 4) | conferir que não houve `LIMITE (instrumento)`, que bloquearia o REFUTA |
| grupo > 0 perde menos que ≤ 0, os dois negativos | **compatível** com "corta queda" | — |
| grupo > 0 **lucrativo em nível** | **compatível; insuficiente** para demonstrar alfa ou lucro futuro (lucro em nível ≠ superioridade sobre benchmark) | estabilidade entre dias; retorno do BTC e da cesta dos 16 mercados nos mesmos dias, para ver quanto do nível acompanha o mercado (sem concluir causalidade) |
| `LIMITE DE DADO` na `volume_anomaly` | **esperado** pela contagem cega | — |
| `CONFIRMA` com limite inferior pouco acima de zero nos dois bootstraps | **não contradiz a literatura; frágil** — num programa com várias tentativas de tendência ([[Registro de Tentativas]]), um p de Holm perto de 0,05 é evidência fraca (contexto de Harvey et al., não limiar alternativo) | wild cluster bootstrap-t por dia e por mercado, separadamente, como sensibilidade; repetição pré-registrada em sinais emitidos depois do registro (o registro já exige) |
| β̂ grande (≥ ~0,15 R por desvio robusto) com IC acima de zero | **não calibrado pela literatura consultada** — a conta ilustrativa só cobre o canal da deriva; o tamanho sozinho não é anomalia | influência de pontos extremos (R_net aparado em ±3 R) **e** alavancagem nas covariáveis (aparar o desfecho não resolve esta); β sem cada dia e sem cada mercado; β com o estado do BTC no lugar do de cada mercado (se reproduz, há componente comum — não prova ausência de informação incremental) |
| contínua passa, patamar ou metades falham | **não satisfaz o protocolo** (NÃO CONFIRMA); pode ser instabilidade, não linearidade ou imprecisão — não prova "pico" | distribuição da razão por dia e por mercado |
| efeito concentrado num tercil de ATR% | **não identifica mecanismo** — pode ser interação tendência × volatilidade, ou tercis com dias e mercados diferentes | β por tercil de ATR% só como descritivo |

## O que isso não diz

- **Não** diz que a tendência diária é inútil: o valor documentado está em **gestão de exposição em dias**, e a
  H-027 mede outra coisa.
- **Não** autoriza trocar 20 por 50 ou 200 dias depois de ver; essa busca é o que White e Hansen corrigem.
- **Não** diz qual regime vigorou em set/2026 nem como a variação da razão se divide entre dias e mercados — não
  medi. A contagem cega diz só que 676 de 874 unidades tinham razão > 0 (registro da H-027).

## Como mediríamos aqui

Já pré-registrado ([[Fila de Hipoteses]] § H-027 e emenda; esta nota não os edita). Os diagnósticos da coluna da
direita podem ir no relatório como descritivo sem rótulo, se o orquestrador quiser.

## Por que pode falhar (esta síntese)

- A conta é ilustrativa (deriva constante, sem stop/alvo, atraso e custo).
- Muitas fontes foram lidas só pelo resumo (ver cada nota). Textos novos lidos: Deprez & Frömmel (inteiro, versão
  de autor), Li, Sakkas & Urquhart (seções 1–3, versão aceita), Shen et al. (seções 3.5–3.7 relidas, versão aceita)
  e Rozario et al. (inteiro).
- Não usei os textos integrais de: Fieberg et al. (Cambridge devolveu 429) e Zarattini et al. (SSRN 403) — só os
  resumos entram, como dito em KB-0173. Não abri: Wen et al. (NAJEF 2022, fechado), Asem & Tian (JFQA — só título e
  descrição do buscador), Hurst, Ooi & Pedersen, Kim, Tse & Wald; nada deles entrou.

## Segunda opinião (Astra)

`.claude/state/astra-review-KB-tendencia-diaria.md` (síntese em
[[06-DECISIONS/Revisoes-Astra/KB-tendencia-diaria|KB-tendencia-diaria]]). Ela recalculou os três cenários (0,0014 /
0,0167 / 0,1111 R) e concordou com a não transferência direta de regras diárias para sinais intradiários com
barreiras, com a separação custo de equilíbrio × bruto × líquido e com repetição futura pré-registrada.
**Sete must-fix, todos aceitos:**

1. **A emenda da H-027 não estava na síntese** (dois bootstraps, maior p, os dois ICs, `LIMITE (instrumento)`, regra
   global, "retrospectiva"). Cenário dela: a `momentum` refuta e a `volume_anomaly` fica em limite — o global é NÃO
   CONFIRMA, não REFUTA. Corrigido (seção "O que a H-027 decide").
2. **A conta funcionava como teto.** A média incondicional não limita o contraste condicional; a fonte tem 0,263 % ×
   0,248 %; stop/alvo não são só desconto; 1 R nominal ≠ risco na entrada. Rebaixada a ilustração do canal da
   deriva, sem papel de teto.
3. **Contraste binário ≠ β ajustado**, e β negativo não implica média bruta maior no grupo ≤ 0; poder e meio-IC são
   aproximações do registro. Corrigido.
4. **Lucro em nível ≠ superioridade sobre benchmark** (KB-0174 e esta nota). O grupo > 0 lucrativo passou de
   "suspeito" a "compatível; insuficiente para alfa".
5. **Cameron, Gelbach & Miller pelo resumo** não demonstram que o IC percentil de pares com 23 dias fica estreito;
   KB-0178 corrigida, com o bootstrap de mercado da emenda.
6. **Tercil de ATR% não identifica mecanismo**; "pico" e "estado do BTC" reescritos (KB-0176 e esta nota).
7. **Extrapolações de leitura:** "robusto entre estados" ≠ "não depende do estado" (KB-0175); Li et al. lido em
   seções, não inteiro; Fieberg/Zarattini entram pelo resumo; "um ou dois estados" e "variação mais entre mercados"
   não estabelecidos (KB-0175, KB-0177). Corrigidos.

Nice-to-have aceitos: cenários sem rótulo de probabilidade (A/B/C), aparar desfecho ≠ alavancagem nas covariáveis,
t > 3 só como contexto, "espere a metade" retirado da KB-0177.

**Divergência parcial (registrada):** ela propôs tirar o tamanho de β da tabela ("o tamanho sozinho não é
anomalia"). Concordo que não é anomalia, mas mantive uma linha para β̂ ≥ ~0,15 R como **"não calibrado — investigar
influência antes de acreditar"**, porque nenhuma fonte lida oferece mecanismo que produza esse tamanho e o
registro só tem 23 clusters de dia; a linha não muda o rótulo. Sobre β negativo, **concordância**: compatível quer
dizer "não contradiz", não "previsto".

## Relacionados

[[KB-0173-tendencia-diaria-em-cripto-o-tamanho-publicado]] · [[KB-0174-o-filtro-de-tendencia-corta-queda-nao-acrescenta-alta]] ·
[[KB-0175-estado-de-mercado-condiciona-momentum-mas-em-que-direcao]] · [[KB-0176-momento-intradiario-condicionado-o-vizinho-mais-perto]] ·
[[KB-0177-decaimento-e-regime-o-que-a-literatura-de-cripto-mostra]] · [[KB-0178-data-snooping-e-poucos-clusters-o-que-vale-para-a-h-027]] ·
[[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] · [[KB-0166-evitar-as-moedas-em-queda-nao-bate-a-cesta]] ·
[[KB-0164-momentum-semanal-em-cripto-grande]] · [[KB-0163-perto-da-maxima-de-24h-nao-separa-os-sinais-do-lab]] ·
[[Registro de Tentativas]] · [[Fila de Hipoteses]] · [[Proximas Hipoteses]] · [[Strategy Backlog]]
