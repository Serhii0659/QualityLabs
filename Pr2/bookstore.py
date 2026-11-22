# pyright: reportUnnecessaryIsInstance=false
from typing import Any


class BookNotFoundError(Exception):
    """Книги з такою назвою немає в інвентарі."""


class InsufficientStockError(Exception):
    """На складі менше книг, ніж запитано."""


class Bookstore:
    def __init__(self) -> None:
        # ключ - назва книги, значення - словник з даними
        self._books: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _validate_title(title: str) -> str:
        if not isinstance(title, str) or not title.strip():
            raise ValueError('Назва має бути непорожнім рядком')
        return title.strip()

    @staticmethod
    def _is_int(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    def add_book(self, title: str, author: str, price: float, quantity: int) -> None:
        """Додає книгу. Якщо така назва вже є, збільшує кількість."""
        title = self._validate_title(title)
        if not isinstance(author, str) or not author.strip():
            raise ValueError('Автор має бути непорожнім рядком')
        if isinstance(price, bool) or not isinstance(price, (int, float)) or price < 0:
            raise ValueError('Ціна має бути числом >= 0')
        if not self._is_int(quantity) or quantity < 0:
            raise ValueError('Кількість має бути цілим числом >= 0')

        if title in self._books:
            self._books[title]['quantity'] += quantity
        else:
            self._books[title] = {
                'title': title,
                'author': author.strip(),
                'price': float(price),
                'quantity': quantity,
            }

    def remove_book(self, title: str) -> bool:
        """Видаляє книгу. Повертає True, якщо видалено, False, якщо книги не було."""
        if not isinstance(title, str):
            return False
        return self._books.pop(title.strip(), None) is not None

    def search_book(self, title: str) -> dict[str, Any] | None:
        """Повертає копію даних книги або None, якщо книги немає."""
        title = self._validate_title(title)
        book = self._books.get(title)
        return dict(book) if book else None

    def purchase_book(self, title: str, quantity: int) -> float:
        """Зменшує запас і повертає вартість покупки."""
        title = self._validate_title(title)
        if not self._is_int(quantity) or quantity <= 0:
            raise ValueError('Кількість для покупки має бути цілим числом > 0')

        book = self._books.get(title)
        if book is None:
            raise BookNotFoundError(f'Книгу "{title}" не знайдено')
        if book['quantity'] < quantity:
            raise InsufficientStockError(
                f'Запитано {quantity}, в наявності {book["quantity"]}'
            )

        book['quantity'] -= quantity
        return round(book['price'] * quantity, 2)

    def inventory_value(self) -> float:
        """Загальна вартість усіх книг на складі."""
        total: float = sum(b['price'] * b['quantity'] for b in self._books.values())
        return round(total, 2)
