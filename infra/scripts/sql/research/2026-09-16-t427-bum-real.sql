\pset format aligned
-- T4.27 — "bum real": SOL DE VERDADE na curva (real_sol_reserves), moedas nao-Mayhem, ultimos 3 dias.
-- Nunca mcap_sol: numa moeda Mayhem o agente empurra a reserva virtual sem SOL entrar (KAT, 15/09 17:37 BRT,
-- 23,9 -> 1 977 SOL virtuais em 60 s com 5 holders). O SOL real e o teto do que pode sair da curva.
--
-- Leitura obrigatoria antes dos numeros: a curva GRADUA quando o SOL real chega ao limiar do registro
-- /global-params (85,005 SOL no registro de 2025-07-18; meme_tokens.curve_filled_seen_at), e dali o SOL vai
-- para a pool. Portanto 100 / 300 / 1 000 SOL de real_sol_reserves NAO EXISTEM numa curva (as tres colunas
-- abaixo devem ler 0 — se lerem > 0 e uma leitura errada de reserva, nao um bum). Os patamares que existem
-- sao 10 / 30 / 60 SOL e "encheu" (>= limiar). Equivalentes TEORICOS numa curva padrao (30 SOL virtuais +
-- real; k = 30 x 1,073 bi): 10 SOL reais ~ 50 SOL de mcap, 30 ~ 112, 60 ~ 252, cheia (85) ~ 411.
--
-- Populacao: meme_tokens com created_at nos ultimos 3 dias e coalesce(mayhem_enabled, false) = false
-- (a mesma convencao do 2026-09-16-t427-bum-real-sem-mayhem.sql; a coluna flag_desconhecido diz quantos
-- desses "bums" nunca tiveram o bit lido na cadeia — o denominador e visivel, nao escondido).

-- 1. Quantos bums reais ha (3 dias), em quanto tempo, quantos graduaram, quantos o Lab viu.
with nm as (
  select t.mint, t.symbol, t.created_at, t.completed_at, t.curve_filled_seen_at, t.mayhem_enabled
  from meme_tokens t
  where t.created_at >= now() - interval '3 days' and coalesce(t.mayhem_enabled, false) = false
), r as (
  select nm.*,
    max(cs.real_sol_reserves) as peak_real_sol,
    min(cs.observed_at) filter (where cs.real_sol_reserves >= 10)   as at_10,
    min(cs.observed_at) filter (where cs.real_sol_reserves >= 30)   as at_30,
    min(cs.observed_at) filter (where cs.real_sol_reserves >= 60)   as at_60,
    min(cs.observed_at) filter (where cs.real_sol_reserves >= 100)  as at_100,
    min(cs.observed_at) filter (where cs.real_sol_reserves >= 300)  as at_300,
    min(cs.observed_at) filter (where cs.real_sol_reserves >= 1000) as at_1000
  from nm join meme_curve_snapshots cs on cs.mint = nm.mint
  group by nm.mint, nm.symbol, nm.created_at, nm.completed_at, nm.curve_filled_seen_at, nm.mayhem_enabled
)
select count(*) as nao_mayhem_com_fotos,
  count(*) filter (where mayhem_enabled is null) as flag_desconhecido,
  count(*) filter (where peak_real_sol >= 10)   as passou_10_sol,
  count(*) filter (where peak_real_sol >= 30)   as passou_30_sol,
  count(*) filter (where peak_real_sol >= 60)   as passou_60_sol,
  count(*) filter (where curve_filled_seen_at is not null) as encheu_a_curva,
  count(*) filter (where peak_real_sol >= 100)  as passou_100_sol_impossivel,
  count(*) filter (where peak_real_sol >= 300)  as passou_300_sol_impossivel,
  count(*) filter (where peak_real_sol >= 1000) as passou_1000_sol_impossivel,
  count(*) filter (where completed_at is not null) as graduou,
  round(percentile_cont(0.5) within group (order by extract(epoch from (at_10 - created_at)) / 60)
        filter (where at_10 is not null)) as mediana_min_ate_10sol,
  round(percentile_cont(0.5) within group (order by extract(epoch from (at_30 - created_at)) / 60)
        filter (where at_30 is not null)) as mediana_min_ate_30sol,
  round(percentile_cont(0.5) within group (order by extract(epoch from (at_60 - created_at)) / 60)
        filter (where at_60 is not null)) as mediana_min_ate_60sol,
  count(*) filter (where at_30 is not null and at_30 - created_at >= interval '3 minutes')  as a_30_depois_de_3min,
  count(*) filter (where at_30 is not null and at_30 - created_at >= interval '10 minutes') as a_30_depois_de_10min,
  count(*) filter (where at_30 is not null and at_30 - created_at >= interval '3 minutes'
                     and exists (select 1 from meme_proposals p where p.mint = r.mint)) as lentas_lab_propos,
  count(*) filter (where at_30 is not null and at_30 - created_at >= interval '3 minutes'
                     and exists (select 1 from meme_paper_bets b where b.mint = r.mint)) as lentas_lab_apostou
