import unittest
from decimal import Decimal

from bookstore import (
    Book,
    BookNotFoundError,
    Customer,
    DiscountConflictError,
    DiscountManager,
    DuplicateIsbnError,
    InsufficientStockError,
    InvalidDataError,
    InvalidRatingError,
    InvalidStatusTransitionError,
    Inventory,
    OrderNotFoundError,
    OrderService,
    OrderStatus,
    PurchaseRequest,
    PurchaseService,
    RatingService,
)


def make_book(
    isbn: str = "978-3-16-148410-0",
    price: str = "100.00",
    category: str = "",
) -> Book:
    return Book(
        title="Кобзар",
        author="Тарас Шевченко",
        isbn=isbn,
        price=Decimal(price),
        category=category,
    )


class AddBookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = Inventory()

    def test_add_book_with_all_data(self) -> None:
        book = make_book()
        self.inventory.add_book(book, 5)
        self.assertEqual(self.inventory.get_book(book.isbn), book)
        self.assertEqual(self.inventory.get_quantity(book.isbn), 5)

    def test_add_books_with_different_isbn(self) -> None:
        self.inventory.add_book(make_book("111"), 1)
        self.inventory.add_book(make_book("222"), 2)
        self.assertTrue(self.inventory.has_book("111"))
        self.assertTrue(self.inventory.has_book("222"))

    def test_duplicate_isbn_raises_error(self) -> None:
        book = make_book()
        self.inventory.add_book(book, 5)
        with self.assertRaises(DuplicateIsbnError):
            self.inventory.add_book(book, 3)

    def test_duplicate_isbn_keeps_original_quantity(self) -> None:
        book = make_book()
        self.inventory.add_book(book, 5)
        with self.assertRaises(DuplicateIsbnError):
            self.inventory.add_book(book, 3)
        self.assertEqual(self.inventory.get_quantity(book.isbn), 5)

    def test_zero_quantity_is_allowed(self) -> None:
        book = make_book()
        self.inventory.add_book(book, 0)
        self.assertEqual(self.inventory.get_quantity(book.isbn), 0)

    def test_negative_quantity_raises_error(self) -> None:
        book = make_book()
        with self.assertRaises(InvalidDataError):
            self.inventory.add_book(book, -1)
        self.assertFalse(self.inventory.has_book(book.isbn))

    def test_empty_required_fields_raise_error(self) -> None:
        price = Decimal(10)
        cases = (
            ("", "Автор", "123", price),
            ("Назва", "  ", "123", price),
            ("Назва", "Автор", "", price),
        )
        for title, author, isbn, book_price in cases:
            with (
                self.subTest(title=title, author=author, isbn=isbn),
                self.assertRaises(InvalidDataError),
            ):
                Book(title, author, isbn, book_price)

    def test_non_positive_price_raises_error(self) -> None:
        for price in (Decimal(0), Decimal(-5)):
            with self.subTest(price=price), self.assertRaises(InvalidDataError):
                Book("Назва", "Автор", "123", price)

    def test_unknown_book_raises_error(self) -> None:
        with self.assertRaises(BookNotFoundError):
            self.inventory.get_book("000")
        with self.assertRaises(BookNotFoundError):
            self.inventory.get_quantity("000")


class RemoveStockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = Inventory()
        self.book = make_book()
        self.inventory.add_book(self.book, 5)

    def test_remove_stock_decreases_quantity(self) -> None:
        self.inventory.remove_stock(self.book.isbn, 2)
        self.assertEqual(self.inventory.get_quantity(self.book.isbn), 3)

    def test_remove_more_than_available_raises_error(self) -> None:
        with self.assertRaises(InsufficientStockError):
            self.inventory.remove_stock(self.book.isbn, 6)
        self.assertEqual(self.inventory.get_quantity(self.book.isbn), 5)

    def test_remove_non_positive_quantity_raises_error(self) -> None:
        for quantity in (0, -1):
            with self.subTest(quantity=quantity), self.assertRaises(InvalidDataError):
                self.inventory.remove_stock(self.book.isbn, quantity)


class PurchaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = Inventory()
        self.first = make_book("111", "100.00")
        self.second = make_book("222", "50.00")
        self.inventory.add_book(self.first, 10)
        self.inventory.add_book(self.second, 4)
        self.service = PurchaseService(self.inventory)

    def test_purchase_decreases_quantity(self) -> None:
        self.service.purchase("111", 3)
        self.assertEqual(self.inventory.get_quantity("111"), 7)

    def test_purchase_of_all_copies_leaves_zero(self) -> None:
        self.service.purchase("222", 4)
        self.assertEqual(self.inventory.get_quantity("222"), 0)

    def test_purchase_is_recorded(self) -> None:
        purchase = self.service.purchase("111", 2)
        self.assertEqual(self.service.history, (purchase,))
        self.assertEqual(purchase.isbn, "111")
        self.assertEqual(purchase.quantity, 2)
        self.assertEqual(purchase.unit_price, Decimal("100.00"))
        self.assertEqual(purchase.total, Decimal("200.00"))

    def test_insufficient_stock_raises_error(self) -> None:
        with self.assertRaises(InsufficientStockError):
            self.service.purchase("222", 5)

    def test_failed_purchase_changes_nothing(self) -> None:
        with self.assertRaises(InsufficientStockError):
            self.service.purchase("222", 5)
        self.assertEqual(self.inventory.get_quantity("222"), 4)
        self.assertEqual(self.service.history, ())

    def test_unknown_book_raises_error(self) -> None:
        with self.assertRaises(BookNotFoundError):
            self.service.purchase("000", 1)

    def test_non_positive_quantity_raises_error(self) -> None:
        for quantity in (0, -2):
            with self.subTest(quantity=quantity), self.assertRaises(InvalidDataError):
                self.service.purchase("111", quantity)

    def test_purchase_many_updates_all_books(self) -> None:
        purchases = self.service.purchase_many(
            [PurchaseRequest("111", 2), PurchaseRequest("222", 1)]
        )
        self.assertEqual(len(purchases), 2)
        self.assertEqual(self.inventory.get_quantity("111"), 8)
        self.assertEqual(self.inventory.get_quantity("222"), 3)
        self.assertEqual(len(self.service.history), 2)

    def test_purchase_many_is_atomic(self) -> None:
        requests = [PurchaseRequest("111", 2), PurchaseRequest("222", 5)]
        with self.assertRaises(InsufficientStockError):
            self.service.purchase_many(requests)
        self.assertEqual(self.inventory.get_quantity("111"), 10)
        self.assertEqual(self.service.history, ())

    def test_purchase_many_sums_repeated_isbn(self) -> None:
        requests = [PurchaseRequest("222", 3), PurchaseRequest("222", 2)]
        with self.assertRaises(InsufficientStockError):
            self.service.purchase_many(requests)
        self.assertEqual(self.inventory.get_quantity("222"), 4)

    def test_empty_request_list_raises_error(self) -> None:
        with self.assertRaises(InvalidDataError):
            self.service.purchase_many([])


class PurchaseWithDiscountTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = Inventory()
        self.inventory.add_book(make_book("111", "200.00"), 10)
        self.discounts = DiscountManager(self.inventory)
        self.service = PurchaseService(self.inventory, self.discounts)

    def test_purchase_uses_discounted_price(self) -> None:
        self.discounts.add_book_discount("111", Decimal(25))
        purchase = self.service.purchase("111", 2)
        self.assertEqual(purchase.unit_price, Decimal("150.00"))
        self.assertEqual(purchase.total, Decimal("300.00"))

    def test_purchase_without_discount_uses_base_price(self) -> None:
        purchase = self.service.purchase("111", 1)
        self.assertEqual(purchase.unit_price, Decimal("200.00"))


class OrderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = Inventory()
        self.inventory.add_book(make_book("111", "100.00"), 10)
        self.inventory.add_book(make_book("222", "50.50"), 3)
        self.purchases = PurchaseService(self.inventory)
        self.service = OrderService(self.purchases)
        self.customer = Customer("Іван Петренко", "ivan@example.com")

    def test_order_is_associated_with_customer(self) -> None:
        order = self.service.place_order(self.customer, [PurchaseRequest("111", 1)])
        self.assertEqual(order.customer, self.customer)
        self.assertEqual(self.service.orders_of(self.customer), [order])

    def test_order_contains_correct_details(self) -> None:
        order = self.service.place_order(
            self.customer,
            [PurchaseRequest("111", 2), PurchaseRequest("222", 1)],
        )
        self.assertEqual([i.isbn for i in order.items], ["111", "222"])
        self.assertEqual([i.quantity for i in order.items], [2, 1])
        self.assertEqual(order.total, Decimal("250.50"))
        self.assertEqual(order.customer.name, "Іван Петренко")
        self.assertEqual(order.customer.contact, "ivan@example.com")

    def test_order_decreases_inventory_and_is_recorded(self) -> None:
        self.service.place_order(self.customer, [PurchaseRequest("111", 4)])
        self.assertEqual(self.inventory.get_quantity("111"), 6)
        self.assertEqual(len(self.purchases.history), 1)

    def test_new_order_is_processing(self) -> None:
        order = self.service.place_order(self.customer, [PurchaseRequest("111", 1)])
        self.assertIs(order.status, OrderStatus.PROCESSING)

    def test_order_ids_are_unique(self) -> None:
        first = self.service.place_order(self.customer, [PurchaseRequest("111", 1)])
        second = self.service.place_order(self.customer, [PurchaseRequest("111", 1)])
        self.assertNotEqual(first.order_id, second.order_id)

    def test_orders_of_other_customer_are_not_returned(self) -> None:
        other = Customer("Олена Коваль", "380501234567")
        self.service.place_order(self.customer, [PurchaseRequest("111", 1)])
        self.assertEqual(self.service.orders_of(other), [])

    def test_get_order_returns_saved_order(self) -> None:
        order = self.service.place_order(self.customer, [PurchaseRequest("111", 1)])
        self.assertIs(self.service.get_order(order.order_id), order)

    def test_get_unknown_order_raises_error(self) -> None:
        with self.assertRaises(OrderNotFoundError):
            self.service.get_order(999)

    def test_failed_order_is_not_saved(self) -> None:
        requests = [PurchaseRequest("222", 10)]
        with self.assertRaises(InsufficientStockError):
            self.service.place_order(self.customer, requests)
        self.assertEqual(self.service.orders_of(self.customer), [])
        order = self.service.place_order(self.customer, [PurchaseRequest("222", 1)])
        self.assertEqual(order.order_id, 1)

    def test_order_with_unknown_book_raises_error(self) -> None:
        requests = [PurchaseRequest("000", 1)]
        with self.assertRaises(BookNotFoundError):
            self.service.place_order(self.customer, requests)


