#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

BEGIN_RE = re.compile(r"^\s*/begin\s+(\S+)(?:\s+(\S+))?", re.IGNORECASE)
END_RE = re.compile(r"^\s*/end\s+(\S+)", re.IGNORECASE)
COMPU_TAB_REF_RE = re.compile(r"^\s*COMPU_TAB_REF\s+(\S+)", re.IGNORECASE)
COMMON_HEADER_NAMES = {
    "signal",
    "signals",
    "name",
    "names",
    "measurement",
    "measurements",
    "symbol",
    "identifier",
    "shortname",
    "shortidentifier",
    "variablename",
}


@dataclass
class Block:
    kind: str
    name: Optional[str]
    lines: list[str]


@dataclass
class RawLine:
    line: str


@dataclass
class Stats:
    total_measurements: int = 0
    kept_measurements: int = 0
    dropped_measurements: int = 0
    total_characteristics: int = 0
    dropped_characteristics: int = 0
    total_axis_pts: int = 0
    dropped_axis_pts: int = 0
    dropped_structure_blocks: int = 0
    total_compu_methods: int = 0
    kept_compu_methods: int = 0
    total_compu_vtabs: int = 0
    kept_compu_vtabs: int = 0
    found_measurements: set[str] = field(default_factory=set)

    def merge(self, other: "Stats") -> None:
        self.total_measurements += other.total_measurements
        self.kept_measurements += other.kept_measurements
        self.dropped_measurements += other.dropped_measurements
        self.total_characteristics += other.total_characteristics
        self.dropped_characteristics += other.dropped_characteristics
        self.total_axis_pts += other.total_axis_pts
        self.dropped_axis_pts += other.dropped_axis_pts
        self.dropped_structure_blocks += other.dropped_structure_blocks
        self.total_compu_methods += other.total_compu_methods
        self.kept_compu_methods += other.kept_compu_methods
        self.total_compu_vtabs += other.total_compu_vtabs
        self.kept_compu_vtabs += other.kept_compu_vtabs
        self.found_measurements.update(other.found_measurements)


@dataclass
class VerifyResult:
    checked_signals: int
    mismatched_measurements: list[str] = field(default_factory=list)
    missing_measurements_in_output: list[str] = field(default_factory=list)
    missing_compu_methods: list[str] = field(default_factory=list)
    mismatched_compu_methods: list[str] = field(default_factory=list)
    missing_compu_vtabs: list[str] = field(default_factory=list)
    mismatched_compu_vtabs: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(
            [
                self.mismatched_measurements,
                self.missing_measurements_in_output,
                self.missing_compu_methods,
                self.mismatched_compu_methods,
                self.missing_compu_vtabs,
                self.mismatched_compu_vtabs,
            ]
        )


@dataclass
class FilterJobResult:
    stats: Stats
    requested_signals: int
    missing_names: list[str]
    output_path: Path
    output_encoding: str
    missing_report_path: Optional[Path] = None
    verify_result: Optional[VerifyResult] = None


class VerifyFailedError(ValueError):
    pass


def read_text_with_fallback(path: Path) -> tuple[str, str]:
    encodings = ["utf-8", "cp1252", "latin-1"]
    last_error: Optional[Exception] = None
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding), encoding
        except UnicodeDecodeError as exc:
            last_error = exc
    raise RuntimeError(f"Could not decode file: {path}") from last_error


def write_text(path: Path, text: str, encoding: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=encoding, newline="") as handle:
        handle.write(text)


def normalize_name(value: str, ignore_case: bool) -> str:
    value = value.strip().strip('"').strip("'")
    return value.upper() if ignore_case else value


