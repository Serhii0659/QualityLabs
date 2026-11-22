"""Додаток книжкового магазину: інвентар, покупки, замовлення, знижки, рейтинги."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

_CENT = Decimal("0.01")


# Винятки


class BookstoreError(Exception):
    """Базова помилка книжкового магазину."""


class InvalidDataError(BookstoreError):
    """Некоректні вхідні дані."""


class DuplicateIsbnError(BookstoreError):
    """Книга з таким ISBN вже є в інвентарі."""


class BookNotFoundError(BookstoreError):
    """Книгу з таким ISBN не знайдено."""


class InsufficientStockError(BookstoreError):
    """Недостатньо примірників для покупки."""


class OrderNotFoundError(BookstoreError):
    """Замовлення не знайдено."""


class InvalidStatusTransitionError(BookstoreError):
    """Недопустима зміна статусу замовлення."""


class DiscountConflictError(BookstoreError):
    """Знижка для цього об'єкта вже існує."""


class InvalidRatingError(InvalidDataError):
    """Оцінка поза допустимим діапазоном."""


# Функція 1: керування інвентарем книг


@dataclass(frozen=True)
class Book:
    title: str
    author: str
    isbn: str
    price: Decimal
    category: str = ""

    def __post_init__(self) -> None:
        required = (
            ("Назва", self.title),
            ("Автор", self.author),
            ("ISBN", self.isbn),
        )
        for name, value in required:
            if not value.strip():
                raise InvalidDataError(f"{name} книги не може бути порожнім")
        if self.price <= 0:
            raise InvalidDataError("Ціна має бути більшою за нуль")


class Inventory:
    def __init__(self) -> None:
        self._books: dict[str, Book] = {}
        self._quantities: dict[str, int] = {}

    def add_book(self, book: Book, quantity: int) -> None:
        if quantity < 0:
            raise InvalidDataError("Кількість не може бути від'ємною")
        if book.isbn in self._books:
            raise DuplicateIsbnError(f"Книга з ISBN {book.isbn} вже існує")
        self._books[book.isbn] = book
        self._quantities[book.isbn] = quantity

    def has_book(self, isbn: str) -> bool:
        return isbn in self._books

    def get_book(self, isbn: str) -> Book:
        book = self._books.get(isbn)
        if book is None:
            raise BookNotFoundError(f"Книгу з ISBN {isbn} не знайдено")
        return book

    def get_quantity(self, isbn: str) -> int:
        self.get_book(isbn)
        return self._quantities[isbn]

    def remove_stock(self, isbn: str, quantity: int) -> None:
        if quantity <= 0:
            raise InvalidDataError("Кількість має бути додатною")
        available = self.get_quantity(isbn)
        if quantity > available:
            raise InsufficientStockError(
                f"Недостатньо примірників: потрібно {quantity}, є {available}"
            )
        self._quantities[isbn] = available - quantity


# Функція 4: управління знижками

MAX_PERCENT = Decimal(90)


@dataclass(frozen=True)
class Discount:
    percent: Decimal

    def __post_init__(self) -> None:
        if not 0 < self.percent <= MAX_PERCENT:
            raise InvalidDataError(
                f"Відсоток знижки має бути в межах (0; {MAX_PERCENT}]"
            )

    def apply(self, price: Decimal) -> Decimal:
        result = price * (100 - self.percent) / 100
        return result.quantize(_CENT, rounding=ROUND_HALF_UP)


class DiscountManager:
    def __init__(self, inventory: Inventory) -> None:
        self._inventory = inventory
        self._by_isbn: dict[str, Discount] = {}
        self._by_category: dict[str, Discount] = {}

    def add_book_discount(self, isbn: str, percent: Decimal) -> None:
        self._inventory.get_book(isbn)
        if isbn in self._by_isbn:
            raise DiscountConflictError(f"Для ISBN {isbn} знижка вже існує")
        self._by_isbn[isbn] = Discount(percent)

    def add_category_discount(self, category: str, percent: Decimal) -> None:
        if not category.strip():
            raise InvalidDataError("Категорія не може бути порожньою")
        if category in self._by_category:
            raise DiscountConflictError(f"Для категорії {category} знижка вже існує")
        self._by_category[category] = Discount(percent)

    def get_discount(self, isbn: str) -> Discount | None:
        book = self._inventory.get_book(isbn)
        # знижка на книгу має пріоритет, знижки не сумуються
        return self._by_isbn.get(isbn) or self._by_category.get(book.category)

    def final_price(self, isbn: str) -> Decimal:
        price = self._inventory.get_book(isbn).price
        discount = self.get_discount(isbn)
        return price if discount is None else discount.apply(price)


# Функція 2: обробка покупок книг


@dataclass(frozen=True)
class PurchaseRequest:
    isbn: str
    quantity: int


@dataclass(frozen=True)
class Purchase:
    isbn: str
    title: str
    quantity: int
    unit_price: Decimal

    @property
    def total(self) -> Decimal:
        return self.unit_price * self.quantity


