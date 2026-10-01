SET statement_timeout='60s';
\d candles_1m
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='agent_signals' ORDER BY ordinal_position;
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='signal_outcomes' ORDER BY ordinal_position;
