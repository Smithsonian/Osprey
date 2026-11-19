#!/usr/bin/env python3
"""Compare the folder lists of two Osprey projects that run in parallel.

Project 2 is the dependent project: every folder it has must also exist in
project 1. The script reports:

  * EXTRA  - folders in project 2 that are not in project 1. These break the
             rule, so they make the script exit non-zero.
  * MISSING - folders in project 1 that have not been created in project 2 yet.
             Informational by default; use --strict to fail on these too.
  * IN BOTH - matched folders, with each side's id and file count. Listed with
             --show-matches, and always present in --json output.

The two projects keep their folders in different tables, so the comparison is
asymmetric by default:

             project 1 (folders)   project 2 (transcription_folders)
    name     project_folder        folder
    id       folder_id             folder_transcription_id

Both ids are selected AS folder_id, so the report, CSV and JSON have one shape;
the console detail still names the underlying column it came from.

Use --project1-source / --project2-source to compare two projects of the same
kind. (`folders_transcription` is a similarly named legacy table with no
callers in the app; `transcription_folders` is the live one.)

Folder names come from the database, so this compares what the dashboard
tracks, not what sits on disk.

Run from the `web_app` root, with settings.py configured:

    export PYTHONPATH=.
    python scripts/compare_project_folders.py <project1> <project2>

Each project is named by its `project_alias` or its numeric `project_id`.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from osprey.db import run_query

# Exit codes
EXIT_OK = 0
EXIT_DIFFERENCES = 1
EXIT_ERROR = 2

# Where each kind of project keeps its folders. Queries are built from this
# fixed mapping, keyed by the argparse choices below, so no user input ever
# reaches a table or column name.
SOURCES = {
    "folders": {
        "table": "folders",
        "name_column": "project_folder",
        "id_column": "folder_id",
    },
    "transcription_folders": {
        "table": "transcription_folders",
        "name_column": "folder",
        "id_column": "folder_transcription_id",
    },
}

DEFAULT_SOURCE1 = "folders"
DEFAULT_SOURCE2 = "transcription_folders"


class ProjectNotFound(Exception):
    """Raised when a project alias or id matches no row in `projects`."""


def _supports_color(stream) -> bool:
    return hasattr(stream, "isatty") and stream.isatty()


class Style:
    """ANSI styling, disabled when the output is not a terminal."""

    def __init__(self, enabled: bool):
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return "\033[{}m{}\033[0m".format(code, text) if self.enabled else text

    def red(self, text: str) -> str:
        return self._wrap("1;31", text)

    def yellow(self, text: str) -> str:
        return self._wrap("1;33", text)

    def green(self, text: str) -> str:
        return self._wrap("1;32", text)

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)


def resolve_project(identifier: str) -> dict:
    """Look up a project by numeric project_id or by project_alias."""
    if identifier.isdigit():
        rows = run_query(
            """
            SELECT project_id, project_alias, project_title, transcription
            FROM projects
            WHERE project_id = %(value)s
            """,
            {"value": int(identifier)},
            log_vals=False,
        )
    else:
        rows = run_query(
            """
            SELECT project_id, project_alias, project_title, transcription
            FROM projects
            WHERE project_alias = %(value)s
            """,
            {"value": identifier},
            log_vals=False,
        )
    if not rows:
        raise ProjectNotFound(
            "no project matches {!r} (expected a project_alias or project_id)".format(identifier)
        )
    if len(rows) > 1:
        raise ProjectNotFound(
            "{!r} matches {} projects; use the numeric project_id instead".format(
                identifier, len(rows)
            )
        )
    return rows[0]


def fetch_folders(project_id: int, source: str) -> list[dict]:
    """A project's folder rows, normalized to folder_name/folder_id columns.

    `source` is a key of SOURCES, so the interpolated identifiers are ours.
    """
    spec = SOURCES[source]
    query = """
        SELECT {id_column} AS folder_id,
               {name_column} AS folder_name,
               status, `date`, no_files, delivered_to_dams
        FROM {table}
        WHERE project_id = %(project_id)s
        ORDER BY {name_column}, {id_column}
    """.format(**spec)
    rows = run_query(query, {"project_id": project_id}, log_vals=False)
    return rows or []


def index_folders(rows: list[dict], case_sensitive: bool) -> dict[str, list[dict]]:
    """Map a comparison key to the folder rows carrying that name.

    `folders.project_folder` is nullable and either column can hold stray
    whitespace, so the key is trimmed, and casefolded unless --case-sensitive
    was passed (both columns' utf8mb3_general_ci collation is
    case-insensitive).
    """
    index: dict[str, list[dict]] = {}
    for row in rows:
        name = (row.get("folder_name") or "").strip()
        if not name:
            continue
        key = name if case_sensitive else name.casefold()
        index.setdefault(key, []).append(row)
    return index


def _id_part(row: dict, source: str) -> str:
    """The row's identifier, named by the column it came from."""
    id_column = SOURCES[source]["id_column"]
    # transcription_folders.folder_transcription_id is nullable.
    if row.get("folder_id") is None:
        return "no {}".format(id_column)
    return "{} {}".format(id_column, row["folder_id"])


