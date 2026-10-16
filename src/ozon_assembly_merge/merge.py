"""Объединение строк нескольких сборочных листов по Артикулу."""

from __future__ import annotations

from dataclasses import dataclass, field

from .parser import AssemblyList


class MergeError(RuntimeError):
    """Сумма количества до и после объединения не совпала."""


@dataclass
class MergedItem:
    article: str
    product: str
    qty: int = 0
    sources: list[tuple[str, int]] = field(default_factory=list)

    @property
    def is_merged(self) -> bool:
        return len(self.sources) > 1

    def sources_text(self) -> str:
        return "; ".join(f"{label}: {qty}" for label, qty in self.sources)


@dataclass
class MergeResult:
    items: list[MergedItem]
    total_qty: int
    input_rows: int
    dates: list[str]
    warnings: list[str]

    @property
    def merged_items(self) -> list[MergedItem]:
        return [i for i in self.items if i.is_merged]


SORT_KEYS = {
    "source": None,
    "article": lambda i: i.article.casefold(),
    "product": lambda i: i.product.casefold(),
    "qty": lambda i: (-i.qty, i.article.casefold()),
}


def merge_lists(lists: list[AssemblyList], sort: str = "source") -> MergeResult:
    """Суммирует Кол-во по Артикулу. Ключ — Артикул, а не название:
    одинаковое название с разными артикулами (цвет, размер) — разные позиции."""
    warnings: list[str] = []
    dates = sorted({a.date for a in lists if a.date})
    if len(dates) > 1:
        warnings.append(f"листы датированы по-разному: {', '.join(dates)}")

    merged: dict[str, MergedItem] = {}
    for alist in lists:
        for row in alist.rows:
            item = merged.get(row.article)
            if item is None:
                item = merged[row.article] = MergedItem(row.article, row.product)
            elif item.product != row.product:
                warnings.append(
                    f"артикул «{row.article}» встречается с разными названиями: "
                    f"«{item.product}» и «{row.product}» (оставлено первое)"
                )
            item.qty += row.qty
            item.sources.append((alist.label, row.qty))

    items = list(merged.values())
    key = SORT_KEYS[sort]
    if key is not None:
        items.sort(key=key)

    before = sum(a.total_qty for a in lists)
    after = sum(i.qty for i in items)
    if before != after:
        raise MergeError(f"сумма Кол-во до объединения {before} не равна сумме после {after}")

    return MergeResult(
        items=items,
        total_qty=after,
        input_rows=sum(len(a.rows) for a in lists),
        dates=dates,
        warnings=warnings,
    )
