import unittest
from typing import Any

from bookstore import BookNotFoundError, Bookstore, InsufficientStockError


def get_book(store: Bookstore, title: str) -> dict[str, Any]:
    """Шукає книгу, яка точно має існувати (звужує тип від None)."""
    book = store.search_book(title)
    assert book is not None
    return book


class TestAddBook(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Bookstore()

    def test_add_new_book(self) -> None:
        self.store.add_book("Python", "John Doe", 10.5, 3)
        self.assertEqual(
            self.store.search_book("Python"),
            {"title": "Python", "author": "John Doe", "price": 10.5, "quantity": 3},
        )

    def test_add_duplicate_increases_quantity(self) -> None:
        self.store.add_book("Python", "John Doe", 10.5, 3)
        self.store.add_book("Python", "John Doe", 10.5, 2)
        self.assertEqual(get_book(self.store, "Python")["quantity"], 5)

    def test_add_duplicate_does_not_create_second_record(self) -> None:
        self.store.add_book("Python", "John Doe", 10.5, 3)
        self.store.add_book("Python", "John Doe", 10.5, 2)
        self.assertAlmostEqual(self.store.inventory_value(), 52.5)

    def test_add_negative_quantity(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_book("Python", "John Doe", 10.5, -1)

    def test_add_negative_price(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_book("Python", "John Doe", -10, 1)

    def test_add_empty_title(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_book("", "John Doe", 10, 1)

    def test_add_none_title(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_book(None, "John Doe", 10, 1)  # pyright: ignore[reportArgumentType]

    def test_add_empty_author(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_book("Python", "", 10, 1)

    def test_add_non_integer_quantity(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_book("Python", "John Doe", 10, 1.5)  # pyright: ignore[reportArgumentType]

    def test_invalid_add_does_not_change_inventory(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_book("Python", "John Doe", -10, 1)
        self.assertIsNone(self.store.search_book("Python"))

    def test_add_zero_quantity_allowed(self) -> None:
        self.store.add_book("Python", "John Doe", 10, 0)
        self.assertEqual(get_book(self.store, "Python")["quantity"], 0)


class TestRemoveBook(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Bookstore()
        self.store.add_book("Python", "John Doe", 10, 3)

    def test_remove_existing_book(self) -> None:
        self.assertTrue(self.store.remove_book("Python"))
        self.assertIsNone(self.store.search_book("Python"))

    def test_remove_nonexistent_book_no_error(self) -> None:
        self.assertFalse(self.store.remove_book("Unknown"))

    def test_remove_twice(self) -> None:
        self.store.remove_book("Python")
        self.assertFalse(self.store.remove_book("Python"))

    def test_remove_none_title_no_error(self) -> None:
        self.assertFalse(self.store.remove_book(None))  # pyright: ignore[reportArgumentType]

    def test_remove_does_not_affect_other_books(self) -> None:
        self.store.add_book("Java", "Jane Doe", 20, 1)
        self.store.remove_book("Python")
        self.assertIsNotNone(self.store.search_book("Java"))


class TestSearchBook(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Bookstore()
        self.store.add_book("Python", "John Doe", 10.5, 3)

    def test_search_existing_book(self) -> None:
        book = get_book(self.store, "Python")
        self.assertEqual(book["title"], "Python")
        self.assertEqual(book["author"], "John Doe")
        self.assertEqual(book["price"], 10.5)
        self.assertEqual(book["quantity"], 3)

    def test_search_nonexistent_book_returns_none(self) -> None:
        self.assertIsNone(self.store.search_book("Unknown"))

    def test_search_empty_title(self) -> None:
        with self.assertRaises(ValueError):
            self.store.search_book("")

    def test_search_whitespace_title(self) -> None:
        with self.assertRaises(ValueError):
            self.store.search_book("   ")

    def test_search_none_title(self) -> None:
        with self.assertRaises(ValueError):
            self.store.search_book(None)  # pyright: ignore[reportArgumentType]

    def test_search_returns_copy(self) -> None:
        book = get_book(self.store, "Python")
        book["quantity"] = 999
        self.assertEqual(get_book(self.store, "Python")["quantity"], 3)


class TestPurchaseBook(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Bookstore()
        self.store.add_book("Python", "John Doe", 10.5, 5)

    def test_purchase_returns_total_price(self) -> None:
        self.assertAlmostEqual(self.store.purchase_book("Python", 3), 31.5)

    def test_purchase_decreases_quantity(self) -> None:
        self.store.purchase_book("Python", 3)
        self.assertEqual(get_book(self.store, "Python")["quantity"], 2)

    def test_purchase_all_stock(self) -> None:
        self.store.purchase_book("Python", 5)
        self.assertEqual(get_book(self.store, "Python")["quantity"], 0)

    def test_purchase_more_than_stock(self) -> None:
        with self.assertRaises(InsufficientStockError):
            self.store.purchase_book("Python", 6)

    def test_failed_purchase_keeps_quantity(self) -> None:
        with self.assertRaises(InsufficientStockError):
            self.store.purchase_book("Python", 6)
        self.assertEqual(get_book(self.store, "Python")["quantity"], 5)

    def test_purchase_nonexistent_book(self) -> None:
        with self.assertRaises(BookNotFoundError):
            self.store.purchase_book("Unknown", 1)

    def test_purchase_with_zero_stock(self) -> None:
        self.store.purchase_book("Python", 5)
        with self.assertRaises(InsufficientStockError):
            self.store.purchase_book("Python", 1)

    def test_purchase_zero_quantity(self) -> None:
        with self.assertRaises(ValueError):
            self.store.purchase_book("Python", 0)

    def test_purchase_negative_quantity(self) -> None:
        with self.assertRaises(ValueError):
            self.store.purchase_book("Python", -2)

    def test_purchase_empty_title(self) -> None:
        with self.assertRaises(ValueError):
            self.store.purchase_book("", 1)


class TestInventoryValue(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Bookstore()

    def test_empty_inventory(self) -> None:
        self.assertEqual(self.store.inventory_value(), 0)

    def test_inventory_value_sum(self) -> None:
        self.store.add_book("Python", "John Doe", 10.5, 2)
        self.store.add_book("Java", "Jane Doe", 20, 3)
        self.assertAlmostEqual(self.store.inventory_value(), 81.0)

    def test_value_after_purchase(self) -> None:
        self.store.add_book("Python", "John Doe", 10, 5)
        self.store.purchase_book("Python", 2)
        self.assertAlmostEqual(self.store.inventory_value(), 30.0)

    def test_value_after_remove(self) -> None:
        self.store.add_book("Python", "John Doe", 10, 5)
        self.store.add_book("Java", "Jane Doe", 20, 1)
        self.store.remove_book("Python")
        self.assertAlmostEqual(self.store.inventory_value(), 20.0)

    def test_value_with_zero_stock_book(self) -> None:
        self.store.add_book("Python", "John Doe", 10, 0)
        self.assertEqual(self.store.inventory_value(), 0)


if __name__ == "__main__":
    unittest.main()
