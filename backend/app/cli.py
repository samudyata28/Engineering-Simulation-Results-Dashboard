"""python -m app.cli import | seed-demands"""
from __future__ import annotations

import argparse
import sys

from .config import get_settings
from .db import init_db, make_engine, make_session_factory
from .services import demands, importer


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="app.cli")
    ap.add_argument("command", choices=["import", "seed-demands"])
    args = ap.parse_args(argv)
    s = get_settings()
    engine = make_engine(s.database_url)
    init_db(engine)
    with make_session_factory(engine)() as db:
        if args.command == "import":
            rep = importer.sync(db, s, trigger="cli")
            print(f"created={rep.created} updated={rep.updated} unchanged={rep.unchanged} failed={rep.failed} missing={rep.missing}")
            from .models import ImportIssue
            for i in db.query(ImportIssue).filter(ImportIssue.run_id == rep.run_id):
                print(f"  [{i.severity}] {i.path}: {i.message}")
            return 1 if rep.failed else 0
        made = demands.seed_rev1_demands(db)
        print(f"created {len(made)} demand(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
