from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import (
    Bookstore,
    DuplicateIsbnError,
    NotFoundError,
    OrderItemIn,
    OrderStatus,
    StockError,
    app,
    get_store,
)


@pytest.fixture
def store() -> Bookstore:
    return Bookstore()


@pytest.fixture
def client(store: Bookstore) -> Iterator[TestClient]:
    # Кожен тест працює з чистим сховищем
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def book_payload(**extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "isbn": "123456789",
        "title": "Python Programming",
        "author": "John Doe",
        "price": 10.5,
        "quantity": 5,
        "description": "Підручник",
    }
    payload.update(extra)
    return payload


def create_book(client: TestClient, isbn: str = "123456789", **extra: object) -> Any:
    response = client.post("/books/", json=book_payload(isbn=isbn, **extra))
    assert response.status_code == 201
    return response.json()


def order_payload(customer_id: int, *items: tuple[int, int]) -> dict[str, object]:
    return {
        "customer_id": customer_id,
        "items": [{"book_id": book, "quantity": qty} for book, qty in items],
    }


def create_order(client: TestClient, customer_id: int, *items: tuple[int, int]) -> Any:
    response = client.post("/orders/", json=order_payload(customer_id, *items))
    assert response.status_code == 201
    return response.json()


# Керування інвентарем: клас Bookstore


def test_store_add_new_book(store: Bookstore) -> None:
    result = store.add_book("123456789", "Python Programming", "John Doe")
    assert result
    assert store.get_book(result.id).isbn == "123456789"


def test_store_duplicate_isbn(store: Bookstore) -> None:
    store.add_book("123456789", "Python Programming", "John Doe")
    with pytest.raises(DuplicateIsbnError):
        store.add_book("123456789", "Another Book", "Jane Doe")
    assert len(store.list_books()) == 1


def test_store_duplicate_isbn_is_value_error(store: Bookstore) -> None:
    store.add_book("123456789", "Python Programming", "John Doe")
    with pytest.raises(ValueError, match="123456789"):
        store.add_book("123456789", "Another Book", "Jane Doe")


def test_store_update_book(store: Bookstore) -> None:
    book = store.add_book("1", "Title", "Author", 10.0, 3)
    updated = store.update_book(book.id, price=20.0, quantity=7, description="Новий")
    assert (updated.price, updated.quantity, updated.description) == (20.0, 7, "Новий")
    assert updated.isbn == "1"
    assert store.get_book(book.id) == updated


def test_store_partial_update_keeps_other_fields(store: Bookstore) -> None:
    book = store.add_book("1", "Title", "Author", 10.0, 3, "Опис")
    updated = store.update_book(book.id, price=15.0)
    assert (updated.quantity, updated.description) == (3, "Опис")


def test_store_update_negative_price(store: Bookstore) -> None:
    book = store.add_book("1", "Title", "Author", 10.0, 3)
    with pytest.raises(ValueError, match="price"):
        store.update_book(book.id, price=-1.0)
    assert store.get_book(book.id).price == 10.0


def test_store_update_unknown_book(store: Bookstore) -> None:
    with pytest.raises(NotFoundError):
        store.update_book(99, price=1.0)


def test_store_delete_by_id(store: Bookstore) -> None:
    book = store.add_book("1", "Title", "Author")
    store.delete_book(book.id)
    assert store.list_books() == []


def test_store_delete_by_isbn(store: Bookstore) -> None:
    store.add_book("1", "Title", "Author")
    store.delete_book_by_isbn("1")
    assert store.list_books() == []


def test_store_delete_unknown_book(store: Bookstore) -> None:
    with pytest.raises(NotFoundError):
        store.delete_book(99)
    with pytest.raises(NotFoundError):
        store.delete_book_by_isbn("missing")


# Обробка покупок: клас Bookstore


def test_store_purchase_succeeds(store: Bookstore) -> None:
    book = store.add_book("1", "Title", "Author", 10.0, 5)
    order = store.create_order(1, [OrderItemIn(book_id=book.id, quantity=2)])
    assert order.total == pytest.approx(20.0)
    assert order.status == OrderStatus.PROCESSING


def test_store_purchase_decreases_quantity(store: Bookstore) -> None:
    book = store.add_book("1", "Title", "Author", 10.0, 5)
    store.create_order(1, [OrderItemIn(book_id=book.id, quantity=2)])
    assert store.get_book(book.id).quantity == 3


def test_store_purchase_all_stock(store: Bookstore) -> None:
    book = store.add_book("1", "Title", "Author", 10.0, 5)
    store.create_order(1, [OrderItemIn(book_id=book.id, quantity=5)])
    assert store.get_book(book.id).quantity == 0


def test_store_purchase_more_than_stock(store: Bookstore) -> None:
    book = store.add_book("1", "Title", "Author", 10.0, 5)
    with pytest.raises(StockError):
        store.create_order(1, [OrderItemIn(book_id=book.id, quantity=6)])
    assert store.get_book(book.id).quantity == 5


