"""Командная строка: ozon-assembly-merge file1.pdf file2.pdf ... [-o result.xlsx]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .merge import SORT_KEYS, MergeError, merge_lists
from .parser import AssemblyParseError, parse_assembly_list
from .writers import FORMATS, write

PATTERN = "carriage_assembly_list*.pdf"


def _collect(inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            found = sorted(p.glob(PATTERN))
            if not found:
                raise SystemExit(f"в папке {p} нет файлов {PATTERN}")
            files.extend(found)
        elif p.is_file():
            files.append(p)
        else:
            raise SystemExit(f"файл не найден: {p}")
    return files


def _default_out(first: Path, dates: list[str], fmt: str) -> Path:
    suffix = dates[0].replace(".", "-") if len(dates) == 1 else "разные_даты"
    return first.parent / f"Сборочный_лист_объединённый_{suffix}.{fmt}"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="ozon-assembly-merge",
        description="Склеивает PDF сборочных листов Ozon в один список с суммой по артикулу.",
    )
    ap.add_argument("inputs", nargs="+", help="PDF-файлы или папки с carriage_assembly_list*.pdf")
    ap.add_argument("-o", "--out", action="append", default=[],
                    help="куда сохранить; формат по расширению (.xlsx/.csv/.pdf); можно указать несколько раз")
    ap.add_argument("-f", "--format", choices=FORMATS, default="xlsx",
                    help="формат файла по умолчанию, если --out не задан (xlsx)")
    ap.add_argument("--sort", choices=list(SORT_KEYS), default="source",
                    help="порядок строк: source — как в листах, article, product, qty (по убыванию)")
    ap.add_argument("--strict-dates", action="store_true",
                    help="остановиться, если листы за разные даты")
    ap.add_argument("-q", "--quiet", action="store_true", help="не печатать сводку")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    files = _collect(args.inputs)

    try:
        lists = [parse_assembly_list(f) for f in files]
        result = merge_lists(lists, sort=args.sort)
    except (AssemblyParseError, MergeError) as e:
        print(f"ОШИБКА: {e}", file=sys.stderr)
        print("Результат не сохранён, чтобы не отдать неполные данные.", file=sys.stderr)
        return 2

    for w in result.warnings:
        print(f"ВНИМАНИЕ: {w}", file=sys.stderr)
    if args.strict_dates and len(result.dates) > 1:
        print("ОШИБКА: листы за разные даты, а задан --strict-dates", file=sys.stderr)
        return 3

    outs = [Path(o) for o in args.out] or [_default_out(files[0], result.dates, args.format)]
    try:
        saved = [write(result, o) for o in outs]
    except ValueError as e:
        print(f"ОШИБКА: {e}", file=sys.stderr)
        return 2

    if not args.quiet:
        print(f"Файлов: {len(lists)}")
        for a in lists:
            print(f"  {a.path.name}: {a.label}, строк {len(a.rows)}, дата {a.date or '—'}")
        print(f"Строк на входе: {result.input_rows}")
        print(f"Уникальных артикулов: {len(result.items)}, из них объединено: {len(result.merged_items)}")
        print(f"Всего штук (до и после объединения): {result.total_qty}")
        for p in saved:
            print(f"Сохранено: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
