\pset format unaligned
\pset tuples_only on
select v.version||' -> '||v.default_parameters::text from strategy_versions v join strategies s on s.id=v.strategy_id where s.key='mean_reversion' order by v.version;
