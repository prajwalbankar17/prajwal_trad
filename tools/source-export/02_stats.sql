-- =====================================================================
-- 02_stats.sql  -  SLOW.  These queries read real data.
--
-- Run this ONLY after 01_inspect.sql, and only if you have time: on a
-- 185 GB table a GROUP BY over every row can take from several minutes
-- to several hours depending on the disk.
--
-- \timing is on so you can see what each one actually cost.
-- If a query is still running after ~15 minutes, press Ctrl+C.  Nothing
-- is written and nothing is damaged: these are read-only SELECTs.
--
-- Run:
--   psql -p 5433 -U postgres -d <dbname> -f 02_stats.sql > stats_out.txt
-- =====================================================================

\timing on

\echo '=== A. ROWS AND DATE RANGE PER TIMEFRAME (full scan) ==='
SELECT timeframe,
       count(*)           AS rows,
       min(timestamp)     AS first_ts,
       max(timestamp)     AS last_ts,
       count(DISTINCT instrument_id) AS instruments
FROM candles
GROUP BY timeframe
ORDER BY timeframe;

\echo ''
\echo '=== B. HOW MANY INSTRUMENTS, BY SERIES ==='
SELECT series, count(*) AS instruments
FROM instruments
GROUP BY series
ORDER BY count(*) DESC;

\echo ''
\echo '=== C. ARE THERE NULLS WHERE WE NEED VALUES? ==='
SELECT count(*) FILTER (WHERE open  IS NULL) AS null_open,
       count(*) FILTER (WHERE high  IS NULL) AS null_high,
       count(*) FILTER (WHERE low   IS NULL) AS null_low,
       count(*) FILTER (WHERE close IS NULL) AS null_close,
       count(*) FILTER (WHERE volume IS NULL) AS null_volume,
       count(*) FILTER (WHERE open_interest IS NULL) AS null_oi
FROM candles;

\echo ''
\echo '=== D. SANITY: ANY IMPOSSIBLE CANDLES? ==='
\echo '--- high < low, or close outside the high/low band, means bad source data.'
SELECT count(*) AS broken_candles
FROM candles
WHERE high < low
   OR close > high OR close < low
   OR open  > high OR open  < low;
