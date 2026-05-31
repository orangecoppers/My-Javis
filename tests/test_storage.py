import sqlite3

from jarvis.models import Listing
from jarvis.storage import Storage


def test_storage_records_listing_and_price_observation(tmp_path) -> None:
    storage = Storage(tmp_path / "jarvis.sqlite3")
    storage.initialize()
    run_id = storage.create_search_run("픽시")
    listing = Listing("bunjang", "123", "리더 픽시", 300_000, "https://m.bunjang.co.kr/products/123")
    first_id = storage.save_listing(listing, run_id)
    second_id = storage.save_listing(listing, run_id)
    with sqlite3.connect(storage.path) as connection:
        listing_count = connection.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        observation_count = connection.execute("SELECT COUNT(*) FROM price_observations").fetchone()[0]
    assert first_id == second_id
    assert listing_count == 1
    assert observation_count == 2


def test_storage_returns_only_previous_search_prices(tmp_path) -> None:
    storage = Storage(tmp_path / "jarvis.sqlite3")
    storage.initialize()
    old_run = storage.create_search_run("old")
    current_run = storage.create_search_run("current")
    storage.save_listing(
        Listing("joongna", "1", "old", 200_000, "https://web.joongna.com/product/1"), old_run
    )
    storage.save_listing(
        Listing("bunjang", "2", "current", 100_000, "https://m.bunjang.co.kr/products/2"),
        current_run,
    )
    assert storage.previous_observed_prices(current_run) == [200_000]
