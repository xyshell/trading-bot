from tradingbot.config import Config


def test_singleton():
    config1 = Config()
    config2 = Config()

    assert config1 is config2


def test_set_database():
    config = Config()
    config.general = {"db_url": r"sqlite:///D:/test.db"}
    assert config.general.db_url == "sqlite:///D:/test.db"
