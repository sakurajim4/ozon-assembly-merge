"""Разбор PDF «сборочного листа» Ozon (carriage_assembly_list_seller_*.pdf).

В этих PDF таблица нарисована без рамок ячеек, поэтому ``extract_tables()``
возвращает пустоту, а построчное чтение текста склеивает соседние ячейки.
Сетка восстанавливается по двум наборам линий:

* на первой странице — линия под заголовком таблицы из 5 сегментов,
  это границы колонок №/Фото/Товар/Артикул/Кол-во;
* на каждой странице — горизонтальные линии между строками.

Многострочный текст центрируется по высоте строки, поэтому на страницах-
продолжениях первая строка начинается выше первой линии страницы. Перед
линиями всегда добавляется виртуальная граница ``0.0``, иначе первая строка
каждой следующей страницы теряется без единой ошибки.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

COL_NAMES = ("№", "Фото", "Товар", "Артикул", "Кол-во")


class AssemblyParseError(ValueError):
    """PDF разобран не полностью — результату доверять нельзя."""


@dataclass(frozen=True)
class Row:
    num: int
    product: str
    article: str
    qty: int


@dataclass
class AssemblyList:
    path: Path
    date: str | None
    warehouse: str
    seller: str | None
    shipments: int | None
    rows: list[Row] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.seller:
            return f"{self.warehouse} (seller {self.seller})"
        return self.warehouse

    @property
    def total_qty(self) -> int:
        return sum(r.qty for r in self.rows)


def _column_bounds(page) -> dict[str, tuple[float, float]]:
    tops = sorted({round(ln["top"], 1) for ln in page.lines})
    if tops:
        first = tops[0]
        segs = sorted(
            {(round(ln["x0"], 1), round(ln["x1"], 1)) for ln in page.lines if round(ln["top"], 1) == first},
            key=lambda s: s[0],
        )
        if len(segs) == len(COL_NAMES):
            return dict(zip(COL_NAMES, segs))

    label_x0: dict[str, float] = {}
    for w in page.extract_words():
        if w["top"] < 150 and w["text"] in COL_NAMES and w["text"] not in label_x0:
            label_x0[w["text"]] = w["x0"]
    missing = [n for n in COL_NAMES if n not in label_x0]
    if missing:
        raise AssemblyParseError(f"не удалось определить границы колонок {missing} на первой странице")
    xs = sorted(label_x0[n] for n in COL_NAMES)
    bounds = {}
    for name in COL_NAMES:
        x0 = label_x0[name]
        i = xs.index(x0)
        x1 = xs[i + 1] if i + 1 < len(xs) else float(page.width)
        bounds[name] = (x0, x1)
    return bounds


def _sorted_text(words) -> str:
    words = sorted(words, key=lambda w: (round(w["top"]), w["x0"]))
    return " ".join(w["text"] for w in words).strip()


def _extract_rows(pdf) -> list[Row]:
    bounds = _column_bounds(pdf.pages[0])
    num_x0, num_x1 = bounds["№"]
    prod_x0, prod_x1 = bounds["Товар"]
    art_x0, art_x1 = bounds["Артикул"]
    qty_x0, qty_x1 = bounds["Кол-во"]

    rows: list[Row] = []
    for page in pdf.pages:
        words = page.extract_words()
        if not words:
            continue
        tops = sorted({round(ln["top"], 1) for ln in page.lines})
        bottom = max(w["bottom"] for w in words) + 20
        boundaries = [0.0] + tops + [bottom]
        cells = list(zip(boundaries[:-1], boundaries[1:]))

        anchors = sorted(
            (w["top"], int(w["text"]))
            for w in words
            if num_x0 - 2 <= w["x0"] <= num_x1 + 2 and re.fullmatch(r"\d+", w["text"])
        )

        for atop, anum in anchors:
            cell = next(((a, b) for a, b in cells if a - 0.5 <= atop < b + 0.5), None)
            if cell is None:
                continue
            start, end = cell
            prod_w, art_w, qty_w = [], [], []
            for w in words:
                if not (start - 0.5 <= w["top"] < end + 0.5):
                    continue
                x0 = w["x0"]
                if prod_x0 - 5 <= x0 < prod_x1 - 2:
                    prod_w.append(w)
                elif art_x0 - 5 <= x0 < art_x1 - 2:
                    art_w.append(w)
                elif qty_x0 - 5 <= x0 < qty_x1 + 5:
                    qty_w.append(w)
            qty_m = re.search(r"\d+", "".join(w["text"] for w in qty_w))
            if qty_m is None:
                raise AssemblyParseError(f"строка {anum}: не прочитано Кол-во")
            rows.append(Row(anum, _sorted_text(prod_w), _sorted_text(art_w), int(qty_m.group())))
    return rows


def parse_assembly_list(path: str | Path) -> AssemblyList:
    """Читает один PDF и проверяет, что строки идут подряд 1..N."""
    path = Path(path)
    with pdfplumber.open(path) as pdf:
        if not pdf.pages:
            raise AssemblyParseError(f"{path.name}: в PDF нет страниц")
        text = pdf.pages[0].extract_text() or ""
        rows = _extract_rows(pdf)

    m_date = re.search(r"Дата:\s*(\S+)", text)
    m_wh = re.search(r"Склад:\s*(.+)", text)
    m_ship = re.search(r"Количество отправлений:\s*(\d+)", text)
    m_seller = re.search(r"seller_(\d+)", path.name)

    nums = [r.num for r in rows]
    expected = list(range(1, len(rows) + 1))
    if not rows:
        raise AssemblyParseError(f"{path.name}: не найдено ни одной строки таблицы")
    if nums != expected:
        missing = sorted(set(range(1, max(nums) + 1)) - set(nums))
        raise AssemblyParseError(
            f"{path.name}: номера строк идут не подряд (пропущены {missing or '—'}). "
            "Обычно это ошибка восстановления границ строк, а не самого PDF."
        )

    return AssemblyList(
        path=path,
        date=m_date.group(1) if m_date else None,
        warehouse=m_wh.group(1).strip() if m_wh else path.stem,
        seller=m_seller.group(1) if m_seller else None,
        shipments=int(m_ship.group(1)) if m_ship else None,
        rows=rows,
    )
