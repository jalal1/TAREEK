# SPDX-License-Identifier: GPL-3.0-or-later
"""Migrate the FHA counts tables to the per-direction schema.

The FHA tables (fha_stations, fha_hourly_volumes) used to store one
bidirectional row per station. They now store one row per (station, travel_dir)
with a travel_dir column and a per-direction primary key. SQLAlchemy's
create_all never alters an existing table, so an old DB keeps the old shape and
per-direction inserts would fail.

This script DROPS the two FHA tables and RECREATES them empty in the new schema.
It does NOT re-ingest: the next `run_experiment.py` run sees the empty tables
(has_data_for_region() == False) and re-ingests FHA data from the zip archives
on demand. Every other table is untouched.

The database location is taken from the SAME config the pipeline uses
(data.data_dir + '/db/trafficsim1.2.duckdb'), so there is exactly one way to run
this and it always targets the pipeline's real DB:

    python scripts/migrate_fha_perdirection.py --config <path/to/config.json>

If the database is not found at that path, the script stops and tells you the
exact path it looked for so you can fix data.data_dir in the config.
"""
import argparse
import json
import sys
from pathlib import Path

# Allow running from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.models import Base, FHAStation, FHAHourlyVolume
from utils.duckdb_manager import DBManager


def main():
    parser = argparse.ArgumentParser(
        description="Drop + recreate the FHA tables in the per-direction schema "
                    "(empty; the next pipeline run re-ingests). The DB path comes "
                    "from the config's data.data_dir."
    )
    parser.add_argument(
        "--config", required=True,
        help="Path to the config JSON the pipeline uses (reads data.data_dir).",
    )
    args = parser.parse_args()

    # --- Resolve the config ------------------------------------------------
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: config file not found: {config_path.resolve()}")
        sys.exit(1)
    with open(config_path) as f:
        config = json.load(f)

    try:
        data_dir = config["data"]["data_dir"]
    except KeyError:
        print(f"ERROR: '{config_path}' has no data.data_dir setting.")
        sys.exit(1)

    db_path = Path(data_dir) / "db" / "trafficsim1.2.duckdb"

    # --- Locate the database, loudly -------------------------------------
    print(f"Config:        {config_path.resolve()}")
    print(f"data.data_dir: {data_dir}")
    print(f"Database path: {db_path.resolve()}")
    if db_path.exists():
        size_mb = db_path.stat().st_size / 1024 / 1024
        print(f"DATABASE FOUND ({size_mb:.1f} MB). Proceeding.\n")
    else:
        print("DATABASE NOT FOUND at the path above.")
        print("  The data.data_dir in your config does not point at an existing")
        print("  database. Fix data.data_dir in the config so it resolves to the")
        print("  directory that contains 'db/trafficsim1.2.duckdb', then re-run.")
        print("  (Relative data_dir values are resolved from the current working")
        print(f"   directory: {Path.cwd()})")
        print("  Refusing to create an empty database.")
        sys.exit(1)

    db = DBManager(data_dir)

    # --- Report current schema -------------------------------------------
    for table in ("fha_stations", "fha_hourly_volumes"):
        cols = db.get_table_columns(table)
        if not cols:
            print(f"  {table}: does not exist (will be created)")
        elif "travel_dir" in cols:
            print(f"  {table}: already per-direction (has travel_dir) — will be rebuilt empty")
        else:
            print(f"  {table}: OLD schema (no travel_dir) — will be dropped + recreated")

    # --- Drop + recreate empty in the new schema -------------------------
    print("Dropping FHA tables...")
    db.drop_table(FHAHourlyVolume)
    db.drop_table(FHAStation)

    print("Recreating FHA tables (empty) in the new schema...")
    with db.write_engine_scope() as engine:
        Base.metadata.create_all(engine)

    # --- Verify ----------------------------------------------------------
    for table in ("fha_stations", "fha_hourly_volumes"):
        cols = db.get_table_columns(table)
        ok = "travel_dir" in cols
        print(f"  {table}: {'OK (travel_dir present)' if ok else 'ERROR — travel_dir missing'}")
        if not ok:
            print("Migration failed to create the new schema.")
            sys.exit(1)

    print("\nDone. The FHA tables are empty in the per-direction schema. "
          "The next run_experiment.py run will re-ingest FHA data from the "
          "zip archives on demand.")


if __name__ == "__main__":
    main()
