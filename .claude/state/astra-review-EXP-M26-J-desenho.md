## RESUMO

**Aceito 1, 2, 3, 4, 6, 8 e 10, com as precisões abaixo. Mudo 5, 7 e 9 antes de congelar J.** Papel: `quant-engineer`, modo OPINIÃO. São fechamentos executáveis do desenho consensuado, cujo aceite de J permanece explícito em [desenho:705](C:/dev/project-hunter/docs/design/exp-m26-grafico-moedas-maduras.md:705).

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

## TESTES

Revisão estática com `Get-Content -Encoding utf8` e `rg -n`. Não executei pytest, lint, SQL ou o moinho.

Calculei dois contraexemplos sintéticos em JavaScript, em memória; saída real:

```text
identidade:
  D_linha_integral = 0.07272727272727272
  D_linha_com_slope = 0.04
  D_slope = 0.04
  ausencia_slope = 0.024390243902439025
  dispara_comparacao_errada = false
  dispara_populacao_comum = true

pares_orfaos:
  completos = 100
  sem_R1 = 26
  taxa_ausentes = 0.20634920634920634
```

Isso verifica a aritmética dos cenários, não a implementação.

## MUST-FIX

**(5) Mudo para leitura analítica fixa: `L = corte + 2 h`; execução permitida somente quando `agora >= L`.**

Aceito `M_min` e `M_max` como os primeiros 00:00Z **maiores ou iguais** aos respectivos limites, metas entre elegíveis conhecidos de C, dentro de `[T0,M)`, e aposentadoria antecipada de qualquer braço como interrupção invalidante. Os mínimos inferenciais continuam separados das metas de inscrição.

A classificação deve usar **L**, nunca o horário efetivo da execução:

- `entry_at` ausente ou `entry_at > L`: F;
- entrada até L e saída ausente ou `exit_at > L`: C;
- saída até L: candidata a A, ainda sujeita à precificabilidade.

**Cenário de falha:** comando executado seis horas depois do corte encontra uma aposta encerrada em corte + 3 h. Usar “leitura = agora” transforma a censura prevista em retorno observado e permite alterar o resultado apenas atrasando o comando. O protocolo fixa a leitura em corte + 2 h ([desenho:411](C:/dev/project-hunter/docs/design/exp-m26-grafico-moedas-maduras.md:411)).

**(7) Mudo o universo das decisões comuns para incluir também propostas órfãs de R1.**

A união de linhas L/H é a base, mas deve receber os mints com proposta desses braços sem registro R1. Esses casos entram como **falha instrumental/par ausente não estressável**, deduplicados por mint; nunca viram pares completos por reconstrução posterior. Aplicar também a distinção E versus falha instrumental ao denominador elegível.

**Cenário de falha:** 100 pares completos e 26 mints com propostas L/H, mas nenhuma linha R1. A definição “mint com linha de L ou H” reporta 0% ausentes; a população reconciliada tem **26/126 = 20,63%**, ultrapassando o teto. A obrigação de contar propostas sem R1 está explícita em [DATABASE:8531](C:/dev/project-hunter/docs/DATABASE.md:8531); a distinção de exclusões nos pares, em [desenho:439](C:/dev/project-hunter/docs/design/exp-m26-grafico-moedas-maduras.md:439).

**Aceito o restante do item:** alinhamento faithful/minuto/foto, separação entre falta de fill e censura, ambos C com diferença p10 recalculada e nível H em perda integral, e não testável com `p=1` na família de tamanho 2. Preservar os outros dois casos: H censurado em perda integral; L censurado no p90 observado de L dos pares completos ([desenho:481](C:/dev/project-hunter/docs/design/exp-m26-grafico-moedas-maduras.md:481)).

**(9) Mudo a identidade para comparar `D_slope` com `D_linha_comparável`, ambos recalculados na mesma população.**

Procedimento executável:

1. Partir dos avaliáveis dos estratos válidos da primária.
2. Retirar slopes ausentes.
3. Manter suporte temporal com os dois grupos **em ambas as divisões**.
4. Recalcular os dois contrastes nessa população, cada qual com os pesos da sua divisão.
5. Disparar identidade se `D_slope >= D_linha_comparável`.

O D_linha principal permanece intacto; esse recálculo pertence ao diagnóstico de identidade. Ausência de suporte impede satisfazer a cláusula. Preservar também a trava de **slope ausente >20%**, expressa em [desenho:396](C:/dev/project-hunter/docs/design/exp-m26-grafico-moedas-maduras.md:396).

**Cenário de falha:** em dez estratos iguais, cada um tem dez true com retorno 0,04, trinta false com retorno zero e um true com retorno 0,40 sem slope. Nos observados, slope e linha separam exatamente os mesmos mints. D_linha integral é 0,072727; D_slope é 0,04. Compará-los assim deixa passar uma variável perfeitamente redundante, apesar de só **2,44%** dos slopes faltarem. Na população comum, ambos dão 0,04 e a identidade dispara. A população comparável foi deixada como aceite explícito de J ([diálogo:597](C:/dev/project-hunter/.claude/state/dialogue-EXP-M26.md:597)).

**Aceito tercis e planalto**, com uma precisão: os vinte avaliáveis por grupo devem estar nos estratos com sobreposição **dentro daquele tercil**. Vinte true em blocos distintos dos vinte false não tornam D estimável. Classes e estratos são refeitos em cada teto do planalto; D indefinido não satisfaz `D>0`.