def describe(row: dict, source: str) -> str:
    """One-line detail for a folder, for the console report."""
    bits = [_id_part(row, source)]
    if row.get("date"):
        bits.append(str(row["date"]))
    if row.get("no_files") is not None:
        bits.append("{} files".format(row["no_files"]))
    return ", ".join(bits)


def label(project: dict, source: str) -> str:
    alias = project.get("project_alias") or "(no alias)"
    return "{} (project_id {}, {})".format(
        alias, project["project_id"], SOURCES[source]["table"]
    )


def compare(
    folders1: dict[str, list[dict]],
    folders2: dict[str, list[dict]],
) -> tuple[list[str], list[str], list[str]]:
    """Return (extra_in_2, missing_in_2, shared) comparison keys, each sorted."""
    keys1 = set(folders1)
    keys2 = set(folders2)
    extra = sorted(keys2 - keys1)
    missing = sorted(keys1 - keys2)
    shared = sorted(keys1 & keys2)
    return extra, missing, shared


def display_name(index: dict[str, list[dict]], key: str) -> str:
    """The folder's name as stored, rather than the normalized key."""
    rows = index.get(key) or []
    if rows:
        return (rows[0].get("folder_name") or "").strip()
    return key


def report(
    project1: dict,
    project2: dict,
    source1: str,
    source2: str,
    index1: dict[str, list[dict]],
    index2: dict[str, list[dict]],
    extra: list[str],
    missing: list[str],
    shared: list[str],
    style: Style,
    show_details: bool,
    show_matches: bool,
) -> None:
    out = sys.stdout
    print(style.bold("Project 1 (reference): {}".format(label(project1, source1))), file=out)
    print(style.bold("Project 2 (dependent): {}".format(label(project2, source2))), file=out)
    print(
        style.dim(
            "{} folders in project 1, {} in project 2, {} in both".format(
                len(index1), len(index2), len(shared)
            )
        ),
        file=out,
    )
    print("", file=out)

    # Rule violation: project 2 must not hold folders project 1 does not have.
    if extra:
        print(
            style.red(
                "EXTRA in project 2 - not in project 1 ({}):".format(len(extra))
            ),
            file=out,
        )
        for key in extra:
            name = display_name(index2, key)
            line = "  {}".format(style.red(name))
            if show_details:
                line += style.dim("  [{}]".format(describe(index2[key][0], source2)))
            print(line, file=out)
        print("", file=out)
    else:
        print(style.green("No extra folders in project 2."), file=out)
        print("", file=out)

    if missing:
        print(
            style.yellow(
                "MISSING from project 2 - present in project 1 ({}):".format(len(missing))
            ),
            file=out,
        )
        for key in missing:
            name = display_name(index1, key)
            line = "  {}".format(style.yellow(name))
            if show_details:
                line += style.dim("  [{}]".format(describe(index1[key][0], source1)))
            print(line, file=out)
        print("", file=out)
    else:
        print(style.green("Project 2 has every folder of project 1."), file=out)
        print("", file=out)

    if show_matches:
        print(style.bold("IN BOTH ({}):".format(len(shared))), file=out)
        for key in shared:
            name = display_name(index1, key)
            row1 = index1[key][0]
            row2 = index2[key][0]
            line = "  {}".format(name)
            if show_details:
                # Ids from each side, then the file counts once. A matched pair
                # whose counts differ is highlighted: same folder, different
                # contents is worth a look.
                counts = "{} vs {} files".format(
                    "?" if row1.get("no_files") is None else row1["no_files"],
                    "?" if row2.get("no_files") is None else row2["no_files"],
                )
                if row1.get("no_files") != row2.get("no_files"):
                    counts = style.yellow(counts)
                line += style.dim("  [{} | {} | ".format(
                    _id_part(row1, source1), _id_part(row2, source2)
                )) + counts + style.dim("]")
            print(line, file=out)
        print("", file=out)

    # Duplicate names within one project point at a data problem of their own.
    for project, source, index in ((project1, source1, index1), (project2, source2, index2)):
        dupes = {k: v for k, v in index.items() if len(v) > 1}
        if dupes:
            print(
                style.yellow(
                    "Duplicate folder names in {} ({}):".format(
                        label(project, source), len(dupes)
                    )
                ),
                file=out,
            )
            id_column = SOURCES[source]["id_column"]
            for key, rows in sorted(dupes.items()):
                ids = ", ".join(
                    "(none)" if r.get("folder_id") is None else str(r["folder_id"])
                    for r in rows
                )
                print(
                    "  {} {}".format(
                        display_name(index, key),
                        style.dim("[{} {}]".format(id_column, ids)),
                    ),
                    file=out,
                )
            print("", file=out)


