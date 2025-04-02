from tradingbot.util import hash_pd


def assert_report(report, snapshot):
    assert len(report['asset']) == len(report['portfolio']) == snapshot  # timeline count
    assert report['asset'].iloc[-1].drop("timestamp").mean().round(4) == snapshot  # ending asset
    assert report['portfolio'].iloc[-1].drop("timestamp").mean().round(4) == snapshot  # ending nav
    assert report['transaction']['timestamp'].mean() == snapshot  # historical transaction
    assert report['trade']['duration'].mean() == snapshot  # historical trade
    assert report['order']['amount'].round(4).mean() == snapshot  # historical order
    assert hash_pd(report['order'].set_index("created_at")['action']) == snapshot
    assert report['order']['filled_at'].mean() == snapshot  # historical order
    # selected agg metrics
    assert report['summary']["trade_num"] == snapshot
    assert report['summary']["ir"].round(4) == snapshot
    assert report['summary']["expectancy"].round(4) == snapshot