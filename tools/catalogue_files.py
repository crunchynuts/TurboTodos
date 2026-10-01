"""Optional example: generate generic task-import rows from a folder listing."""
import argparse
import csv
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Create task CSV/JSON from filenames; never reads file contents")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--project", default="", help="Existing project name or ID")
    parser.add_argument("--recursive", action="store_true")
    args = parser.parse_args()
    if not args.folder.is_dir():
        parser.error("Folder does not exist")
    if args.output.suffix.lower() not in {".csv", ".json"}:
        parser.error("Output must end in .csv or .json")
    if args.output.exists():
        parser.error("Output already exists. Choose a new path to avoid overwriting it.")
    files = args.folder.rglob("*") if args.recursive else args.folder.iterdir()
    rows = [{"title": file.name, "tags": args.tag, "project": args.project, "path": str(file.resolve()),
             "source_key": str(file.resolve())} for file in sorted(files) if file.is_file()]
    with args.output.open("x", encoding="utf-8", newline="") as output:
        if args.output.suffix.lower() == ".json":
            json.dump(rows, output, ensure_ascii=False, indent=2)
        else:
            writer = csv.DictWriter(output, fieldnames=["title", "tags", "project", "path", "source_key"])
            writer.writeheader()
            writer.writerows({**row, "tags": "|".join(row["tags"])} for row in rows)
    print(f"Wrote {len(rows)} tasks to {args.output}. Import in batches of at most 5,000 rows.")


if __name__ == "__main__":
    main()
