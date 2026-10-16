"""Генератор синтетических сборочных листов в раскладке, как у Ozon.

Без рамок ячеек: на первой странице — линия под заголовком таблицы из 5
сегментов и линии между строками; на страницах-продолжениях первая строка
начинается от верха страницы, а первая линия страницы — её НИЖНЯЯ граница.
Текст ячеек центрируется по высоте строки. Данные вымышленные.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from ozon_assembly_merge.writers import _font_path

FONT = "DejaVuSans"
PAGE_W, PAGE_H = 595.0, 842.0
COLS = {"№": (28, 58), "Фото": (58, 118), "Товар": (118, 318), "Артикул": (318, 498), "Кол-во": (498, 568)}
ROW_H = 56.0
LEADING = 10.0
SIZE = 8
FIRST_PAGE_TABLE_TOP = 120.0
CONT_PAGE_TOP = 20.0
PAGE_BOTTOM_LIMIT = 800.0


@dataclass
class Item:
    product: str
    article: str
    qty: int


def _register_font() -> None:
    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT, _font_path()))


def _wrap(text: str, width: float) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if pdfmetrics.stringWidth(trial, FONT, SIZE) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _y(top: float) -> float:
    return PAGE_H - top


def _draw_cell(c: canvas.Canvas, col: str, lines: list[str], row_top: float) -> None:
    x0, _ = COLS[col]
    mid = row_top + ROW_H / 2
    first_top = mid - len(lines) * LEADING / 2
    for i, line in enumerate(lines):
        c.drawString(x0 + 3, _y(first_top + (i + 1) * LEADING - 2), line)


def make_assembly_pdf(
    path: Path,
    items: list[Item],
    *,
    date: str = "17.10.2026",
    warehouse: str = "Тестовый склад",
    shipments: int | None = None,
    numbers: list[int] | None = None,
) -> Path:
    _register_font()
    c = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    c.setFont(FONT, 10)
    for i, text in enumerate([
        f"Дата: {date}",
        f"Количество отправлений: {shipments if shipments is not None else len(items)}",
        f"Склад: {warehouse}",
        "Служба доставки: Ozon",
    ]):
        c.drawString(28, _y(40 + i * 15), text)

    c.setFont(FONT, SIZE)
    for name, (x0, _) in COLS.items():
        c.drawString(x0 + 3, _y(112), name)
    c.setLineWidth(0.5)
    for x0, x1 in COLS.values():
        c.line(x0 + 1, _y(FIRST_PAGE_TABLE_TOP), x1 - 1, _y(FIRST_PAGE_TABLE_TOP))

    row_top = FIRST_PAGE_TABLE_TOP
    nums = numbers or list(range(1, len(items) + 1))
    for num, item in zip(nums, items):
        if row_top + ROW_H > PAGE_BOTTOM_LIMIT:
            c.showPage()
            c.setFont(FONT, SIZE)
            c.setLineWidth(0.5)
            row_top = CONT_PAGE_TOP
        _draw_cell(c, "№", [str(num)], row_top)
        c.setFillGray(0.85)
        c.rect(COLS["Фото"][0] + 8, _y(row_top + ROW_H - 6), 44, ROW_H - 12, stroke=0, fill=1)
        c.setFillGray(0)
        _draw_cell(c, "Товар", _wrap(item.product, 190), row_top)
        _draw_cell(c, "Артикул", _wrap(item.article, 170), row_top)
        _draw_cell(c, "Кол-во", [str(item.qty)], row_top)
        row_top += ROW_H
        c.line(COLS["№"][0], _y(row_top), COLS["Кол-во"][1], _y(row_top))
    c.save()
    return path


PRODUCTS = [
    ("Конструктор «Городская пожарная часть», 520 деталей", "KONSTR-CITY-FIRE-520"),
    ("Батарейки для слуховых аппаратов ZA13, 6 шт", "для слуховых аппаратов ZA13, 6 шт, упаковка блистер"),
    ("Часы наручные детские электронные", "WATCH-KIDS-BLUE"),
    ("Часы наручные детские электронные", "WATCH-KIDS-PINK"),
    ("Серьги-кольца позолоченные, диаметр 20 мм", "EAR-RING-20-GOLD"),
    ("Конструктор «Космическая станция» с мини-фигурками и наклейками, 1200 деталей",
     "KONSTR SPACE STATION 1200 деталей набор с фигурками и наклейками версия 2"),
    ("Батарейка литиевая CR2032, 5 шт", "CR2032-5"),
    ("Набор браслетов из бусин, 12 шт", "BRACELET-SET-12"),
]


def catalog(n: int, offset: int = 0, qty_base: int = 1) -> list[Item]:
    out = []
    for i in range(n):
        product, article = PRODUCTS[(i + offset) % len(PRODUCTS)]
        k = (i + offset) // len(PRODUCTS)
        if k:
            article = f"{article}-V{k}"
        out.append(Item(product, article, qty_base + (i % 4)))
    return out
