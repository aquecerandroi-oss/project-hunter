# notes-T4.28e — o estágio 1 recusava tudo por `progress_below_window` (unidade do denominador) + o cap por hora contava recusas

**Quando:** 16/09/2026, 11:46–12:2x BRT. **Quem:** Sexta-feira (à mão; o T4.28d rodava em paralelo em outros arquivos).

## O fato medido (VPS, executor `hunter-api:9f828dd`, primeiro dia com `MEME_LIVE=1`)
- 11:46:36, 11:46:55, 11:47:18, 11:47:55 BRT: quatro `meme_live_auto_approved` no mesmo mint (`FHcHh1…`, INCEPT, criado 11:43:56),
  quatro `meme_live_entry_refused` com `progress_below_window`. `admission.checks.curve_progress`: `value = −541546.79…`, `limit = 0.02`.
- Causa: `meme_tokens.initial_real_token_reserves` está em **tokens** (793 100 000; 100 654 linhas, máx. 800,9 M, nenhuma > 1e12) e
  `CurveState.real_token_reserves` (leitura RPC da curva) está em **subunidades** (6 casas). `(793,1e6 − 4,29e14) / 793,1e6 ≈ −5,4e5`.
  Toda moeda seria recusada; o estágio 1 nunca compraria.
- Efeito colateral: `hb:meme:executor.auto_approved_1h = 4` — o cap de 5 por hora (`MEME_LIVE_AUTO_APPROVE_MAX_PER_HOUR`) contava
  as propostas abertas pelo robô mesmo quando a admissão recusou (a proposta fica `rejected`). Everton, 12:1x BRT: "porque robô tá com
  rate limit, não quero isso".

## O que mudou
- `admission.py`: `denominator_subunits()` converte o denominador para subunidades (`TOKEN_SUBUNITS_PER_TOKEN` do adaptador) ao montar o
  `MemeContext`; `None`/≤ 0 continua `None` → `progress_denominator_missing`.
- `auto_approve.py`: `_APPROVED_LAST_HOUR` conta só `status <> 'rejected'`; docstring do módulo atualizada. No estágio 1 o cap (5) passa a
  ser igual ao `max_trades` do escopo e nunca trava antes dele.
- `tests/test_live_persistence.py`: fixture do `TokenContext` passa a usar a unidade real do banco (793 100 000 tokens).
- `tests/test_admission_units.py`: regressão — conversão, janela 2–50 % com números reais de curva, ausência.
- Docs: `RISK_ENGINE_MEME.md` §3.1 (unidade) e §3.5 (cap conta só admitidas); `ACTIVATION.md` §9b.

## Fora deste hotfix (fila)
- Dedupe entre tiques: a mesa repropõe o mesmo mint a cada ~20 s; o robô abre e a admissão recusa de novo (uma leitura RPC + uma linha
  `refused` por vez). Não custa dinheiro; custa ruído. Candidato: pular mint com recusa determinística nos últimos N min.
- `wallet_unrecognized_holdings` nunca é preenchido (o executor não lê as contas de token da carteira). A carteira do robô tem 21,33 USDC
  parados (depósito errado do Everton, 11:35 BRT) e isso hoje não bloqueia — se um dia for preenchido, USDC/WSOL precisam de allowlist.
- T4.28d (recarga dos portões): edição não atômica (`nano`) pode ser lida no meio e travar o switch com `gates_invalid:gates_file_invalid`;
  o doc manda `mv`/`sed -i`. Uma tolerância de um tique removeria o risco.