def test_store_purchase_unknown_book(store: Bookstore) -> None:
    with pytest.raises(NotFoundError):
        store.create_order(1, [OrderItemIn(book_id=99, quantity=1)])


def test_store_purchase_is_atomic(store: Bookstore) -> None:
    first = store.add_book("1", "First", "Author", 10.0, 5)
    second = store.add_book("2", "Second", "Author", 10.0, 1)
    items = [
        OrderItemIn(book_id=first.id, quantity=2),
        OrderItemIn(book_id=second.id, quantity=2),
    ]
    with pytest.raises(StockError):
        store.create_order(1, items)
    assert store.get_book(first.id).quantity == 5
    assert store.list_customer_orders(1) == []


def test_store_purchase_merges_same_book(store: Bookstore) -> None:
    book = store.add_book("1", "Title", "Author", 10.0, 3)
    items = [
        OrderItemIn(book_id=book.id, quantity=2),
        OrderItemIn(book_id=book.id, quantity=2),
    ]
    with pytest.raises(StockError):
        store.create_order(1, items)


def test_store_order_without_items(store: Bookstore) -> None:
    with pytest.raises(ValueError, match="хоча б одну"):
        store.create_order(1, [])


# Відстеження замовлень: клас Bookstore


def test_store_order_ids_are_unique(store: Bookstore) -> None:
    book = store.add_book("1", "Title", "Author", 10.0, 5)
    items = [OrderItemIn(book_id=book.id, quantity=1)]
    ids = {store.create_order(1, items).id for _ in range(3)}
    assert len(ids) == 3


def test_store_order_contains_details(store: Bookstore) -> None:
    book = store.add_book("1", "Title", "Author", 12.5, 5)
    order = store.create_order(7, [OrderItemIn(book_id=book.id, quantity=2)])
    assert order.customer_id == 7
    assert [(i.book_id, i.quantity, i.price) for i in order.items] == [
        (book.id, 2, 12.5)
    ]


def test_store_change_order_status(store: Bookstore) -> None:
    book = store.add_book("1", "Title", "Author", 10.0, 5)
    order = store.create_order(1, [OrderItemIn(book_id=book.id, quantity=1)])
    updated = store.update_order_status(order.id, OrderStatus.SHIPPED)
    assert updated.status == OrderStatus.SHIPPED
    assert store.get_order(order.id).status == OrderStatus.SHIPPED


def test_store_unknown_order(store: Bookstore) -> None:
    with pytest.raises(NotFoundError):
        store.get_order(99)
    with pytest.raises(NotFoundError):
        store.update_order_status(99, OrderStatus.SHIPPED)


def test_store_customer_orders(store: Bookstore) -> None:
    book = store.add_book("1", "Title", "Author", 10.0, 10)
    items = [OrderItemIn(book_id=book.id, quantity=1)]
    first = store.create_order(1, items)
    second = store.create_order(1, items)
    store.create_order(2, items)
    assert [o.id for o in store.list_customer_orders(1)] == [first.id, second.id]
    assert store.list_customer_orders(3) == []


# Керування інвентарем: API


def test_api_add_book(client: TestClient) -> None:
    created = create_book(client)
    assert created["id"] == 1
    response = client.get(f"/books/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_api_duplicate_isbn(client: TestClient) -> None:
    create_book(client)
    response = client.post("/books/", json=book_payload(title="Another Book"))
    assert response.status_code == 409
    assert len(client.get("/books/").json()) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"price": -1},
        {"quantity": -1},
        {"isbn": ""},
        {"title": ""},
        {"price": "abc"},
    ],
)
def test_api_add_book_invalid_data(
    client: TestClient, changes: dict[str, object]
) -> None:
    response = client.post("/books/", json=book_payload(**changes))
    assert response.status_code == 422


def test_api_add_book_missing_field(client: TestClient) -> None:
    payload = book_payload()
    del payload["author"]
    assert client.post("/books/", json=payload).status_code == 422


def test_api_get_all_books(client: TestClient) -> None:
    assert client.get("/books/").json() == []
    create_book(client, "1")
    create_book(client, "2")
    response = client.get("/books/")
    assert [b["isbn"] for b in response.json()] == ["1", "2"]


def test_api_get_unknown_book(client: TestClient) -> None:
    assert client.get("/books/99").status_code == 404


def test_api_update_book(client: TestClient) -> None:
    book = create_book(client)
    response = client.put(
        f"/books/{book['id']}",
        json={"price": 20.0, "quantity": 9, "description": "Оновлено"},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["price"], body["quantity"], body["description"]) == (
        20.0,
        9,
        "Оновлено",
    )
    assert client.get(f"/books/{book['id']}").json() == body


