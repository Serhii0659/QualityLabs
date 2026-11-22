"""Автоматизовані UI-тести сайту the-internet.herokuapp.com (Selenium, Firefox і Chromium)."""

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

type Locator = tuple[str, str]

PROJECT_DIR = Path(__file__).parent
BASE_URL = "https://the-internet.herokuapp.com"
TIMEOUT = 10

VALID_USERNAME = "tomsmith"
VALID_PASSWORD = "SuperSecretPassword!"

USERNAME_FIELD: Locator = (By.ID, "username")
PASSWORD_FIELD: Locator = (By.ID, "password")
LOGIN_BUTTON: Locator = (By.CSS_SELECTOR, "button.radius")
LOGOUT_BUTTON: Locator = (By.CSS_SELECTOR, "a.button.secondary")
FLASH_MESSAGE: Locator = (By.ID, "flash")
CHECKBOXES: Locator = (By.CSS_SELECTOR, "#checkboxes input[type='checkbox']")
DROPDOWN: Locator = (By.ID, "dropdown")
START_BUTTON: Locator = (By.CSS_SELECTOR, "#start button")
FINISH_TEXT: Locator = (By.CSS_SELECTOR, "#finish h4")


def create_firefox() -> WebDriver:
    # Firefox у режимі без інтерфейсу
    options = FirefoxOptions()
    options.add_argument("-headless")
    service = FirefoxService(executable_path=str(PROJECT_DIR / "geckodriver.exe"))
    return webdriver.Firefox(options=options, service=service)


def create_chromium() -> WebDriver:
    # Chromium у режимі без інтерфейсу
    options = ChromeOptions()
    chromium_path = Path(os.environ["LOCALAPPDATA"]) / "Chromium" / "Application" / "chrome.exe"
    options.binary_location = str(chromium_path)
    options.add_argument("--headless=new")
    service = ChromeService(executable_path=str(PROJECT_DIR / "chromedriver.exe"))
    return webdriver.Chrome(options=options, service=service)


BROWSERS: dict[str, Callable[[], WebDriver]] = {
    "firefox": create_firefox,
    "chromium": create_chromium,
}


@pytest.fixture(params=list(BROWSERS))
def driver(request: pytest.FixtureRequest) -> Iterator[WebDriver]:
    # Кожен тест виконується в усіх браузерах зі списку
    browser = BROWSERS[request.param]()
    try:
        yield browser
    finally:
        browser.quit()


def wait_visible(driver: WebDriver, locator: Locator) -> WebElement:
    # Явне очікування видимості елемента
    return WebDriverWait(driver, TIMEOUT).until(
        EC.visibility_of_element_located(locator)
    )


def login(driver: WebDriver, username: str, password: str) -> None:
    # Заповнення форми входу та надсилання
    driver.get(f"{BASE_URL}/login")
    wait_visible(driver, USERNAME_FIELD).send_keys(username)
    driver.find_element(*PASSWORD_FIELD).send_keys(password)
    driver.find_element(*LOGIN_BUTTON).click()


def test_successful_login(driver: WebDriver) -> None:
    login(driver, VALID_USERNAME, VALID_PASSWORD)

    message = wait_visible(driver, FLASH_MESSAGE)
    assert "You logged into a secure area!" in message.text
    assert driver.current_url.endswith("/secure")


@pytest.mark.parametrize(
    ("username", "password", "expected"),
    [
        (VALID_USERNAME, "wrong_password", "Your password is invalid!"),
        ("wrong_user", VALID_PASSWORD, "Your username is invalid!"),
    ],
)
def test_login_with_invalid_credentials(
    driver: WebDriver, username: str, password: str, expected: str
) -> None:
    login(driver, username, password)

    message = wait_visible(driver, FLASH_MESSAGE)
    assert expected in message.text
    assert driver.current_url.endswith("/login")


def test_logout(driver: WebDriver) -> None:
    login(driver, VALID_USERNAME, VALID_PASSWORD)
    wait_visible(driver, LOGOUT_BUTTON).click()

    message = wait_visible(driver, FLASH_MESSAGE)
    assert "You logged out of the secure area!" in message.text
    assert driver.current_url.endswith("/login")


def test_checkboxes_toggle(driver: WebDriver) -> None:
    driver.get(f"{BASE_URL}/checkboxes")
    wait_visible(driver, CHECKBOXES)

    for checkbox in driver.find_elements(*CHECKBOXES):
        state_before = checkbox.is_selected()
        checkbox.click()
        assert checkbox.is_selected() is not state_before


def test_dropdown_select_option(driver: WebDriver) -> None:
    driver.get(f"{BASE_URL}/dropdown")
    select = Select(wait_visible(driver, DROPDOWN))

    select.select_by_visible_text("Option 2")

    assert select.first_selected_option.text == "Option 2"


def test_dynamic_loading(driver: WebDriver) -> None:
    driver.get(f"{BASE_URL}/dynamic_loading/1")
    wait_visible(driver, START_BUTTON).click()

    result = wait_visible(driver, FINISH_TEXT)
    assert result.text == "Hello World!"