def detect_dialect(text: str):
    sample = text[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        if sample.count(";") > sample.count(","):
            class SemiColon(csv.excel):
                delimiter = ";"
            return SemiColon
        return csv.excel


def looks_like_header(row: list[str]) -> bool:
    normalized = set()
    for cell in row:
        token = re.sub(r"[^a-z0-9]+", "", cell.strip().lower())
        if token:
            normalized.add(token)
    return bool(normalized & COMMON_HEADER_NAMES)


def load_signal_names(csv_path: Path, column: Optional[str], ignore_case: bool) -> set[str]:
    text, _ = read_text_with_fallback(csv_path)
    dialect = detect_dialect(text)

    if column:
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        if not reader.fieldnames:
            raise ValueError("CSV file does not contain a header row, but --csv-column was used.")

        field_map = {field.lower(): field for field in reader.fieldnames if field is not None}
        real_column = field_map.get(column.lower())
        if not real_column:
            raise ValueError(
                f"Column '{column}' was not found in CSV header. Available columns: {', '.join(reader.fieldnames)}"
            )

        return {
            normalize_name(value, ignore_case)
            for row in reader
            for value in [row.get(real_column, "")]
            if value and value.strip()
        }

    rows = list(csv.reader(io.StringIO(text), dialect=dialect))
    if not rows:
        return set()

    start_index = 1 if looks_like_header(rows[0]) else 0
    names: set[str] = set()
    for row in rows[start_index:]:
        value = next((cell.strip() for cell in row if cell and cell.strip()), "")
        if value:
            names.add(normalize_name(value, ignore_case))
    return names


def find_matching_end(lines: list[str], start_index: int) -> int:
    depth = 0
    for index in range(start_index, len(lines)):
        if BEGIN_RE.match(lines[index]):
            depth += 1
        elif END_RE.match(lines[index]):
            depth -= 1
            if depth == 0:
                return index
    raise ValueError(f"Could not find matching /end for block starting on line {start_index + 1}.")


def parse_module_body(body_lines: list[str]) -> list[Block | RawLine]:
    items: list[Block | RawLine] = []
    index = 0
    while index < len(body_lines):
        begin_match = BEGIN_RE.match(body_lines[index])
        if begin_match:
            end_index = find_matching_end(body_lines, index)
            items.append(
                Block(
                    kind=begin_match.group(1).upper(),
                    name=begin_match.group(2),
                    lines=body_lines[index : end_index + 1],
                )
            )
            index = end_index + 1
        else:
            items.append(RawLine(body_lines[index]))
            index += 1
    return items


def significant_body_lines(block_lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in block_lines[1:-1]:
        stripped = line.strip()
        if stripped:
            result.append(stripped)
    return result


def extract_measurement_compu_method(block_lines: list[str]) -> Optional[str]:
    body = significant_body_lines(block_lines)
    if not body:
        return None

    first_tokens = body[0].split()
    if len(first_tokens) >= 2 and not body[0].lstrip().startswith(('"', "'")):
        return first_tokens[1].strip('"')

    if len(body) >= 3:
        token = body[2].split()[0]
        return token.strip('"')

    return None


def extract_compu_tab_ref(block_lines: list[str]) -> Optional[str]:
    for line in block_lines[1:-1]:
        match = COMPU_TAB_REF_RE.match(line)
        if match:
            return match.group(1)
    return None


def collect_needed_support(
    items: list[Block | RawLine],
    selected_names: set[str],
    ignore_case: bool,
) -> tuple[set[str], set[str], Stats]:
    stats = Stats()
    needed_compu_methods: set[str] = set()

    for item in items:
        if not isinstance(item, Block):
            continue
        if item.kind == "MEASUREMENT":
            stats.total_measurements += 1
            if item.name is None:
                continue
            normalized_name = normalize_name(item.name, ignore_case)
            stats.found_measurements.add(normalized_name)
            if normalized_name in selected_names:
                stats.kept_measurements += 1
                compu_method = extract_measurement_compu_method(item.lines)
                if compu_method and compu_method.upper() != "NO_COMPU_METHOD":
                    needed_compu_methods.add(compu_method)
            else:
                stats.dropped_measurements += 1
        elif item.kind == "CHARACTERISTIC":
            stats.total_characteristics += 1
        elif item.kind == "AXIS_PTS":
            stats.total_axis_pts += 1
        elif item.kind == "COMPU_METHOD":
            stats.total_compu_methods += 1
        elif item.kind == "COMPU_VTAB":
            stats.total_compu_vtabs += 1

    needed_compu_vtabs: set[str] = set()
    if needed_compu_methods:
        for item in items:
            if not isinstance(item, Block):
                continue
            if item.kind == "COMPU_METHOD" and item.name in needed_compu_methods:
                ref = extract_compu_tab_ref(item.lines)
                if ref:
                    needed_compu_vtabs.add(ref)

    return needed_compu_methods, needed_compu_vtabs, stats


def filter_module_block(
    module_lines: list[str],
    selected_names: set[str],
    drop_structure: bool,
    drop_characteristics: bool,
    drop_axis_pts: bool,
    prune_support: bool,
    ignore_case: bool,
) -> tuple[list[str], Stats]:
    if len(module_lines) < 2:
        return module_lines, Stats()

    module_header = module_lines[0]
    module_footer = module_lines[-1]
    module_body = module_lines[1:-1]
    items = parse_module_body(module_body)

    needed_compu_methods, needed_compu_vtabs, stats = collect_needed_support(items, selected_names, ignore_case)

    new_body: list[str] = []
    for item in items:
        if isinstance(item, RawLine):
            new_body.append(item.line)
            continue

        if item.kind == "MEASUREMENT":
            if item.name is None:
                new_body.extend(item.lines)
                continue
            normalized_name = normalize_name(item.name, ignore_case)
            if normalized_name in selected_names:
                new_body.extend(item.lines)
            continue

        if drop_characteristics and item.kind == "CHARACTERISTIC":
            stats.dropped_characteristics += 1
            continue

        if drop_axis_pts and item.kind == "AXIS_PTS":
            stats.dropped_axis_pts += 1
            continue

        if drop_structure and item.kind in {"GROUP", "FUNCTION"}:
            stats.dropped_structure_blocks += 1
            continue

        if item.kind == "COMPU_METHOD":
            if prune_support and item.name not in needed_compu_methods:
                continue
            stats.kept_compu_methods += 1
            new_body.extend(item.lines)
            continue

        if item.kind == "COMPU_VTAB":
            if prune_support and item.name not in needed_compu_vtabs:
                continue
            stats.kept_compu_vtabs += 1
            new_body.extend(item.lines)
            continue

        new_body.extend(item.lines)

    return [module_header, *new_body, module_footer], stats


def filter_a2l_lines(
    lines: list[str],
    selected_names: set[str],
    drop_structure: bool,
    drop_characteristics: bool,
    drop_axis_pts: bool,
    prune_support: bool,
    ignore_case: bool,
) -> tuple[list[str], Stats]:
    output_lines: list[str] = []
    total_stats = Stats()
    index = 0
    module_count = 0

    while index < len(lines):
        begin_match = BEGIN_RE.match(lines[index])
        if begin_match and begin_match.group(1).upper() == "MODULE":
            end_index = find_matching_end(lines, index)
            module_count += 1
            filtered_module, module_stats = filter_module_block(
                lines[index : end_index + 1],
                selected_names,
                drop_structure,
                drop_characteristics,
                drop_axis_pts,
                prune_support,
                ignore_case,
            )
            output_lines.extend(filtered_module)
            total_stats.merge(module_stats)
            index = end_index + 1
        else:
            output_lines.append(lines[index])
            index += 1

    if module_count == 0:
        raise ValueError("No /begin MODULE ... /end MODULE block was found in the A2L file.")

    return output_lines, total_stats


def extract_named_blocks(lines: list[str], kind: str) -> dict[str, Block]:
    blocks: dict[str, Block] = {}
    wanted_kind = kind.upper()
    index = 0
    while index < len(lines):
        begin_match = BEGIN_RE.match(lines[index])
        if begin_match and begin_match.group(1).upper() == wanted_kind:
            end_index = find_matching_end(lines, index)
            name = begin_match.group(2)
            if name and name not in blocks:
                blocks[name] = Block(wanted_kind, name, lines[index : end_index + 1])
            index = end_index + 1
        else:
            index += 1
    return blocks


def verify_measurements(
    original_lines: list[str],
    filtered_lines: list[str],
    selected_names: set[str],
    ignore_case: bool,
) -> VerifyResult:
    original_measurements = {
        normalize_name(name, ignore_case): block
        for name, block in extract_named_blocks(original_lines, "MEASUREMENT").items()
    }
    filtered_measurements = {
        normalize_name(name, ignore_case): block
        for name, block in extract_named_blocks(filtered_lines, "MEASUREMENT").items()
    }

    verify_result = VerifyResult(checked_signals=0)
    needed_compu_methods: set[str] = set()

    for selected_name in sorted(selected_names):
        original_block = original_measurements.get(selected_name)
        if original_block is None:
            continue
        verify_result.checked_signals += 1
        filtered_block = filtered_measurements.get(selected_name)
        display_name = original_block.name or selected_name

        if filtered_block is None:
            verify_result.missing_measurements_in_output.append(display_name)
            continue

        if original_block.lines != filtered_block.lines:
            verify_result.mismatched_measurements.append(display_name)
            continue

        compu_method = extract_measurement_compu_method(original_block.lines)
        if compu_method and compu_method.upper() != "NO_COMPU_METHOD":
            needed_compu_methods.add(compu_method)

    original_compu_methods = extract_named_blocks(original_lines, "COMPU_METHOD")
    filtered_compu_methods = extract_named_blocks(filtered_lines, "COMPU_METHOD")
    needed_compu_vtabs: set[str] = set()

    for compu_method_name in sorted(needed_compu_methods):
        original_method = original_compu_methods.get(compu_method_name)
        if original_method is None:
            continue
        filtered_method = filtered_compu_methods.get(compu_method_name)
        if filtered_method is None:
            verify_result.missing_compu_methods.append(compu_method_name)
            continue
        if original_method.lines != filtered_method.lines:
            verify_result.mismatched_compu_methods.append(compu_method_name)
            continue
        compu_tab_ref = extract_compu_tab_ref(original_method.lines)
        if compu_tab_ref:
            needed_compu_vtabs.add(compu_tab_ref)

    original_compu_vtabs = extract_named_blocks(original_lines, "COMPU_VTAB")
    filtered_compu_vtabs = extract_named_blocks(filtered_lines, "COMPU_VTAB")

    for compu_vtab_name in sorted(needed_compu_vtabs):
        original_vtab = original_compu_vtabs.get(compu_vtab_name)
        if original_vtab is None:
            continue
        filtered_vtab = filtered_compu_vtabs.get(compu_vtab_name)
        if filtered_vtab is None:
            verify_result.missing_compu_vtabs.append(compu_vtab_name)
            continue
        if original_vtab.lines != filtered_vtab.lines:
            verify_result.mismatched_compu_vtabs.append(compu_vtab_name)

    return verify_result


def build_verify_error_message(verify_result: VerifyResult) -> str:
    problems: list[str] = []
    if verify_result.missing_measurements_in_output:
        problems.append(
            f"missing MEASUREMENT in output: {', '.join(verify_result.missing_measurements_in_output[:5])}"
        )
    if verify_result.mismatched_measurements:
        problems.append(
            f"mismatched MEASUREMENT: {', '.join(verify_result.mismatched_measurements[:5])}"
        )
    if verify_result.missing_compu_methods:
        problems.append(
            f"missing COMPU_METHOD: {', '.join(verify_result.missing_compu_methods[:5])}"
        )
    if verify_result.mismatched_compu_methods:
        problems.append(
            f"mismatched COMPU_METHOD: {', '.join(verify_result.mismatched_compu_methods[:5])}"
        )
    if verify_result.missing_compu_vtabs:
        problems.append(
            f"missing COMPU_VTAB: {', '.join(verify_result.missing_compu_vtabs[:5])}"
        )
    if verify_result.mismatched_compu_vtabs:
        problems.append(
            f"mismatched COMPU_VTAB: {', '.join(verify_result.mismatched_compu_vtabs[:5])}"
        )
    details = "; ".join(problems) if problems else "unknown verification problem"
    return f"VERIFY FAILED: {details}"


def build_summary(result: FilterJobResult, drop_structure: bool) -> str:
    lines = [
        f"CSV signals requested : {result.requested_signals}",
        f"MEASUREMENTs in A2L   : {result.stats.total_measurements}",
        f"MEASUREMENTs kept     : {result.stats.kept_measurements}",
        f"MEASUREMENTs removed  : {result.stats.dropped_measurements}",
        f"CHARACTERISTICs total : {result.stats.total_characteristics}",
        f"CHARACTERISTICs removed: {result.stats.dropped_characteristics}",
        f"AXIS_PTS total        : {result.stats.total_axis_pts}",
        f"AXIS_PTS removed      : {result.stats.dropped_axis_pts}",
    ]
    if drop_structure:
        lines.append(f"GROUP/FUNCTION removed: {result.stats.dropped_structure_blocks}")
    lines.extend(
        [
            f"COMPU_METHOD kept     : {result.stats.kept_compu_methods}/{result.stats.total_compu_methods}",
            f"COMPU_VTAB kept       : {result.stats.kept_compu_vtabs}/{result.stats.total_compu_vtabs}",
            f"Signals not found     : {len(result.missing_names)}",
            f"Output written to     : {result.output_path}",
        ]
    )
    if result.missing_report_path is not None:
        lines.append(f"Missing report        : {result.missing_report_path}")
    if result.verify_result is not None:
        verify = result.verify_result
        lines.extend(
            [
                "",
                "--- VERIFY ---",
                f"Checked signals      : {verify.checked_signals}",
                f"Missing MEASUREMENT  : {len(verify.missing_measurements_in_output)}",
                f"Mismatched MEASUREMENT: {len(verify.mismatched_measurements)}",
                f"Missing COMPU_METHOD : {len(verify.missing_compu_methods)}",
                f"Mismatched COMPU_METHOD: {len(verify.mismatched_compu_methods)}",
                f"Missing COMPU_VTAB   : {len(verify.missing_compu_vtabs)}",
                f"Mismatched COMPU_VTAB: {len(verify.mismatched_compu_vtabs)}",
                f"Verify status        : {'OK' if verify.ok else 'FAILED'}",
            ]
        )
    return "\n".join(lines)


def run_filter_job(
    input_a2l: Path,
    input_csv: Path,
    output_a2l: Path,
    *,
    csv_column: Optional[str] = None,
    ignore_case: bool = False,
    drop_structure: bool = False,
    drop_characteristics: bool = False,
    drop_axis_pts: bool = False,
    prune_support: bool = False,
    missing_report: Optional[Path] = None,
    verify: bool = False,
) -> FilterJobResult:
    a2l_text, a2l_encoding = read_text_with_fallback(input_a2l)
    selected_names = load_signal_names(input_csv, csv_column, ignore_case)
    if not selected_names:
        raise ValueError("No signal names were read from the CSV file.")

    input_lines = a2l_text.splitlines(keepends=True)
    filtered_lines, stats = filter_a2l_lines(
        input_lines,
        selected_names,
        drop_structure,
        drop_characteristics,
        drop_axis_pts,
        prune_support,
        ignore_case,
    )

    verify_result = None
    if verify:
        verify_result = verify_measurements(input_lines, filtered_lines, selected_names, ignore_case)
        if not verify_result.ok:
            raise VerifyFailedError(build_verify_error_message(verify_result))

    missing_names = sorted(selected_names - stats.found_measurements)
    output_text = "".join(filtered_lines)
    write_text(output_a2l, output_text, a2l_encoding)

    if missing_report is not None:
        write_text(missing_report, "\n".join(missing_names) + ("\n" if missing_names else ""), "utf-8")

    return FilterJobResult(
        stats=stats,
        requested_signals=len(selected_names),
        missing_names=missing_names,
        output_path=output_a2l,
        output_encoding=a2l_encoding,
        missing_report_path=missing_report,
        verify_result=verify_result,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a filtered A2L that only keeps selected MEASUREMENT blocks from a CSV list."
    )
    parser.add_argument("input_a2l", type=Path, help="Source A2L file")
    parser.add_argument("input_csv", type=Path, help="CSV with signal names to keep")
    parser.add_argument("output_a2l", type=Path, help="Filtered A2L file to write")
    parser.add_argument(
        "--csv-column",
        help="Name of the CSV column that contains the A2L measurement names. If omitted, the first non-empty column is used.",
    )
    parser.add_argument(
        "--ignore-case",
        action="store_true",
        help="Compare signal names case-insensitively.",
    )
    parser.add_argument(
        "--drop-structure",
        action="store_true",
        help="Drop GROUP and FUNCTION blocks to avoid references to removed measurements.",
    )
    parser.add_argument(
        "--drop-characteristics",
        action="store_true",
        help="Drop CHARACTERISTIC blocks so the output only contains measurement objects plus supporting metadata.",
    )
    parser.add_argument(
        "--drop-axis-pts",
        action="store_true",
        help="Drop AXIS_PTS blocks. Useful when generating a measurement-only A2L.",
    )
    parser.add_argument(
        "--prune-support",
        action="store_true",
        help="Keep only COMPU_METHOD and COMPU_VTAB blocks that are referenced by the kept measurements.",
    )
    parser.add_argument(
        "--missing-report",
        type=Path,
        help="Optional path for a text file listing CSV signals that were not found in the A2L.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify that kept MEASUREMENT, COMPU_METHOD and COMPU_VTAB blocks are identical to the original A2L.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_filter_job(
        args.input_a2l,
        args.input_csv,
        args.output_a2l,
        csv_column=args.csv_column,
        ignore_case=args.ignore_case,
        drop_structure=args.drop_structure,
        drop_characteristics=args.drop_characteristics,
        drop_axis_pts=args.drop_axis_pts,
        prune_support=args.prune_support,
        missing_report=args.missing_report,
        verify=args.verify,
    )

    print(build_summary(result, drop_structure=args.drop_structure))

    if result.missing_names:
        preview = ", ".join(result.missing_names[:20])
        if len(result.missing_names) > 20:
            preview += ", ..."
        print(f"Missing names preview : {preview}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