def test_api_update_cannot_change_isbn(client: TestClient) -> None:
    book = create_book(client)
    response = client.put(f"/books/{book['id']}", json={"isbn": "999"})
    assert response.status_code == 422
    assert client.get(f"/books/{book['id']}").json()["isbn"] == "123456789"


def test_api_update_invalid_price(client: TestClient) -> None:
    book = create_book(client)
    response = client.put(f"/books/{book['id']}", json={"price": -5})
    assert response.status_code == 422


def test_api_update_unknown_book(client: TestClient) -> None:
    assert client.put("/books/99", json={"price": 1}).status_code == 404


def test_api_delete_book_by_id(client: TestClient) -> None:
    book = create_book(client)
    assert client.delete(f"/books/{book['id']}").status_code == 204
    assert client.get(f"/books/{book['id']}").status_code == 404


def test_api_delete_book_by_isbn(client: TestClient) -> None:
    create_book(client)
    assert client.delete("/books/isbn/123456789").status_code == 204
    assert client.get("/books/").json() == []


def test_api_delete_unknown_book(client: TestClient) -> None:
    # Відсутня книга дає 404, а не внутрішню помилку сервера
    assert client.delete("/books/99").status_code == 404
    assert client.delete("/books/isbn/missing").status_code == 404


# Обробка покупок: API


def test_api_purchase_succeeds(client: TestClient) -> None:
    book = create_book(client, price=10.0, quantity=5)
    order = create_order(client, 1, (book["id"], 2))
    assert order["total"] == pytest.approx(20.0)
    assert order["status"] == "processing"


def test_api_purchase_decreases_quantity(client: TestClient) -> None:
    book = create_book(client, quantity=5)
    create_order(client, 1, (book["id"], 2))
    assert client.get(f"/books/{book['id']}").json()["quantity"] == 3


def test_api_purchase_more_than_stock(client: TestClient) -> None:
    book = create_book(client, quantity=5)
    response = client.post("/orders/", json=order_payload(1, (book["id"], 6)))
    assert response.status_code == 409
    assert client.get(f"/books/{book['id']}").json()["quantity"] == 5


def test_api_purchase_unknown_book(client: TestClient) -> None:
    response = client.post("/orders/", json=order_payload(1, (99, 1)))
    assert response.status_code == 404


def test_api_purchase_out_of_stock(client: TestClient) -> None:
    book = create_book(client, quantity=0)
    response = client.post("/orders/", json=order_payload(1, (book["id"], 1)))
    assert response.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"customer_id": 1, "items": []},
        {"customer_id": 1, "items": [{"book_id": 1, "quantity": 0}]},
        {"customer_id": 0, "items": [{"book_id": 1, "quantity": 1}]},
        {"items": [{"book_id": 1, "quantity": 1}]},
    ],
)
def test_api_order_invalid_data(client: TestClient, payload: dict[str, object]) -> None:
    assert client.post("/orders/", json=payload).status_code == 422


# Відстеження замовлень: API


def test_api_order_ids_are_unique(client: TestClient) -> None:
    book = create_book(client, quantity=10)
    ids = {create_order(client, 1, (book["id"], 1))["id"] for _ in range(3)}
    assert len(ids) == 3


def test_api_order_contains_details(client: TestClient) -> None:
    book = create_book(client, price=12.5, quantity=10)
    order = create_order(client, 7, (book["id"], 2))
    fetched = client.get(f"/orders/{order['id']}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["customer_id"] == 7
    assert body["items"] == [{"book_id": book["id"], "quantity": 2, "price": 12.5}]


def test_api_get_unknown_order(client: TestClient) -> None:
    assert client.get("/orders/99").status_code == 404


@pytest.mark.parametrize("new_status", ["shipped", "completed", "processing"])
def test_api_change_order_status(client: TestClient, new_status: str) -> None:
    book = create_book(client)
    order = create_order(client, 1, (book["id"], 1))
    response = client.put(f"/orders/{order['id']}", json={"status": new_status})
    assert response.status_code == 200
    assert client.get(f"/orders/{order['id']}").json()["status"] == new_status


def test_api_invalid_order_status(client: TestClient) -> None:
    book = create_book(client)
    order = create_order(client, 1, (book["id"], 1))
    response = client.put(f"/orders/{order['id']}", json={"status": "unknown"})
    assert response.status_code == 422


def test_api_change_status_of_unknown_order(client: TestClient) -> None:
    response = client.put("/orders/99", json={"status": "shipped"})
    assert response.status_code == 404


def test_api_customer_orders(client: TestClient) -> None:
    book = create_book(client, quantity=10)
    first = create_order(client, 1, (book["id"], 1))
    second = create_order(client, 1, (book["id"], 2))
    create_order(client, 2, (book["id"], 1))
    response = client.get("/customers/1/orders")
    assert response.status_code == 200
    assert [o["id"] for o in response.json()] == [first["id"], second["id"]]
    assert client.get("/customers/3/orders").json() == []
