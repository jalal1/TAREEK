# SPDX-License-Identifier: GPL-3.0-or-later
"""Delete a single GTFS feed from the database (for testing/benchmarking loads).

Removes the feed's rows across every GTFS table so the next pipeline run will
re-ingest it from the raw text files instead of skipping (cache hit).

Usage:
    python scripts/delete_gtfs_feed.py <feed_id> [--config config/config_local.json]

Example:
    python e:\projects\Tareek\scripts\delete_gtfs_feed.py mdb-205 --data-dir E:\projects\Tareek\data\db
"""
import argparse
import json
import sys
from pathlib import Path

# Allow running from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from utils.duckdb_manager import DBManager
from models.models import (
    GTFSFeed, GTFSRoute, GTFSStop, GTFSStopRoute, GTFSStopTime, GTFSTrip,
)


def main():
    parser = argparse.ArgumentParser(description="Delete a GTFS feed from the DB.")
    parser.add_argument("feed_id", help="Feed id to delete, e.g. mdb-205")
    parser.add_argument(
        "--config", default="config/config_local.json",
        help="Path to config JSON (for data_dir). Default: config/config_local.json",
    )
    parser.add_argument(
        "--data-dir", default=None,
        help="Override data_dir directly (the dir containing 'db/trafficsim1.2.duckdb'). "
             "Bypasses the config so you don't depend on the working directory.",
    )
    args = parser.parse_args()

    if args.data_dir:
        data_dir = args.data_dir
    else:
        with open(args.config) as f:
            config = json.load(f)
        data_dir = config["data"]["data_dir"]

    db_path = Path(data_dir) / "db" / "trafficsim1.2.duckdb"
    print(f"Using database: {db_path.resolve()}")
    if not db_path.exists():
        print(f"WARNING: no db file at {db_path.resolve()} — wrong data_dir? "
              f"Pass --data-dir explicitly.")

    feed_id = args.feed_id
    db = DBManager(data_dir)

    # Report what's there before deleting.
    before = {
        "gtfs_feeds": len(db.query_all(GTFSFeed, filters={"feed_id": feed_id})),
        "gtfs_routes": len(db.query_all(GTFSRoute, filters={"feed_id": feed_id})),
        "gtfs_stops": len(db.query_all(GTFSStop, filters={"feed_id": feed_id})),
        "gtfs_trips": len(db.query_all(GTFSTrip, filters={"feed_id": feed_id})),
        "gtfs_stop_times": len(db.query_all(GTFSStopTime, filters={"feed_id": feed_id})),
    }
    print(f"Feed '{feed_id}' current row counts:")
    for table, n in before.items():
        print(f"  {table}: {n:,}")

    if before["gtfs_feeds"] == 0:
        print(f"Feed '{feed_id}' is not in the database. Nothing to delete.")
        return

    # gtfs_stop_routes is keyed by stop_pk (-> gtfs_stops.id), not feed_id.
    # Delete it via a subquery, then delete the feed-keyed tables.
    with db.write_session_scope() as session:
        session.execute(
            text(
                "DELETE FROM gtfs_stop_routes WHERE stop_pk IN "
                "(SELECT id FROM gtfs_stops WHERE feed_id = :feed_id)"
            ),
            {"feed_id": feed_id},
        )

    for model in (GTFSStopTime, GTFSTrip, GTFSStop, GTFSRoute, GTFSFeed):
        db.delete_records(model, filters={"feed_id": feed_id})

    print(f"Deleted feed '{feed_id}' from all GTFS tables. Re-run the pipeline to re-ingest.")


if __name__ == "__main__":
    main()