from r;

-- 2. Por dia (Brasilia): quantos bums reais por dia — a resposta "quantos ha por dia".
with nm as (
  select t.mint, t.created_at from meme_tokens t
  where t.created_at >= now() - interval '3 days' and coalesce(t.mayhem_enabled, false) = false
), r as (
  select nm.mint, nm.created_at,
    max(cs.real_sol_reserves) as peak_real_sol,
    min(cs.observed_at) filter (where cs.real_sol_reserves >= 30) as at_30
  from nm join meme_curve_snapshots cs on cs.mint = nm.mint group by nm.mint, nm.created_at
)
select (created_at at time zone 'America/Sao_Paulo')::date as dia_brt,
  count(*) as moedas,
  count(*) filter (where peak_real_sol >= 10) as passou_10,
  count(*) filter (where peak_real_sol >= 30) as passou_30,
  count(*) filter (where peak_real_sol >= 60) as passou_60,
  count(*) filter (where at_30 is not null and at_30 - created_at >= interval '3 minutes') as lentas_30_apos_3min
from r group by 1 order by 1;

-- 3. A que horas (Brasilia) as lentas cruzam 30 SOL reais — a resposta "a que horas".
with nm as (
  select t.mint, t.created_at from meme_tokens t
  where t.created_at >= now() - interval '3 days' and coalesce(t.mayhem_enabled, false) = false
), r as (
  select nm.mint, nm.created_at, min(cs.observed_at) filter (where cs.real_sol_reserves >= 30) as at_30
  from nm join meme_curve_snapshots cs on cs.mint = nm.mint group by nm.mint, nm.created_at
)
select extract(hour from (at_30 at time zone 'America/Sao_Paulo'))::int as hora_brt,
  count(*) as lentas_cruzando_30sol,
  round(100.0 * count(*) / sum(count(*)) over (), 1) as pct
from r where at_30 is not null and at_30 - created_at >= interval '3 minutes'
group by 1 order by 1;

-- 4. Controle: as moedas Mayhem dos mesmos 3 dias, pelo SOL REAL — o que sobra do "pico" quando se tira o
--    SOL virtual do agente (compare com os 95 picos >= 500 SOL de mcap_sol do 2026-09-16-t427-picos-sao-mayhem.sql).
with mh as (
  select t.mint from meme_tokens t
  where t.created_at >= now() - interval '3 days' and t.mayhem_enabled = true
), r as (
  select mh.mint, max(cs.real_sol_reserves) as peak_real_sol, max(cs.mcap_sol) as peak_mcap_teorico
  from mh join meme_curve_snapshots cs on cs.mint = mh.mint group by mh.mint
)
select count(*) as mayhem_com_fotos,
  count(*) filter (where peak_mcap_teorico >= 500) as pico_mcap_teorico_500,
  count(*) filter (where peak_real_sol >= 10) as passou_10_sol_reais,
  count(*) filter (where peak_real_sol >= 30) as passou_30_sol_reais,
  count(*) filter (where peak_real_sol >= 60) as passou_60_sol_reais,
  round(percentile_cont(0.5) within group (order by peak_real_sol) filter (where peak_mcap_teorico >= 500), 2)
    as mediana_sol_real_dos_picos_500
from r;
