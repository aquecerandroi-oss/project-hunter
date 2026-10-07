**RESUMO**

**Ainda não fecharia a revisão.** Há correções substanciais, mas reproduzi dois casos de CONFIRMA indevido perante o texto registrado. A calibração é aceitável como **evidência condicional aos cenários simulados**, não como garantia dos limites anunciados.

**ARQUIVOS**

Revisão como `quant-engineer`, somente leitura. Nenhum arquivo alterado; nenhum commit ou consulta à VPS.

**TESTES**

`uv run --no-sync pytest .claude/state/h036 -q -p no:cacheprovider`, com bytecode desabilitado:

```text
31 passed in 4.62s
Hashes verificados: 42; divergencias: 0
Emenda presente na Fila: True
```

Também executei reproduções sintéticas em memória. Não rerodei as 20.000 simulações.

**MUST-FIX**

Situação dos nove itens anteriores:

| Item da rodada 1 | Estado | Motivo |
|---|---|---|
| 1. Calendário × informação | **Parcial** | Bonferroni resolve a dependência entre consultas, mas a aproximação da t não entrega as caudas declaradas; ver abaixo. |
| 2. REFUTA após parada | **Parcial** | A calibração própria melhorou; ainda não inclui a regra completa de adiamento por cobertura/instabilidade. |
| 3. Precedência e portões | **Parcial** | Ordem correta em [decision.py:85](C:/dev/project-hunter/.claude/state/h036/decision.py:85); população vazia quebra antes dos portões. |
| 4. Simulação fiel e poder | **Parcial** | Compartilha `decide`, mas não todo o procedimento; há também divergência nas metades. |
| 5. “B estrito” executável | **Fechado** | Primário todo a mercado; B explicitamente condicionado, conforme [emenda:1](C:/dev/project-hunter/.claude/state/h036/prereg_emenda_frozen.md:1). |
| 6. Fallback de custo | **Parcial** | Retirou 15,7 bp e acrescentou cobertura; restam lacunas no p99 e no estresse. |
| 7. Entrada passiva | **Fechado** | Retirada da inferência; conclusão limitada à aproximação, na [emenda:1](C:/dev/project-hunter/.claude/state/h036/prereg_emenda_frozen.md:1). |
| 8. Export e preservação | **Parcial** | Preços removidos, T0 protegido e export semanal; falta a semana corrente da consulta. |
| 9. Congelamento e regra global | **Fechado** | Manifesto íntegro e decisões intermediárias explicitamente permitidas na [emenda:1](C:/dev/project-hunter/.claude/state/h036/prereg_emenda_frozen.md:1). |

**1. A fronteira t é numericamente permissiva no mínimo de semanas.**  
[decision.py:37](C:/dev/project-hunter/.claude/state/h036/decision.py:37) usa expansão truncada; o teste apenas compara duas implementações da mesma aproximação ([test_decision.py:83](C:/dev/project-hunter/.claude/state/h036/test_decision.py:83)).

Reproduzi, com cinco semanas, 30 dias, 150 trades, metades e estresse positivos:

```text
t(0,9995; 4): código 8,187033; valor exato 8,610302
t observado: 8,4 → código CONFIRMA
```

Pela fronteira registrada, deveria continuar. Para REFUTA, `t(0,9975;4)` também fica abaixo: **5,483969 versus 5,597568**. Corrigir o quantil e recalibrar.

**2. A mediana entra na metade errada quando há número ímpar de dias.**  
O contrato diz “antes × a partir da mediana” ([registro:6](C:/dev/project-hunter/.claude/state/h036/prereg_frozen.md:6)); `ceil(dias/2)` coloca o dia mediano na primeira metade ([decision.py:70](C:/dev/project-hunter/.claude/state/h036/decision.py:70)).

Reprodução com 181 dias: primeiros 90 com média −0,001; dia mediano +0,1; últimos 90 +0,2. **O código CONFIRMA**, embora a primeira metade contratual seja negativa. Corrigir ou emendar explicitamente essa convenção antes de T0.

**3. População sem trades quebra; o ensaio não valida exclusões.**  
Com apenas `no_entry`, reproduzi `ValueError: min() iterable argument is empty` em [look.py:98](C:/dev/project-hunter/.claude/state/h036/look.py:98). O mesmo acontece se todos os elegíveis estiverem censurados ou sem funding. Deveria produzir continua/LIMITE, com contagens.

