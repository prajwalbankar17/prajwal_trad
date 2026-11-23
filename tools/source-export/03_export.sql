-- =====================================================================
-- 03_export.sql  -  Pull out a SMALL subset to carry to the Mac.
--
-- READ-ONLY.  Every statement here is a SELECT.  Your source database is
-- not modified in any way.
--
-- Run:
--   psql -p 5433 -U postgres -d <dbname> -f D:\pgsql\03_export.sql
--
-- ---------------------------------------------------------------------
-- YOU MUST EDIT THE TIMEFRAME LABEL BELOW, BY HAND.  Marked  <<< EDIT.
--
-- psql does NOT substitute \set variables inside a \copy line - it passes
-- the text through literally.  So the label has to be typed directly into
-- the \copy command.  Using a variable there produces an EMPTY csv file
-- and no obvious error, which is why this script spells it out instead.
-- =====================================================================

\echo '=== Step 1: does the daily timeframe label actually exist? ==='
\echo '--- Stops at the first matching row, so it is fast even on 185 GB.'
\echo '--- If this prints (0 rows), your label is WRONG.  Stop and fix it.'

SELECT * FROM candles WHERE timeframe = '1d' LIMIT 1;    -- <<< EDIT the label

\echo ''
\echo '=== Step 2: exporting instruments ==='

\copy (SELECT * FROM instruments) TO 'D:/export/instruments.csv' CSV HEADER

\echo ''
\echo '=== Step 3: exporting daily candles ==='
\echo '--- This one takes a while.  It is reading real data.'

\copy (SELECT * FROM candles WHERE timeframe = '1d') TO 'D:/export/daily_candles.csv' CSV HEADER    -- <<< EDIT the label

\echo ''
\echo '=== Done - now VERIFY, do not assume ==='
\echo '    instruments.csv    expect a few MB'
\echo '    daily_candles.csv  expect roughly 1-3 GB'
\echo ''
\echo 'A csv of 0 bytes, or one holding only a header line, means the'
\echo 'timeframe label did not match anything.  The command will still'
\echo 'have reported success.  Check the file sizes yourself.'
