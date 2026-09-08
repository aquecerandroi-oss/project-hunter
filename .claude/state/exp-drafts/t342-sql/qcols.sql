\pset border 2
select column_name, data_type from information_schema.columns where table_name='strategy_versions' order by ordinal_position;