O denominador prospectivo está correto: exclui `no_entry` e mantém os demais estados ([look.py:94](C:/dev/project-hunter/.claude/state/h036/look.py:94)). Porém, `--ensaio` filtra `exit_ts`, eliminando também pendentes/censurados sem saída ([gen_look.py:21](C:/dev/project-hunter/.claude/state/h036/gen_look.py:21)). **Cenário:** 213 terminais e 20 pendentes virariam “0% excluídos”, apesar de 8,6% na população elegível. O ensaio comprova a aritmética dos terminais, não esse portão.

**4. A calibração não cobre o procedimento completo de parada.**  
A simulação fixa cobertura válida ([run_design2.py:85](C:/dev/project-hunter/.claude/state/h036/run_design2.py:85)) e não chama `robust_label`; a consulta pode transformar REFUTA intermediário em continua ([look.py:57](C:/dev/project-hunter/.claude/state/h036/look.py:57)).

**Cenário:** a simulação encerra um caminho em L1; a consulta continua por instabilidade e ganha oportunidades posteriores de CONFIRMA/REFUTA. Portanto, os erros simulados não são automaticamente limites desse procedimento.

Sobre **(c)**: aceito os resultados como planejamento condicionado à cobertura perfeita e aos cinco modelos. Para 20.000 caminhos, calculei ICs Monte Carlo de Wilson de 95%:

- 0,0236 → **[0,02159; 0,02580]**;
- 0,0189 → **[0,01710; 0,02088]**.

Logo, não demonstram tetos de 0,0236/0,019. Bonferroni limita a união **quando os testes individuais respeitam seus níveis**; não torna CR1+t exato por si só ([NIST](https://www.itl.nist.gov/div898/handbook/prc/section4/prc463.htm)). Emendar essa garantia e explicitar o que ficou fora da calibração.

**5. O tratamento de custo ausente ainda tem caminhos incompletos.**

- O p90/p99 só usa snapshots do minuto exato ([look.py:96](C:/dev/project-hunter/.claude/state/h036/look.py:96)), embora vizinhos contem como medidos. **Cenário:** 95% dos trades medidos por vizinhos e 5% por mediana: cobertura passa, mas `observed` vazio produz p99 `NaN`; a verificação de estabilidade perde um veredito que poderia ser calculado.
- Quando falta o minuto seguinte à saída, o estresse reutiliza o spread atual ([look.py:113](C:/dev/project-hunter/.claude/state/h036/look.py:113)). **Cenário:** justamente esse minuto teria spread elevado; o estresse fica artificialmente positivo e permite CONFIRMA. Congelar fallback/cobertura para esse insumo também.

**6. Falta export complementar na própria consulta.**  
A cadência preserva somente semanas encerradas ([gen_export2.py:10](C:/dev/project-hunter/.claude/state/h036/gen_export2.py:10)); L1 ocorre quarta-feira e inclui emissões até quarta às 06:00Z ([gen_look.py:25](C:/dev/project-hunter/.claude/state/h036/gen_look.py:25)).

**Cenário:** seguindo exatamente a cadência, os trades de segunda a quarta ficam sem spread exportado, recebem substitutos ou fazem falhar a cobertura apesar de os dados existirem. Registrar export complementar obrigatório antes de abrir os resultados.

**NICE-TO-HAVE**

- Validação Monte Carlo independente após congelar as correções; a calibração fina reutiliza os mesmos caminhos ([calib_pref.py:8](C:/dev/project-hunter/.claude/state/h036/calib_pref.py:8)).
- Publicar contagens separadas de `no_entry`, censura, pendência e funding ausente, além do total agregado ([look.py:136](C:/dev/project-hunter/.claude/state/h036/look.py:136)).

**O QUE EU FARIA DIFERENTE**

Antes de T0, acrescentaria emenda curta cobrindo os seis pontos acima, preservaria os artefatos atuais e congelaria novos hashes após correções e validação.

**CONCORDO COM**

O alinhamento ISO está correto: quarta–domingo ficam na primeira semana; segunda abre a seguinte ([decision.py:45](C:/dev/project-hunter/.claude/state/h036/decision.py:45)). A precedência também está correta; não são esses os bloqueios.

**OBSIDIAN**

- **Fila de Hipóteses — H-036:** registrar a nova emenda e delimitar o alcance da calibração.
- **Revisões Astra — H-036-prereg:** acrescentar rodada 2, estados dos nove itens e reproduções.
- **KB-0193 — O custo Binance medido nos instantes do Lab:** documentar cobertura do estresse e tratamento dos spreads ausentes.