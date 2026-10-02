"""Filtros y paginación del catálogo, sin modificar sus datos."""

from dataclasses import dataclass
import unicodedata
from urllib.parse import urlencode


PAGE_SIZE = 5


def searchable(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", value.casefold())
        if not unicodedata.combining(char)
    )


def article_identity(article: dict) -> tuple[str, str, str]:
    return tuple(article[key].casefold() for key in ("category", "subcategory", "name"))


@dataclass(frozen=True)
class ArticleSearch:
    query: str = ""
    category: str = ""
    subcategory: str = ""
    page: int = 1
    sold_page: int = 1

    @classmethod
    def from_form(cls, values: dict):
        try:
            page = max(1, int(values.get("page", "1")))
        except ValueError:
            page = 1
        try:
            sold_page = max(1, int(values.get("sold_page", "1")))
        except ValueError:
            sold_page = 1
        return cls(
            values.get("q", ""), values.get("filter_category", ""),
            values.get("filter_subcategory", ""), page, sold_page,
        )

    def fields(self, *, post: bool = False, page: int | None = None) -> dict:
        return {
            "q": self.query,
            "filter_category" if post else "category": self.category,
            "filter_subcategory" if post else "subcategory": self.subcategory,
            "page": self.page if page is None else page,
            "sold_page": self.sold_page,
        }

    def url(self, *, page: int | None = None) -> str:
        return "/articulos?" + urlencode(self.fields(page=page))

    def matching(self, articles: list[dict]) -> list[dict]:
        query = searchable(self.query.strip())
        matches = [
            article for article in articles
            if query in searchable(article["name"])
            and (not self.category or article["category"] == self.category)
            and (not self.subcategory or article["subcategory"] == self.subcategory)
        ]
        matches.sort(key=lambda article: (
            searchable(article["name"]), article_identity(article), article["id"],
        ))
        return matches

    def paginate(self, matches: list[dict], *, page_size: int = PAGE_SIZE) -> tuple[list[dict], int, int, int]:
        if page_size not in (2, 3, 4, 5):
            raise ValueError("El tamaño de página debe estar entre 2 y 5.")
        pages = max(1, (len(matches) + page_size - 1) // page_size)
        page = min(max(1, self.page), pages)
        start = (page - 1) * page_size
        return matches[start:start + page_size], len(matches), page, pages

    def results(self, articles: list[dict], *, page_size: int = PAGE_SIZE) -> tuple[list[dict], int, int, int]:
        return self.paginate(self.matching(articles), page_size=page_size)
