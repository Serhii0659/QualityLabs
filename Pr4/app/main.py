from enum import StrEnum
from typing import Annotated

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field


class NotFoundError(LookupError):
    """Об'єкт не знайдено."""


class DuplicateIsbnError(ValueError):
    """Книга з таким ISBN вже існує."""


class StockError(ValueError):
    """Недостатньо примірників на складі."""


class OrderStatus(StrEnum):
    PROCESSING = "processing"
    SHIPPED = "shipped"
    COMPLETED = "completed"


class BookCreate(BaseModel):
    isbn: str = Field(min_length=1)
    title: str = Field(min_length=1)
    author: str = Field(min_length=1)
    price: float = Field(ge=0)
    quantity: int = Field(ge=0)
    description: str = ""


class Book(BookCreate):
    id: int


class BookUpdate(BaseModel):
    # ISBN та інші поля змінювати заборонено
    model_config = ConfigDict(extra="forbid")

    price: float | None = Field(default=None, ge=0)
    quantity: int | None = Field(default=None, ge=0)
    description: str | None = None


class OrderItemIn(BaseModel):
    book_id: int = Field(ge=1)
    quantity: int = Field(ge=1)


class OrderCreate(BaseModel):
    customer_id: int = Field(ge=1)
    items: list[OrderItemIn] = Field(min_length=1)


class OrderItem(BaseModel):
    book_id: int
    quantity: int
    price: float


class Order(BaseModel):
    id: int
    customer_id: int
    items: list[OrderItem]
    status: OrderStatus
    total: float


class StatusUpdate(BaseModel):
    status: OrderStatus


class Bookstore:
    """Сховище книг і замовлень у пам'яті."""

    def __init__(self) -> None:
        self._books: dict[int, Book] = {}
        self._orders: dict[int, Order] = {}
        self._next_book_id = 1
        self._next_order_id = 1

    def _find_book(self, book_id: int) -> Book:
        book = self._books.get(book_id)
        if book is None:
            raise NotFoundError(f"Книгу з ID {book_id} не знайдено")
        return book

    def _find_order(self, order_id: int) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise NotFoundError(f"Замовлення з ID {order_id} не знайдено")
        return order

    def add_book(
        self,
        isbn: str,
        title: str,
        author: str,
        price: float = 0.0,
        quantity: int = 0,
        description: str = "",
    ) -> Book:
        if any(book.isbn == isbn for book in self._books.values()):
            raise DuplicateIsbnError(f"Книга з ISBN {isbn} вже існує")
        book = Book(
            id=self._next_book_id,
            isbn=isbn,
            title=title,
            author=author,
            price=price,
            quantity=quantity,
            description=description,
        )
        self._books[book.id] = book
        self._next_book_id += 1
        return book.model_copy()

    def get_book(self, book_id: int) -> Book:
        return self._find_book(book_id).model_copy()

    def list_books(self) -> list[Book]:
        return [book.model_copy() for book in self._books.values()]

    def update_book(
        self,
        book_id: int,
        price: float | None = None,
        quantity: int | None = None,
        description: str | None = None,
    ) -> Book:
        book = self._find_book(book_id)
        changes: dict[str, object] = {}
        if price is not None:
            changes["price"] = price
        if quantity is not None:
            changes["quantity"] = quantity
        if description is not None:
            changes["description"] = description
        # Повторна валідація відхиляє некоректні значення
        updated = Book.model_validate({**book.model_dump(), **changes})
        self._books[book_id] = updated
        return updated.model_copy()

    def delete_book(self, book_id: int) -> None:
        self._find_book(book_id)
        del self._books[book_id]

    def delete_book_by_isbn(self, isbn: str) -> None:
        for book in self._books.values():
            if book.isbn == isbn:
                del self._books[book.id]
                return
        raise NotFoundError(f"Книгу з ISBN {isbn} не знайдено")

    def create_order(self, customer_id: int, items: list[OrderItemIn]) -> Order:
        if not items:
            raise ValueError("Замовлення має містити хоча б одну книгу")
        # Однакові книги в одному замовленні об'єднуються
        requested: dict[int, int] = {}
        for item in items:
            requested[item.book_id] = requested.get(item.book_id, 0) + item.quantity
        # Спочатку перевіряємо наявність, потім списуємо
        for book_id, quantity in requested.items():
            book = self._find_book(book_id)
            if book.quantity < quantity:
                raise StockError(
                    f"Недостатньо примірників книги {book_id}: "
                    f"доступно {book.quantity}, потрібно {quantity}"
                )
        order_items: list[OrderItem] = []
        for book_id, quantity in requested.items():
            book = self._books[book_id]
            book.quantity -= quantity
            order_items.append(
                OrderItem(book_id=book_id, quantity=quantity, price=book.price)
            )
        total = round(sum(item.price * item.quantity for item in order_items), 2)
        order = Order(
            id=self._next_order_id,
            customer_id=customer_id,
            items=order_items,
            status=OrderStatus.PROCESSING,
            total=total,
        )
        self._orders[order.id] = order
        self._next_order_id += 1
        return order.model_copy(deep=True)

    def get_order(self, order_id: int) -> Order:
        return self._find_order(order_id).model_copy(deep=True)

    def update_order_status(self, order_id: int, new_status: OrderStatus) -> Order:
        order = self._find_order(order_id)
        order.status = new_status
        return order.model_copy(deep=True)

    def list_customer_orders(self, customer_id: int) -> list[Order]:
        return [
            order.model_copy(deep=True)
            for order in self._orders.values()
            if order.customer_id == customer_id
        ]


app = FastAPI(title="Книжковий магазин")
_store = Bookstore()


def get_store() -> Bookstore:
    return _store


StoreDep = Annotated[Bookstore, Depends(get_store)]


@app.exception_handler(NotFoundError)
def handle_not_found(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)}
    )


@app.exception_handler(DuplicateIsbnError)
@app.exception_handler(StockError)
def handle_conflict(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)}
    )


@app.post("/books/", status_code=status.HTTP_201_CREATED)
def add_book(data: BookCreate, store: StoreDep) -> Book:
    return store.add_book(
        data.isbn,
        data.title,
        data.author,
        data.price,
        data.quantity,
        data.description,
    )


@app.get("/books/")
def get_books(store: StoreDep) -> list[Book]:
    return store.list_books()


@app.get("/books/{book_id}")
def get_book(book_id: int, store: StoreDep) -> Book:
    return store.get_book(book_id)


@app.put("/books/{book_id}")
def update_book(book_id: int, data: BookUpdate, store: StoreDep) -> Book:
    return store.update_book(book_id, data.price, data.quantity, data.description)


@app.delete("/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: int, store: StoreDep) -> None:
    store.delete_book(book_id)


@app.delete("/books/isbn/{isbn}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book_by_isbn(isbn: str, store: StoreDep) -> None:
    store.delete_book_by_isbn(isbn)


@app.post("/orders/", status_code=status.HTTP_201_CREATED)
def create_order(data: OrderCreate, store: StoreDep) -> Order:
    return store.create_order(data.customer_id, data.items)


@app.get("/orders/{order_id}")
def get_order(order_id: int, store: StoreDep) -> Order:
    return store.get_order(order_id)


@app.put("/orders/{order_id}")
def update_order_status(order_id: int, data: StatusUpdate, store: StoreDep) -> Order:
    return store.update_order_status(order_id, data.status)


@app.get("/customers/{customer_id}/orders")
def get_customer_orders(customer_id: int, store: StoreDep) -> list[Order]:
    return store.list_customer_orders(customer_id)
