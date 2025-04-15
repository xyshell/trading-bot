from tradingbot.config import get_config


def test_singleton():
    config1 = get_config()
    config2 = get_config()

    assert config1 is config2


def test_set_database():
    config = get_config()
    config.general = {"db_url": r"sqlite:///D:/test.db"}
    assert config.general.db_url == "sqlite:///D:/test.db"