## NICE-TO-HAVE

- Congelar gerador pseudoaleatório, ordenação das unidades e índices sorteados. Reutilizar sementes, sozinho, não garante números aleatórios comuns se os arrays mudarem entre observado e estresse.
- Publicar contagens excluídas por falta de sobreposição e a fração de réplicas inválidas em cada procedimento.
- Corrigir o exemplo SQL de [DATABASE:8560](C:/dev/project-hunter/docs/DATABASE.md:8560), para não ensinar um denominador diferente do protocolo.

## O QUE EU FARIA DIFERENTE

Transformaria os três cenários acima em aceites sintéticos de J, junto dos casos já acordados: bloco duplicado, réplica vazia, nenhum censurado true e grupo sem observados. Não alteraria limiares, braços ou saída.

## CONCORDO COM

**(1) Aceito.** Estrato é a chave UTC completa `(data, floor(hora/6))`, com intervalos semiabertos. Um bloco duplicado dobra contagens e peso: `w(2n_t,2n_f)=2w(n_t,n_f)`. Não dobra o número de blocos independentes da amostra original. Base: [desenho:394](C:/dev/project-hunter/docs/design/exp-m26-grafico-moedas-maduras.md:394).

**(2) Aceito como convenção pré-registrada de J.** Fórmula, normalização, reconstrução dos estratos, IC percentil linear, p bilateral com correção `+1` e sementes propostas são compatíveis com o contrato ([desenho:444](C:/dev/project-hunter/docs/design/exp-m26-grafico-moedas-maduras.md:444)).

Fixar expressamente: 10.000 réplicas **tentadas** por procedimento; até 1% inválidas, quantis sobre as válidas, sem repor silenciosamente os sorteios; acima de 1%, IC indisponível e **NÃO CONFIRMA, inclusive impedindo REFUTA**. O limiar de 1% é convenção operacional nova, não garantia estatística demonstrada.

**(3) Aceito.** `fidelity` é uma bifurcação anterior à contagem: não faithful termina em I da classe conhecida ou U; uma recusa posterior não pode excluí-lo como E. Proposta de C sem R1 entra uma vez por mint em U, conservando o motivo instrumental. Não reconstruir classe usando oportunidade posterior. Isso corresponde à falha instrumental obrigatória de [DATABASE:8527](C:/dev/project-hunter/docs/DATABASE.md:8527).

**(4) Aceito.** Exclusão permanente por mint em qualquer dos três braços antes de T0 protege as duas análises contra contaminação do piloto ([desenho:334](C:/dev/project-hunter/docs/design/exp-m26-grafico-moedas-maduras.md:334), [desenho:405](C:/dev/project-hunter/docs/design/exp-m26-grafico-moedas-maduras.md:405)). `created_at` do controle serve como âncora do seed; registrar o timestamp exato e verificar que os três braços pertencem ao mesmo seed.

**(6) Aceito**, entendendo C aqui como censurados preenchidos:

- False censurados aumentam `n_f` e o peso; a média permanece a dos false observados, recalculada na réplica.
- Sem false observado, não há média imputável: **o estrato inteiro fica fora do contraste**, não se inventa zero nem se transporta média de outro bloco.
- Nível true é a média simples das unidades true nos estratos válidos, incluindo censurados no estresse.
- Ponto de inversão: com suporte e contagens fixos, escrever `D(x)=a+bx`. Se `b=0`, declarar “sem solução única/sem censurados true com peso”, sem dividir por zero.
- Aceito grade 5×5 pontual: `−1`, ponto médio até a média, média, ponto médio até p90, p90.

São cenários condicionais, como acordado em [desenho:464](C:/dev/project-hunter/docs/design/exp-m26-grafico-moedas-maduras.md:464) e [diálogo:512](C:/dev/project-hunter/.claude/state/dialogue-EXP-M26.md:512).

**(8) Aceito.** H-022 recebe o rótulo primário; H−L recebe rótulo próprio. Compartilham Holm, não o sucesso obrigatório dos dois contrastes. “Mesma regra” significa mesma lógica de precedência e concordância dos ICs, com os requisitos específicos de cada contraste ([desenho:396](C:/dev/project-hunter/docs/design/exp-m26-grafico-moedas-maduras.md:396), [desenho:502](C:/dev/project-hunter/docs/design/exp-m26-grafico-moedas-maduras.md:502)).

**(10) Aceito.** Denominador é o `size_sol` congelado dos parâmetros, **0,07**, para retorno observado, perda integral e cenário contábil. A definição normativa está em [desenho:491](C:/dev/project-hunter/docs/design/exp-m26-grafico-moedas-maduras.md:491); o SQL com `initial_risk_sol` em [DATABASE:8560](C:/dev/project-hunter/docs/DATABASE.md:8560) diverge dela. J deve seguir o protocolo.

## OBSIDIAN

- **EXP-M26 — estrutura do gráfico em moedas maduras:** acrescentar os fechamentos executáveis de J e os três aceites pendentes, preservando o protocolo histórico.
- **Diálogo — EXP-M26:** registrar a reconciliação sobre leitura fixa, propostas órfãs e população comparável da identidade.
- **Revisões-Astra — EXP-M26/J:** registrar este parecer e seus contraexemplos sintéticos, sem declarar implementação aprovada.