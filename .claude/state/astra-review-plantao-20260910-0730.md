**RESUMO**
Eu faria **D-P15 → D-P14 → D-P13**: primeiro validar a contabilidade do funding, depois medir a fronteira de custo; a covariância fica como diagnóstico exploratório. Parecer como `quant-engineer`: **DONE_WITH_CONCERNS**.

**ARQUIVOS**
Nenhum criado ou modificado; nenhum commit.

**TESTES**
Não executei testes nem consultas à VPS. Conferi o rascunho, memória, código e fontes primárias; não reconfirmei o snapshot dos 782 símbolos nem os números do PPI/BTC.

**MUST-FIX**

- **D-P15: corrigir o mecanismo descrito.** Dois gaps novos iguais vencem a moda dos três; não são necessários três ([funding.py:198](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:198)). Settlements observados entram mesmo fora da grade inferida; esta serve para detectar ausências ([funding.py:325](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:325)). Cenário: na volta 1 h→4 h, a grade antiga pode produzir `funding_missing` falso; na aceleração, pode deixar de detectar um settlement ausente. Medir **cobertura, falsos nulos e diferença de custo**, não presumir subcobrança em toda transição.
- **D-P13: retorno menos média do dia não basta.** Média do dia completo usa futuro; média acumulada é causal, mas não garante uma inovação. Eu definiria \(c_t=r_t-\widehat E[r_t\mid\mathcal F_{t-1}]\), com estimador fixado e ajustado apenas ao passado. Alinhar com a decisão tomada **depois** da barra fechada; retorno posterior responde a outra pergunta, de desempenho.
- **π=0/1 é aceitável como proxy descritiva**, numa grade completa de barras elegíveis, incluindo ausência de posição; indisponibilidade não vira zero. Só entradas dão π constante e covariância zero. Separar posição mantida de mudança de posição, Δπ. Cov<0 não comprova execução provedora: comprar agressivamente uma queda também pode dar sinal negativo.
- **Retirar a expectativa obrigatória de Cov<0.** A regra combina desconto em relação à média com fechamento acima do meio da barra; pode comprar uma barra positiva de recuperação ([mean_reversion_v1.py:224](/C:/dev/project-hunter/packages/core/hunter_core/strategies/mean_reversion_v1.py:224)). Cov>0 nessa escala não refuta o mecanismo de reversão.
- **Retirar “N² explica a KB-0083”.** O teorema de regret exige condições sobre processo e média da política; o corolário N² acrescenta hipóteses de correlação/equilíbrio/impacto. Não equivale a somar R de versões. [Aldridge, §§3, 5 e 7.6](https://arxiv.org/html/2606.29018v2). Contraexemplo: N cópias da mesma aposta dão soma NR e variância N²Var(R), sem qualquer impacto adicional. Confundir isso com perda superlinear fabricaria confirmação.

**NICE-TO-HAVE**
D-P15 deve distinguir lacunas de coleta de mudanças reais e incluir 8 h↔4 h. `fundingInfo` lista ajustes atuais de teto/piso/intervalo; não reconstrói os 90 dias nem representa automaticamente o universo do Lab. [Binance](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-Info).

**O QUE EU FARIA DIFERENTE**
Na D-P14, reportaria **fronteira de equilíbrio: maior custo suportável**, com intervalo de confiança, cobertura e “nenhuma célula positiva” quando aplicável. Fixaria spread e evitaria contá-lo novamente no slippage; mudar preços de entrada exige revalidar geometria, não apenas descontar bps.
A grade proposta começa em taxa de 4 bp: não testa maker de 2 bp. Acrescentar essa célula seria sensibilidade econômica; viabilidade maker exige estudar preenchimento, fila e seleção adversa.
Na redundância, priorizaria H-P13 com orçamento agregado de risco igual e ocupação completa; regressão de R contra número de versões seria apenas associação.

**CONCORDO COM**
Zeng justifica auditar dados e custos, não condenar toda reversão: são **23 execuções ×20 células**, dependentes, e não 460 replicações independentes. O holdout é retrospectivo; disponibilidade do funding usa hipótese de atraso, não timestamp comprovado. [Zeng et al., §§5–7](https://arxiv.org/html/2608.25348).
Retirar os “três regimes” foi correto. O episódio PPI/BTC merece registro de evento, mas coincidência temporal não identifica causalidade.
**KB-0085 merece existir sem medição própria**, como nota crítica de teoria externa e protocolo ainda não testado; não como classificador validado no Hunter nem sustentação empírica de N².

**OBSIDIAN**

- **KB-0085 — Auditoria de liquidez:** registrar hipóteses do teorema, definição temporal de c/π e limites da interpretação.
- **Hipóteses do plantão:** reformular D-P13–15, ordenar D-P15→14→13 e retirar a previsão N² para R.
- **KB-0083 — Uma hora de −34 R:** distinguir duplicação de exposição, variância e impacto de mercado.
- **Plantão/2026-09-10:** incorporar correções de cadência, fronteira de custo e alcance dos estudos.