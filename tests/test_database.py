import sqlalchemy as sa

from tradingbot import config
from tradingbot.database import Database

def test_get_engine():
    engine = Database.get_engine(config.general.db_url)
    assert engine

def test_get_opt_table():
    table = Database.get_opt_table()
    assert isinstance(table, sa.Table) 