class PurchaseService:
    def __init__(
        self, inventory: Inventory, discounts: DiscountManager | None = None
    ) -> None:
        self._inventory = inventory
        self._discounts = discounts
        self._history: list[Purchase] = []

    @property
    def history(self) -> tuple[Purchase, ...]:
        return tuple(self._history)

    def purchase(self, isbn: str, quantity: int) -> Purchase:
        return self.purchase_many([PurchaseRequest(isbn, quantity)])[0]

    def purchase_many(self, requests: Sequence[PurchaseRequest]) -> list[Purchase]:
        self._check_availability(requests)
        purchases = [self._execute(request) for request in requests]
        self._history.extend(purchases)
        return purchases

    def _check_availability(self, requests: Sequence[PurchaseRequest]) -> None:
        if not requests:
            raise InvalidDataError("Список покупок не може бути порожнім")
        needed: dict[str, int] = {}
        for request in requests:
            if request.quantity <= 0:
                raise InvalidDataError("Кількість має бути додатною")
            needed[request.isbn] = needed.get(request.isbn, 0) + request.quantity
        for isbn, quantity in needed.items():
            available = self._inventory.get_quantity(isbn)
            if quantity > available:
                raise InsufficientStockError(
                    f"Недостатньо примірників {isbn}: "
                    f"потрібно {quantity}, є {available}"
                )

    def _execute(self, request: PurchaseRequest) -> Purchase:
        book = self._inventory.get_book(request.isbn)
        price = book.price
        if self._discounts is not None:
            price = self._discounts.final_price(book.isbn)
        self._inventory.remove_stock(request.isbn, request.quantity)
        return Purchase(book.isbn, book.title, request.quantity, price)


# Функція 3: відстеження замовлень клієнтів


class OrderStatus(Enum):
    PROCESSING = "в обробці"
    SHIPPED = "відправлено"
    DELIVERED = "доставлено"


_NEXT_STATUS: dict[OrderStatus, OrderStatus] = {
    OrderStatus.PROCESSING: OrderStatus.SHIPPED,
    OrderStatus.SHIPPED: OrderStatus.DELIVERED,
}


@dataclass(frozen=True)
class Customer:
    name: str
    contact: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvalidDataError("Ім'я клієнта не може бути порожнім")
        if not self.contact.strip():
            raise InvalidDataError("Контактні дані клієнта не можуть бути порожніми")


@dataclass
class Order:
    order_id: int
    customer: Customer
    items: tuple[Purchase, ...]
    status: OrderStatus = OrderStatus.PROCESSING

    @property
    def total(self) -> Decimal:
        return sum((item.total for item in self.items), Decimal(0))


class OrderService:
    def __init__(self, purchases: PurchaseService) -> None:
        self._purchases = purchases
        self._orders: dict[int, Order] = {}
        self._next_id = 1

    def place_order(
        self, customer: Customer, requests: Sequence[PurchaseRequest]
    ) -> Order:
        items = self._purchases.purchase_many(requests)
        order = Order(self._next_id, customer, tuple(items))
        self._orders[order.order_id] = order
        self._next_id += 1
        return order

    def get_order(self, order_id: int) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise OrderNotFoundError(f"Замовлення {order_id} не знайдено")
        return order

    def orders_of(self, customer: Customer) -> list[Order]:
        return [o for o in self._orders.values() if o.customer == customer]

    def update_status(self, order_id: int, new_status: OrderStatus) -> None:
        order = self.get_order(order_id)
        if _NEXT_STATUS.get(order.status) is not new_status:
            raise InvalidStatusTransitionError(
                f"Перехід зі статусу '{order.status.value}' "
                f"у '{new_status.value}' неможливий"
            )
        order.status = new_status


# Функція 5: рейтинг книг

MIN_STARS = 1
MAX_STARS = 5


class RatingService:
    def __init__(self, inventory: Inventory) -> None:
        self._inventory = inventory
        self._ratings: dict[str, dict[str, int]] = {}

    def rate(self, isbn: str, user_id: str, stars: int) -> None:
        self._inventory.get_book(isbn)
        if not user_id.strip():
            raise InvalidDataError("Ідентифікатор користувача не може бути порожнім")
        # bool є підкласом int, тому перевіряємо окремо
        if isinstance(stars, bool) or not MIN_STARS <= stars <= MAX_STARS:
            raise InvalidRatingError(f"Оцінка має бути від {MIN_STARS} до {MAX_STARS}")
        self._ratings.setdefault(isbn, {})[user_id] = stars

    def count(self, isbn: str) -> int:
        self._inventory.get_book(isbn)
        return len(self._ratings.get(isbn, {}))

    def average(self, isbn: str) -> Decimal | None:
        self._inventory.get_book(isbn)
        votes = self._ratings.get(isbn)
        if not votes:
            return None
        mean = Decimal(sum(votes.values())) / len(votes)
        return mean.quantize(_CENT, rounding=ROUND_HALF_UP)
