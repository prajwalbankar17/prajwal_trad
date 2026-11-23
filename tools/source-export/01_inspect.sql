-- =====================================================================
-- 01_inspect.sql  -  FAST, metadata only.  Safe on a 185 GB cluster.
--
-- Nothing here scans a large table.  Every number about row counts is a
-- PLANNER ESTIMATE from pg_class/pg_stats, not a real COUNT(*), because a
-- real count on a 185 GB candles table would read every page on disk.
--
-- Run:
--   psql -p 5433 -U postgres -d <dbname> -f 01_inspect.sql > inspect_out.txt
--
-- Errors here are not fatal: ON_ERROR_STOP is deliberately OFF, so if a
-- table is named something other than `candles` / `instruments`, the
-- sections above it have already told you the real names.
-- =====================================================================

\echo '=== 1. SERVER VERSION AND BUILD TARGET ==='
SELECT version();

\echo ''
\echo '=== 2. DATABASES IN THIS CLUSTER ==='
SELECT datname,
       pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
WHERE datistemplate = false
ORDER BY pg_database_size(datname) DESC;

\echo ''
\echo '=== 3. TABLES IN THE CURRENT DATABASE ==='
SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name;

\echo ''
\echo '=== 4. TABLE SIZES AND ESTIMATED ROW COUNTS (no scan) ==='
SELECT c.relname,
       c.reltuples::bigint AS estimated_rows,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(c.oid) DESC;

\echo ''
\echo '=== 5. EVERY COLUMN OF EVERY USER TABLE ==='
SELECT table_name, ordinal_position, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_name, ordinal_position;

\echo ''
\echo '=== 6. TIMEFRAME VALUES FROM STATISTICS (instant, no scan) ==='
\echo '--- If this is empty, run ANALYZE candles; first (that WILL take a while).'
SELECT tablename, attname, n_distinct, most_common_vals, most_common_freqs
FROM pg_stats
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
  AND attname IN ('timeframe', 'series', 'exchange', 'segment')
ORDER BY tablename, attname;

\echo ''
\echo '=== 7. SAMPLE ROWS - instruments ==='
SELECT * FROM instruments LIMIT 10;

\echo ''
\echo '=== 8. SAMPLE ROWS - candles ==='
SELECT * FROM candles LIMIT 5;

\echo ''
\echo '=== 9. INDEXES (decides which queries are fast) ==='
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY tablename, indexname;

\echo ''
\echo '=== 10. PARTITIONS, IF THE CANDLES TABLE IS PARTITIONED ==='
SELECT parent.relname AS parent, child.relname AS partition,
       pg_size_pretty(pg_total_relation_size(child.oid)) AS size
FROM pg_inherits i
JOIN pg_class parent ON parent.oid = i.inhparent
JOIN pg_class child  ON child.oid  = i.inhrelid
ORDER BY parent.relname, child.relname;
