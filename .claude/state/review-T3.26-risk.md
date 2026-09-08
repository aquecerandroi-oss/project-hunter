# Revisão risk-engine-guardian do commit be3674a (T3.26) — 2026-09-08 — veredito: aprovar com ressalvas (nada abre caminho para a carteira)

Travas verificadas: INSERT crava purpose=research_only (derive_variant.py:272); --set só aceita nomes do schema (:130); pai research_only congelado (:229-236); purpose congelado pela trigger 0010 e UPDATE revogado; ponte recusa research_only e coorte != prospective (bridge_screen.py:269/273) e exige linha em agents (bridge_repo.py:124-127); admissão recusa purpose != paper (sources.py:262-273). Nenhum código de produção cria linha em agents.

A1 (ALTA) activate_strategy_version.py:142 — a rota _DERIVED depende de "derived_from=v<n>" no changelog (coluna não congelada). A imagem da VPS anterior a be3674a usa startswith("paper line of") → derivar+ativar pelo runbook (docs/ACTIVATION.md:37, script da imagem) cai na rota de pesquisa, reescreve default_parameters do código e apaga o override em silêncio; um UPDATE manual no changelog também derruba a rota. Correção estrutural: a rota de pesquisa recusa rascunho com default_parameters não vazio e diferente do canônico do código.

A2 (MÉDIA) derive_variant.py:140 — valida forma/presença, não faixa (schema.py:10-16 reservava isso para o M4). Probe: atr_pct_min=-0.5, stop_atr=0/-2, target_atr=-1.5, rvol_min=-999999, lookback_closes=-20, horizon_s=-3600, fee_bps=-100, base_confidence=42, piso>teto — todos ACEITOS. fee_bps/slippage_bps/assumed_spread_bps entram no sizing (hunter_risk/sizing.py:227-238); backstops seguram (AssumedCosts ge=0 envelope.py:69-72; EntryProposal stop>=entry sources.py:255; check 8 checks.py:252) → dano é de pesquisa (versão congelada que levanta exceção a cada barra), não de carteira.

A3 (MÉDIA) consumer.py:123 — loop por versão sem try/except: uma versão com exceção aborta handle_candle, sem ack; load_version_roster ordena versão como texto (catalogue.py:280): v10 antes de v3 → variante quebrada avaliada antes da linha paper, que para em silêncio.

A4 (BAIXA) activate_derived.py:97-100 — evento de ativação grava a nota do operador, sem pai/params_hash/changelog preservado.

A5 (BAIXA) obsidian_strategy_pages.py:105-110 — _SUCCEEDS_RE antes de _DERIVED_FROM_RE pode inventar pai errado.

Indireta: ENTRY_WINDOW=120 s a partir de source_bar_close (bridge_repo.py:38/:110) — terceira versão ativa em 200+ mercados pode atrasar a emissão de v3; acompanhar hunter_bridge_candidates_total{outcome="entry_window_closed"}; strategy-worker não tem histograma bar_close→emitted_at.

Política (D10): uma variante derivada de volume_anomaly (sem linha paper) poderia virar coorte paper amanhã sem evidência prospectiva — decisão do Everton.

Saídas: 32 passed (lineage + obsidian pages); 86 passed/9 errors testcontainers (sem Docker por instrução); ruff limpo.
