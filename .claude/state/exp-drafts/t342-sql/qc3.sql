\pset border 2
select column_name from information_schema.columns where table_name='shadow_outbox' order by ordinal_position;