class StatusTests(unittest.TestCase):
    def setUp(self) -> None:
        inventory = Inventory()
        inventory.add_book(make_book("111"), 10)
        self.service = OrderService(PurchaseService(inventory))
        customer = Customer("Іван Петренко", "ivan@example.com")
        self.order = self.service.place_order(customer, [PurchaseRequest("111", 1)])

    def test_status_moves_through_all_stages(self) -> None:
        self.service.update_status(self.order.order_id, OrderStatus.SHIPPED)
        self.assertIs(self.order.status, OrderStatus.SHIPPED)
        self.service.update_status(self.order.order_id, OrderStatus.DELIVERED)
        self.assertIs(self.order.status, OrderStatus.DELIVERED)

    def test_skipping_status_raises_error(self) -> None:
        with self.assertRaises(InvalidStatusTransitionError):
            self.service.update_status(self.order.order_id, OrderStatus.DELIVERED)
        self.assertIs(self.order.status, OrderStatus.PROCESSING)

    def test_going_back_raises_error(self) -> None:
        self.service.update_status(self.order.order_id, OrderStatus.SHIPPED)
        with self.assertRaises(InvalidStatusTransitionError):
            self.service.update_status(self.order.order_id, OrderStatus.PROCESSING)

    def test_delivered_order_cannot_change(self) -> None:
        self.service.update_status(self.order.order_id, OrderStatus.SHIPPED)
        self.service.update_status(self.order.order_id, OrderStatus.DELIVERED)
        with self.assertRaises(InvalidStatusTransitionError):
            self.service.update_status(self.order.order_id, OrderStatus.SHIPPED)

    def test_update_status_of_unknown_order_raises_error(self) -> None:
        with self.assertRaises(OrderNotFoundError):
            self.service.update_status(999, OrderStatus.SHIPPED)


class CustomerTests(unittest.TestCase):
    def test_empty_name_raises_error(self) -> None:
        with self.assertRaises(InvalidDataError):
            Customer(" ", "ivan@example.com")

    def test_empty_contact_raises_error(self) -> None:
        with self.assertRaises(InvalidDataError):
            Customer("Іван Петренко", "")


class DiscountTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = Inventory()
        self.inventory.add_book(make_book("111", "200.00", "Фантастика"), 5)
        self.inventory.add_book(make_book("222", "99.99", "Поезія"), 5)
        self.manager = DiscountManager(self.inventory)

    def test_price_without_discount_is_unchanged(self) -> None:
        self.assertEqual(self.manager.final_price("111"), Decimal("200.00"))
        self.assertIsNone(self.manager.get_discount("111"))

    def test_book_discount_reduces_price(self) -> None:
        self.manager.add_book_discount("111", Decimal(10))
        self.assertEqual(self.manager.final_price("111"), Decimal("180.00"))

    def test_book_discount_does_not_affect_other_books(self) -> None:
        self.manager.add_book_discount("111", Decimal(10))
        self.assertEqual(self.manager.final_price("222"), Decimal("99.99"))

    def test_category_discount_applies_to_books_of_category(self) -> None:
        self.manager.add_category_discount("Фантастика", Decimal(50))
        self.assertEqual(self.manager.final_price("111"), Decimal("100.00"))
        self.assertEqual(self.manager.final_price("222"), Decimal("99.99"))

    def test_category_discount_applies_to_book_added_later(self) -> None:
        self.manager.add_category_discount("Історія", Decimal(20))
        self.inventory.add_book(make_book("333", "100.00", "Історія"), 1)
        self.assertEqual(self.manager.final_price("333"), Decimal("80.00"))

    def test_only_one_discount_per_book_is_applied(self) -> None:
        self.manager.add_category_discount("Фантастика", Decimal(50))
        self.manager.add_book_discount("111", Decimal(10))
        self.assertEqual(self.manager.final_price("111"), Decimal("180.00"))

    def test_final_price_is_rounded_to_cents(self) -> None:
        self.manager.add_book_discount("222", Decimal(15))
        self.assertEqual(self.manager.final_price("222"), Decimal("84.99"))

    def test_second_book_discount_raises_error(self) -> None:
        self.manager.add_book_discount("111", Decimal(10))
        with self.assertRaises(DiscountConflictError):
            self.manager.add_book_discount("111", Decimal(20))
        self.assertEqual(self.manager.final_price("111"), Decimal("180.00"))

    def test_second_category_discount_raises_error(self) -> None:
        self.manager.add_category_discount("Поезія", Decimal(10))
        with self.assertRaises(DiscountConflictError):
            self.manager.add_category_discount("Поезія", Decimal(30))

    def test_invalid_percent_raises_error(self) -> None:
        for percent in ("0", "-5", "91", "100"):
            with self.subTest(percent=percent), self.assertRaises(InvalidDataError):
                self.manager.add_book_discount("111", Decimal(percent))

    def test_maximum_percent_is_allowed(self) -> None:
        self.manager.add_book_discount("111", Decimal(90))
        self.assertEqual(self.manager.final_price("111"), Decimal("20.00"))

    def test_discount_for_unknown_book_raises_error(self) -> None:
        with self.assertRaises(BookNotFoundError):
            self.manager.add_book_discount("000", Decimal(10))

    def test_empty_category_raises_error(self) -> None:
        with self.assertRaises(InvalidDataError):
            self.manager.add_category_discount(" ", Decimal(10))


class RatingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = Inventory()
        self.inventory.add_book(make_book("111"), 5)
        self.inventory.add_book(make_book("222"), 5)
        self.service = RatingService(self.inventory)

    def test_book_without_ratings_has_no_average(self) -> None:
        self.assertIsNone(self.service.average("111"))
        self.assertEqual(self.service.count("111"), 0)

    def test_boundary_ratings_are_accepted(self) -> None:
        self.service.rate("111", "u1", 1)
        self.service.rate("111", "u2", 5)
        self.assertEqual(self.service.count("111"), 2)

    def test_rating_below_minimum_raises_error(self) -> None:
        with self.assertRaises(InvalidRatingError):
            self.service.rate("111", "u1", 0)

    def test_rating_above_maximum_raises_error(self) -> None:
        with self.assertRaises(InvalidRatingError):
            self.service.rate("111", "u1", 6)

    def test_boolean_rating_raises_error(self) -> None:
        with self.assertRaises(InvalidRatingError):
            self.service.rate("111", "u1", True)

    def test_invalid_rating_is_not_saved(self) -> None:
        with self.assertRaises(InvalidRatingError):
            self.service.rate("111", "u1", 7)
        self.assertEqual(self.service.count("111"), 0)

    def test_average_of_several_ratings(self) -> None:
        for user, stars in (("u1", 4), ("u2", 2)):
            self.service.rate("111", user, stars)
        self.assertEqual(self.service.average("111"), Decimal("3.00"))

    def test_average_is_rounded_to_two_decimals(self) -> None:
        for user, stars in (("u1", 4), ("u2", 5), ("u3", 5)):
            self.service.rate("111", user, stars)
        self.assertEqual(self.service.average("111"), Decimal("4.67"))

    def test_repeated_rating_replaces_previous(self) -> None:
        self.service.rate("111", "u1", 1)
        self.service.rate("111", "u1", 5)
        self.assertEqual(self.service.count("111"), 1)
        self.assertEqual(self.service.average("111"), Decimal("5.00"))

    def test_ratings_of_books_are_independent(self) -> None:
        self.service.rate("111", "u1", 5)
        self.service.rate("222", "u1", 1)
        self.assertEqual(self.service.average("111"), Decimal("5.00"))
        self.assertEqual(self.service.average("222"), Decimal("1.00"))

    def test_rating_unknown_book_raises_error(self) -> None:
        with self.assertRaises(BookNotFoundError):
            self.service.rate("000", "u1", 3)

    def test_empty_user_raises_error(self) -> None:
        with self.assertRaises(InvalidDataError):
            self.service.rate("111", " ", 3)

    def test_average_of_unknown_book_raises_error(self) -> None:
        with self.assertRaises(BookNotFoundError):
            self.service.average("000")


if __name__ == "__main__":
    unittest.main()
