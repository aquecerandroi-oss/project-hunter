---
tags: [knowledge, nota, volume, dado, qualidade]
tema: Volume e fluxo de ordens
fonte: "Cong, Li, Tang & Yang, Crypto Wash Trading (arXiv:2108.10984, versão de julho de 2021; publicado em Management Science, 2023); Bitwise Asset Management (2019), Analysis of Real Bitcoin Trade Volume, apresentação à SEC"
fonte_url: https://arxiv.org/pdf/2108.10984
lido_em: 2026-09-06
evidencia: estudo revisado (lido na versão de trabalho, com página citada) + relatório de gestora a regulador (não conferido nesta rodada)
hipotese_testavel: sim
astra: concorda com correções (classificação da Binance no estudo verificada por ela)
---

# Volume relatado e o denominador que usamos

## O que afirma

Volume reportado por corretora de cripto não é um dado neutro. Cong, Li, Tang & Yang examinam
corretoras centralizadas com três testes que não dependem de acesso interno: distribuição do
**primeiro dígito significativo** do tamanho dos negócios (lei de Benford), **agrupamento em números
redondos**, e a **cauda** da distribuição de tamanhos (lei de potência). As corretoras reguladas
exibem os padrões observados em mercados financeiros; as não reguladas exibem anomalias nos três, com
wash trading estimado em torno de **77,5% de média e 79,1% de mediana** do volume reportado nesse
grupo (página 5 da versão de trabalho). O motivo é banal e por isso persistente: volume reportado
determina posição em ranking e, com ela, visibilidade e listagem.

**O detalhe que eu tinha declarado como "não sei" e que a Astra foi conferir:** naquele estudo, a
**Binance é classificada como UT1 — "Unregulated Tier-1"** (apêndice, página 62). Registro isso
mesmo sendo o contrário do que me seria conveniente. E registro junto o que impede transportar a
conclusão: a amostra principal é de **9 de julho a 3 de novembro de 2019**, de mercado **spot**, e
os 77,5%/79,1% são agregados **do grupo**, não números atribuíveis a uma corretora específica. Nada
disso caracteriza a Binance USDⓈ-M de hoje, que é o que operamos. O relatório da Bitwise, da mesma
época e também sobre spot, não foi conferido nesta rodada.

## Onde foi mostrado

Corretoras **spot** centralizadas, 2019, negócios agregados por corretora. Não é perpétuo, não é a
nossa janela, e não é o nosso pipeline.

## Como mediríamos aqui

**A invariância, enunciada com a condição que ela exige.** Nós não comparamos volume **entre**
corretoras, que é onde o wash trading distorce mais; todos os denominadores do Lab vêm da nossa
própria coleta do mesmo lugar (`volume_anomaly_v1.py:139`; `features/volume.py:79`). E a razão é
invariante a um **mesmo fator multiplicativo positivo** aplicado a toda a janela, barra atual
inclusive:

```
(c·V_atual) / mediana(c·V₁ … c·V₂₈₈)  =  V_atual / mediana(V₁ … V₂₈₈)
```

**Onde esse argumento falha** — e são quatro lugares, não zero:

- **Contaminação aditiva não se cancela.** Volume atual 400 e mediana 100 dão razão 4; somar 100 a
  cada barra dá 500/200 = **2,5**. "Constante" tem de significar **fator**, não quantidade.
- **Fator variável no tempo.** Volume artificial concentrado na barra atual **fabrica** um pico;
  concentrado no histórico **esconde** um pico real. Mesma corretora não garante fator constante.
- **Fatores constantes mas diferentes entre mercados** preservam a razão de cada mercado e alteram a
  **seleção do universo**, que usa volume **absoluto** de 24 h para ordenar e cortar
  (`market-worker/universe_repo.py:191,204`). A razão fica intacta e a lista de quem é observado
  muda.
- **Invariância não é interpretação econômica.** Razão preservada não demonstra que aquele volume é
  liquidez executável ou demanda independente.

Enunciado correto, então: *a razão é invariante a uma escala multiplicativa comum; não medimos se a
contaminação real obedece a essa condição.*

**A defesa contra minutos ausentes existe, e faz o oposto do que eu tinha escrito.** Eu afirmei que
buracos de coleta **inflam** o denominador. Não é o que o código faz: `aggregate()` exige entradas
finais de 1 minuto (`aggregate.py:65`), define a janela exata terminando em `source_bar_close`
(linha 103) e, se **qualquer** minuto faltar, devolve `Window(reason="gap")` e **descarta o
resultado inteiro** (linha 135). A avaliação fica **indisponível**, não enviesada. É por isso que a
[[EXP-0002-volume-anomaly-v1]] registra que um único minuto ausente custa até ~24 h de avaliações
naquele mercado. O risco real não é denominador furado; é **perda de cobertura**.

