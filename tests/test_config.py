import pytest
import tradingbot as tb


@pytest.fixture(scope="function")
def config():
    return tb.config.model_copy()


def test_set_database(config):
    config.general = {"db_url": r"sqlite:///D:/test.db"}
    assert config.general.db_url == "sqlite:///D:/test.db"