def write_csv(
    path: Path,
    source1: str,
    source2: str,
    index1: dict[str, list[dict]],
    index2: dict[str, list[dict]],
    extra: list[str],
    missing: list[str],
    shared: list[str],
    include_shared: bool,
) -> None:
    def cell(row: dict) -> str:
        """A folder id for CSV; empty rather than "None" for a NULL uid."""
        value = row.get("folder_id")
        return "" if value is None else str(value)

    rows: list[tuple[str, str, str, str]] = []
    for key in extra:
        rows.append(
            ("extra_in_project2", display_name(index2, key), "", cell(index2[key][0]))
        )
    for key in missing:
        rows.append(
            ("missing_in_project2", display_name(index1, key), cell(index1[key][0]), "")
        )
    if include_shared:
        for key in shared:
            rows.append(
                (
                    "in_both",
                    display_name(index1, key),
                    cell(index1[key][0]),
                    cell(index2[key][0]),
                )
            )
    header = ["status", "folder_name", "project1_folder_id", "project2_folder_id"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def build_json(
    project1: dict,
    project2: dict,
    source1: str,
    source2: str,
    index1: dict[str, list[dict]],
    index2: dict[str, list[dict]],
    extra: list[str],
    missing: list[str],
    shared: list[str],
) -> dict:
    return {
        "project1": {
            "project_id": project1["project_id"],
            "project_alias": project1.get("project_alias"),
            "source_table": SOURCES[source1]["table"],
            "folder_count": len(index1),
        },
        "project2": {
            "project_id": project2["project_id"],
            "project_alias": project2.get("project_alias"),
            "source_table": SOURCES[source2]["table"],
            "folder_count": len(index2),
        },
        "extra_in_project2": [display_name(index2, k) for k in extra],
        "missing_in_project2": [display_name(index1, k) for k in missing],
        "in_both_count": len(shared),
        "in_both": [
            {
                "folder_name": display_name(index1, k),
                "project1_folder_id": index1[k][0].get("folder_id"),
                "project2_folder_id": index2[k][0].get("folder_id"),
                "project1_no_files": index1[k][0].get("no_files"),
                "project2_no_files": index2[k][0].get("no_files"),
            }
            for k in shared
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare the folders of two Osprey projects. Project 2 must not have "
            "folders that project 1 does not have."
        ),
        epilog=(
            "Each project is given as its project_alias or its numeric project_id. "
            "By default project 1 is read from `folders` and project 2 from "
            "`transcription_folders`."
        ),
    )
    parser.add_argument("project1", help="reference project (alias or project_id)")
    parser.add_argument("project2", help="dependent project (alias or project_id)")
    parser.add_argument(
        "--project1-source",
        choices=sorted(SOURCES),
        default=DEFAULT_SOURCE1,
        help="table holding project 1's folders (default: %(default)s)",
    )
    parser.add_argument(
        "--project2-source",
        choices=sorted(SOURCES),
        default=DEFAULT_SOURCE2,
        help="table holding project 2's folders (default: %(default)s)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also exit non-zero when project 2 is missing folders from project 1",
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="compare folder names case-sensitively (default follows the DB collation)",
    )
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="list folder names only, without folder id/date/file counts",
    )
    parser.add_argument(
        "--show-matches",
        action="store_true",
        help="also list the folders present in both projects (always in --json)",
    )
    parser.add_argument(
        "--no-color", action="store_true", help="disable ANSI colors in the report"
    )
    parser.add_argument("--csv", metavar="PATH", help="also write the comparison to a CSV file")
    parser.add_argument(
        "--csv-include-shared",
        action="store_true",
        help="include folders present in both projects in the CSV",
    )
    parser.add_argument(
        "--json", action="store_true", help="print the result as JSON instead of a report"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source1 = args.project1_source
    source2 = args.project2_source

    try:
        project1 = resolve_project(args.project1)
        project2 = resolve_project(args.project2)
    except ProjectNotFound as err:
        print("error: {}".format(err), file=sys.stderr)
        return EXIT_ERROR

    if project1["project_id"] == project2["project_id"] and source1 == source2:
        print("error: both arguments resolve to the same project and table", file=sys.stderr)
        return EXIT_ERROR

    # A transcription project read from `folders`, or the reverse, is usually a
    # mistake, so say so without refusing: the flags are there to be used.
    for project, source, position in (
        (project1, source1, "project 1"),
        (project2, source2, "project 2"),
    ):
        is_transcription = bool(project.get("transcription"))
        reads_transcription = source == "transcription_folders"
        if is_transcription != reads_transcription:
            print(
                "warning: {} ({}) has transcription={}, but is being read from {}".format(
                    position,
                    project.get("project_alias") or project["project_id"],
                    int(is_transcription),
                    SOURCES[source]["table"],
                ),
                file=sys.stderr,
            )

    index1 = index_folders(fetch_folders(project1["project_id"], source1), args.case_sensitive)
    index2 = index_folders(fetch_folders(project2["project_id"], source2), args.case_sensitive)
    extra, missing, shared = compare(index1, index2)

    if args.json:
        print(
            json.dumps(
                build_json(
                    project1, project2, source1, source2,
                    index1, index2, extra, missing, shared,
                ),
                indent=2,
                default=str,
            )
        )
    else:
        style = Style(enabled=not args.no_color and _supports_color(sys.stdout))
        report(
            project1,
            project2,
            source1,
            source2,
            index1,
            index2,
            extra,
            missing,
            shared,
            style,
            show_details=not args.no_details,
            show_matches=args.show_matches,
        )

    if args.csv:
        csv_path = Path(args.csv)
        write_csv(
            csv_path, source1, source2, index1, index2,
            extra, missing, shared, args.csv_include_shared,
        )
        print("Wrote {}".format(csv_path), file=sys.stderr)

    if extra or (args.strict and missing):
        return EXIT_DIFFERENCES
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
