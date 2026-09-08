# Revisão quantitativa do commit 9a56e37 (T3.18b) — quant-engineer, 2026-09-08 (resumo fiel; veredito: aprovar com ressalvas)

1. Vazamento replay → veredito/maturidade: não encontrado (rows_for prospective, versions_with_signals prospective, parent_outcomes prospective, curva default prospective). Ressalva de apresentação: replication.status (pode vir de replay) ao lado de verdict (nunca) — o cartão tem de rotular.
2. Definições SQL replay × prospectivo: idênticas (is_evaluable, rate, expectancy, profit_factor reutilizados). Divergência real em replication.parent: repositories/lab_replication.py:107 sem o portão de horizonte is_evaluable; PopulationStats.days conta dias de decisão (placar: dias de saída); PF só-perdas: placar 0.0000/None, replicação None/sem_ganhos (SHADOW-LAB §19 manda "sem perdas" como único motivo nulo). O mesmo JSON pode publicar verdict reprovada e parent.verdict inconclusivo.
3. Adaptador: desvio 1 (pai em prospective) e 2 (irmãs pelas colunas 0012) corretos; desvio 3 não declarado: order_by(emitted_at) sem id — bootstrap reamostra por índice; IC medido diferente com a mesma semente ao permutar empates (replay tem empates garantidos: replay/environment.py:86). Fix: (emitted_at, id).
4. resolve_seed() fallback: estatisticamente aceitável (determinístico, antes da amostra); contrato ruim: payload não diz se a semente foi registrada ou derivada → seed_source; ler a semente do evento strategy_version_replicated.
5. refutada com rodada incompleta é defeito: protocol.py:153/169 usa total=len(arms); 6 irmãs perfeitas → "refutada: 0 negativas". Fix: pool = max(total, expected); passed=None "rodada incompleta" até expected.
6. replay_runs_summary ignora as_of (repositories/lab_scoreboard.py:182).
7. outcomes=[*live,*replay] sem dedup nem janela declarada (repositories/lab_replication.py:181); REPLICATION.md §3.5 item 4 exige rótulo "siblings: replay sobre <janela>".
8. Custo: N+1 (~5 consultas/versão + 2/irmã); replication_report roda halves+bootstrap mesmo com promising_at None e descarta; COHORT LIKE replay:% sem índice.
9. decisions_simulated = SUM(bars_evaluated) inclui barras sem decisão (unavailable/ineligible) — D14 pede decisão registrada; publicar evaluations_by_state.
10. CurveOut não ecoa cohort; coringa replay soma corridas sobrepostas duas vezes.
11. Teste-prova fraco (prospectivo imaturo → inconclusivo de qualquer jeito); usar maduro negativo × replay positivo; _sibling reimplementa a regra de evidence.
12. ensure_utc ausente em repositories/lab_replication.py:135.
13. Irmã promovida a viva perde a evidência prospectiva (:167-181).
Saídas: 936 passed (unit + indicators), 424 passed (api unit).
