---
tags: [astra, revisao, shadow-lab, pesquisa, estatistica]
updated: 2026-09-06
---

# Revisão da Astra — as hipóteses de falha do Shadow Lab (S4, 2026-09-06, tarde)

Transcrição integral em `.claude/state/astra-review-S4-hipoteses.md`. Perguntei sobre a **honestidade
estatística** de duas hipóteses de falha que eu ia registrar em [[EXP-0001-momentum-v1]] e
[[EXP-0002-volume-anomaly-v1]] sobre a coorte da VPS (`as_of = 2026-09-06T13:00:00Z`): (H1) se a
invalidação está matando operações que teriam batido o alvo, e (H2) se os outcomes com funding não
apurável são ausência de dado ou falha de identificação temporal.

**Resultado: os cinco must-fix foram aceitos e aplicados antes de publicar.** O padrão dos achados é
o mesmo das outras revisões dela: a aritmética estava certa, o **enunciado** estava maior que a
evidência.

## Os cinco must-fix

**1. "Intervalo que contém o contrafactual" era falso.** Eu ia escrever que substituir os invalidados
pela média dos targets e pela média dos stops produz um intervalo `[−0,3560; +0,1597]` que "contém o
contrafactual e atravessa o zero". A conta preserva os pesos corretos — o problema não é média de
médias. O problema é **transportar a média de outro grupo para os invalidados sem justificar a
imputação**: eles podem ter outra geometria entrada–stop–alvo, outro tempo restante e outra exposição
a funding, e o modelo admite stop na abertura abaixo do nível (`walker.py:71`), então a média
observada dos stops nem sequer é um piso financeiro garantido. Passaram a se chamar **dois cenários
de substituição que mostram sensibilidade**, explicitamente não-limites. Ela também derrubou a saída
que eu ofereci: bootstrap sobre as distribuições de target/stop **não** resolve — acrescentaria
incerteza amostral a uma imputação que continua sem identificação.

**2. "Não está gravado em lugar nenhum" era forte demais.** O acompanhamento realmente para na
invalidação (`walker.py:173`), então o MFE do outcome não responde o que aconteceria depois. Mas as
velas de 1 min **estão** persistidas e um replay é possível em princípio; o que falta é verificar a
continuidade da cobertura até o horizonte de cada entrada. Virou pré-requisito declarado, não
resultado. **No mesmo achado ela pegou um erro de fato meu:** as duas estratégias têm regras de
invalidação **diferentes** — momentum fecha abaixo do máximo anterior no timeframe de 15 min
(`momentum_v1.py:282`), volume fecha abaixo do **meio da barra do sinal** em 5 min
(`volume_anomaly_v1.py:241`). Eu estava tratando as duas como a mesma regra, o que faria atribuir à
"invalidação" uma diferença que é de desenho. Verifiquei no código antes de aceitar.

**3. "72 bugs de identidade e 3 corridas comprovadas" excedia a evidência.** Substituído por
evidência graduada: **69** casos com candidato próximo mas não exato (compatível com falha de
identidade temporal), **3** com casamento exato hoje e causa histórica por demonstrar, **1** sem
candidato em ±60 s (e mesmo esse exige verificar se a liquidação era devida).

**4. Os três deltas de 0 ms não provam corrida de leitura.** `FundingRate` não registra horário de
ingestão e `SignalOutcome.updated_at` não registra o snapshot da consulta de funding, então não há
como datar a visibilidade da linha. A corrida é **plausível** — o coletor consulta, enfileira e só
depois persiste (`market-worker/funding.py:55`) —, mas não demonstrável com agregados. E os dois
mecanismos não são mutuamente exclusivos: os 69 desencontros também podem ter sofrido chegada tardia.

**5. Corrigir com "linha mais próxima em ±2 s" criaria dois defeitos novos.** Cenário concreto: a
grade calculada tem `08:00:00` e o observado tem `08:00:00.005`; a função hoje faz a **união** dos
dois conjuntos, então dar tolerância só ao `known.get()` permite **cobrar a mesma liquidação duas
vezes** (`strategy-worker/funding.py:126`). Segundo cenário: saída às `08:00:00` e liquidação às
`08:00:00.005` — uma janela larga passa a cobrar funding **posterior** à saída, enquanto o recorte
atual termina em `exit_ts` (`settle.py:60`). ±2 s é janela **diagnóstica**, não tolerância
demonstrada. O protocolo correto precisa validar a cadência vigente, exigir associação única sem
reutilizar liquidação, preservar o timestamp original separando identidade de incidência, recusar
ambiguidades nas fronteiras e usar tolerância muito menor que metade do espaçamento mínimo validado.
Registrado em [[Open Bugs]].

## O que ela acrescentou e eu adotei

- **Ponto de equilíbrio em vez de cenário.** "Quanto os invalidados precisariam render para zerar a
  coorte" é uma pergunta respondível sem imputação: **+0,22035 R** no momentum (renderam −0,5768) e
  **−0,06620 R** no volume (renderam −0,7164). E para os excluídos por funding: **+1,36654 R**
  (momentum) e **+2,02279 R** (volume) — nenhum plausível, ou seja, funding não resgata nenhuma das
  duas coortes.
- **Medir a composição do grupo excluído** com `r_ex_funding`, que existe para todos eles. Foi o que
  revelou que a direção do viés é **oposta** entre as duas estratégias (momentum −0,3526 contra
  −0,2102; volume +0,0225 contra −0,2302), ambas abaixo de 0,03 R.
- **Contar liquidações distintas, não outcomes**: são **66 liquidações em 57 mercados e 7 instantes**,
  não 73 falhas independentes.
- **Separar o efeito da saída sobre entradas fixas do efeito sobre a estratégia inteira**: terminar um
  acompanhamento libera a barreira de reentrada (`outcomes.py:102`), então mudar a saída muda também
  as entradas seguintes. São dois experimentos, não um.

## Divergência registrada

Nenhuma que eu tenha decidido contra ela nesta rodada. A única coisa que fiz além do que ela pediu
foi **medir o tamanho do funding quando ele foi apurado** — 0 acompanhamentos de momentum e 9 de
volume atravessaram uma liquidação, com efeito médio de −0,000195 R e máximo de 0,028 R. Isso
transforma a H2 de "possível explicação do vermelho" em "defeito de instrumento com efeito duas
ordens de grandeza menor que a expectancy", que é uma conclusão mais dura do que qualquer um dos dois
motores tinha antes de rodar a consulta.

## Relacionadas

[[EXP-0001-momentum-v1]] · [[EXP-0002-volume-anomaly-v1]] · [[S4-avaliacoes-shadow]] · [[S4-vps-lab]] ·
[[Strategy Performance]] · [[Open Bugs]] · [[Mente da Sexta-feira]] · [[Experiments Index]]
