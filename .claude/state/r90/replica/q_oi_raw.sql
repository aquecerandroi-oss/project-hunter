-- R90 réplica — export CRU de open_interest_history dos mercados da momentum elegível (sem agregação, sem desfecho).
BEGIN READ ONLY;
SET LOCAL statement_timeout='300s';
COPY (SELECT market_id, ts, open_interest FROM open_interest_history
      WHERE market_id IN ('01a073bb-9bab-7704-b083-6ce85d7b72ad','01a073bb-9bac-72b1-a560-acda32ff5816','01a073bb-9bae-7d9c-9f80-68983761b3c8','01a073bb-9bb2-76e1-bdba-ee95a3cfbb45','01a073bb-9bb6-7f75-8666-2790fcaf7fd9','01a073bb-9bb7-72ad-9c9b-63f84a60f8fd','01a073bb-9bb9-7fcf-9bdf-fd974c9c35e1','01a073bb-9bc8-7290-abcd-1c2440bf9eff','01a073bb-9bd4-7e13-9813-3acbc5b927fc','01a073bb-9bd5-7390-808e-95f403dd0a9d','01a073bb-9bd9-73d2-b14b-3222b61e78ce','01a073bb-9c23-7327-9007-6d5e421dc1f3','01a073bb-9c29-7ae1-ac44-adc1632b76d2','01a073bb-9c6e-7291-bb17-5d3c9abbb350','01a073bb-9cbc-777a-b9d6-5dec1c0dbcf0') AND ts >= '2026-09-05' AND ts < '2026-10-06' ORDER BY market_id, ts)
TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