## Hipótese testável no Lab

**H-KB0018 — auditoria de cobertura e disponibilidade no instante da decisão** (reformulada; a versão
anterior procurava um viés que o desenho já impede).

1. **Cruzar os sinais emitidos com `ingestion_gaps`** sobre a janela do denominador. **A expectativa
   de "zero interseções" está errada**, e o motivo é de desenho: um gap **recuperado por backfill
   antes da decisão** pode intersectar legitimamente a janela de um sinal válido — a barra existe
   quando a avaliação roda. Portanto o relatório separa: gaps **abertos** na hora da decisão (que
   deveriam ter tornado a avaliação indisponível — e uma interseção dessas **é** um caminho a
   investigar), gaps **recuperados** antes dela (esperados e legítimos), e — nice-to-have aceito —
   contagem de **sinais intersectados** distinta de **pares sinal–gap**, para não duplicar.
2. **Sanidade do volume por mercado**, como hipótese **separada**: excesso de barras com volume
   idêntico repetido e concentração em valores redondos. Não temos tamanho de negócio individual,
   então **o teste de Benford está fora do nosso alcance**; o que resta é bem mais fraco e tem de ser
   rotulado assim.

**O que um resultado negativo significa, e só isso: "não detectado pelos diagnósticos utilizados".**
Não significa "denominador limpo" nem "risco descartado" — era o que eu tinha escrito. Volume
artificial que varie suavemente, sem números repetidos nem redondos, passa nos dois testes com a
razão distorcida.

**Nenhuma mudança de parâmetro decorre disto.** Se (1) achar gaps **abertos** intersectando a janela
de um sinal, o conserto é de engenharia de coleta, não de estratégia.

## Por que pode falhar

- **Confundir invariância de escala com imunidade.** Aditivo, fator variável e efeito sobre a
  seleção do universo são três brechas reais.
- **Extrapolação de mercado e de época.** Spot, 2019, agregados de grupo. Usar UT1 de 2019 para
  afirmar algo sobre a Binance USDⓈ-M de 2026 seria exatamente a citação folclórica que esta base
  existe para não produzir.
- **Testes que não podemos rodar** — sem tamanho de negócio individual, os três do artigo estão fora
  de alcance.
- **Ausência de evidência ≠ evidência de ausência**, e sobre **um dia** de coorte ainda menos.
- **Condenar um sinal por existir um registro `recovered`** — o erro que a reformulação de (1)
  evita.
- **Fontes lidas parcialmente.** A versão do arXiv foi conferida com página; a versão publicada de
  2023 e o relatório Bitwise, não.

## Segunda opinião (Astra)

`.claude/state/astra-review-KB-0018-volume-relatado.md`. **Quatro must-fix, todos aceitos**, e a
contribuição mais valiosa foi ela **conseguir ler o PDF que eu não consegui** e resolver a pendência
que eu tinha declarado como desconhecida: a Binance é **UT1, "Unregulated Tier-1"**, naquele estudo
(página 62), com amostra principal de **9/7 a 3/11/2019** e os 77,5%/79,1% como agregados de grupo
(página 5).

1. **Retirada a afirmação de que gaps inflam o denominador.** O código recusa a avaliação inteira
   (`aggregate.py:135`). Cenário de falha: indisponibilidade corretamente recusada vira diagnóstico
   falso de sinal contaminado, e alguém conserta uma falha que não existe.
2. **"Qualquer interseção vira bug" substituído.** Cenário: backfill completo antes da decisão gera
   sinal válido, condenado pelo protocolo por existir um registro `recovered`.
3. **"Denominador limpo" e "risco descartado" retirados** de um resultado negativo. Cenário: volume
   artificial suave, sem repetição nem números redondos, passa nos dois testes com a razão
   distorcida.
4. **"Nos afeta pouco" restrito à invariância demonstrada**, com as quatro brechas escritas no corpo
   — inclusive a que eu não tinha visto, de fatores constantes por mercado mudando a **seleção do
   universo** (`universe_repo.py:191,204`).

Ela confirmou a defesa de contiguidade com as linhas exatas (`aggregate.py:65,103,135`) e aceitou o
resto da leitura. **Divergência:** nenhuma.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] · [[Index]] ·
[[KB-0013-vpin-e-a-disputa-sobre-toxicidade]] ·
[[KB-0015-volume-relativo-e-o-pico-como-exaustao]] ·
[[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]] · [[EXP-0002-volume-anomaly-v1]] ·
[[Market Collector]] · [[Data Flow]] · [[Open Bugs]] · [[Features]]
