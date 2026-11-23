# Getting the historical data off the Drive backup (Windows)

The 185 GB `pgsql` folder on Google Drive is a **PostgreSQL 17 data
directory**, not a file you can open. To get data out of it you have to start
a PostgreSQL server that points at it, then run read-only queries.

This folder holds the scripts for that. Run them on the **Windows** machine.

> **Your data is never modified.** Every query in these scripts is a `SELECT`.
> But note that *starting* a PostgreSQL server always writes to its own data
> directory (WAL, crash recovery, hint bits). So work on the **downloaded
> copy** and leave the Drive original untouched as your backup.

---

## Before you start

| What you need | Why |
|---|---|
| ~200 GB free on one drive | 185 GB for the cluster, plus room for the exports |
| PostgreSQL **17.x** for Windows | A PG 16 server cannot read a PG 17 data directory |
| A few hours | The download is the slow part |

Check your free space first — PowerShell:

```powershell
Get-PSDrive -PSProvider FileSystem | Select-Object Name,@{n='FreeGB';e={[math]::Round($_.Free/1GB,1)}}
```

If no drive has ~200 GB free, stop here and tell me — the plan changes.

---

## Step 1 — Install PostgreSQL 17

Download the Windows installer from
<https://www.enterprisedb.com/downloads/postgres-postgresql-downloads> and pick
a **17.x** version.

During install it creates its own empty data directory. That is fine and we
will not touch it — we start a *second* server on a different port instead.

Confirm it installed:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe" --version
```

It must print `pg_ctl (PostgreSQL) 17.x`. If it prints 16 or 18, the cluster
will not start.

---

## Step 2 — Download the folder from Drive

Download `Indian Market Data/pgsql` to a path **with no spaces in it**, for
example `D:\pgsql`. Spaces in a data directory path cause avoidable trouble
with the Windows service tooling.

Easiest route: install **Google Drive for Desktop**, right-click the `pgsql`
folder, choose *Available offline*, and let it finish. It resumes by itself if
the connection drops.

When it is done you should have:

```
D:\pgsql\data\     <- the cluster
D:\pgsql\log\      <- the old server logs
```

**Verify the download actually completed** before going on. A partial data
directory will fail in confusing ways:

```powershell
(Get-ChildItem D:\pgsql\data -Recurse -File | Measure-Object Length -Sum).Sum / 1GB
```

That number should be close to the size Drive reports for the folder. If it is
noticeably smaller, the download is not finished.

---

## Step 3 — Clear a stale lock file

The cluster was copied while it may have been running, so it can carry a lock
file from the old machine. If it is there, delete it — it refers to a process
ID on a computer that is not this one:

```powershell
Remove-Item D:\pgsql\data\postmaster.pid -ErrorAction SilentlyContinue
```

---

## Step 4 — Let yourself log in

The cluster keeps its own users and passwords, which you probably do not have.
Open `D:\pgsql\data\pg_hba.conf` in Notepad and change the method column of
every uncommented line to `trust`:

```
host    all    all    127.0.0.1/32    trust
host    all    all    ::1/128         trust
```

`trust` means "no password for local connections". It is fine here because the
server only listens on this machine and only for as long as you are exporting.
Change it back when you are done if you keep the copy around.

---

## Step 5 — Start the server

Open PowerShell as your **normal user**. Do *not* use "Run as administrator" —
PostgreSQL refuses to start under an elevated account.

```powershell
& "C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe" -D "D:\pgsql\data" -o "-p 5433" -l "D:\pgsql\startup.log" start
```

Port 5433 keeps this separate from the PostgreSQL you just installed.

Now **read the log** — do not assume it worked:

```powershell
Get-Content D:\pgsql\startup.log -Tail 30
```

You want a line ending in `database system is ready to accept connections`.

If instead you see:

- `incompatible version` → the installed PostgreSQL is not 17.x
- `incorrect checksum` / `invalid page` → the download is corrupt or incomplete
- `could not open ... permission denied` → right-click `D:\pgsql`, Properties,
  Security, and give your user Full control

---

## Step 6 — Find the database name

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -p 5433 -U postgres -l
```

Pick the one that is not `postgres`, `template0` or `template1`. That name goes
in place of `<dbname>` below.

---

## Step 7 — Inspect (fast, safe)

Copy this folder's `.sql` files to `D:\pgsql\`, then:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -p 5433 -U postgres -d <dbname> -f D:\pgsql\01_inspect.sql > D:\pgsql\inspect_out.txt
```

This reads only catalog metadata, so it finishes in seconds even on 185 GB.

**Send me `inspect_out.txt`.** It is a small text file and it tells me the real
table names, the real column types, and the real timeframe labels — so I can
write the importer against what is actually there instead of guessing.

---

## Step 8 — Export the subset

Create the output folder first:

```powershell
New-Item -ItemType Directory -Force -Path D:\export
```

Open `03_export.sql` in Notepad. Two lines are marked `<<< EDIT` — replace
`'1d'` in **both** with the label the inspect output showed for end-of-day
candles.

Edit the label by hand in those lines; do not try to use a psql variable. A
`\copy` line does not expand variables, so a variable there silently writes an
empty file and still reports success. (Found and fixed while testing these
scripts.) Then:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -p 5433 -U postgres -d <dbname> -f D:\pgsql\03_export.sql
```

Check what came out:

```powershell
Get-ChildItem D:\export | Select-Object Name,@{n='MB';e={[math]::Round($_.Length/1MB,1)}}
```

`instruments.csv` should be a few MB and `daily_candles.csv` roughly 1–3 GB. If
either is empty, the timeframe label is wrong — fix it and run again.

---

## Step 9 — Stop the server

```powershell
& "C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe" -D "D:\pgsql\data" stop
```

---

## Step 10 — Send the exports over

Put `instruments.csv` and `daily_candles.csv` back on Google Drive (or a USB
disk) so they can be copied to the Mac where the platform runs. Together they
are a few GB, which fits in the free space there.

Intraday (`1m`) candles come later, and only for the handful of symbols the
backtest actually selects — that keeps it to about 1 GB instead of 185.

---

## What happens next

On the Mac I will:

1. Read `inspect_out.txt` and write a real importer for your actual schema
2. Load instruments and daily candles into the platform database
3. Have the platform pick stocks from that real data — not a hardcoded list
4. Split ₹1,00,000 across them and run the full pipeline end to end
5. Apply real Indian transaction costs and report the net result, win or lose

## The optional slow one

`02_stats.sql` gives exact row counts and date ranges per timeframe, and checks
for impossible candles (`high < low` and similar). It reads every row, so on
185 GB it can take minutes or hours. It is read-only and safe to interrupt with
Ctrl+C. Run it only if you want the exact picture.
