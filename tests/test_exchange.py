from unittest.mock import MagicMock

import pytest
import ccxt

from tradingbot.exchange import CCXTExchange


insufficient_funds_response = 'okx {"code":"1","data":[{"clOrdId":"e847386590ce4dBC41721bb12450fd4a","ordId":"","sCode":"51008","sMsg":"Order failed. Insufficient USDT balance in account. ","tag":"e847386590ce4dBC","ts":"1728445289108"}],"inTime":"1728445289108394","msg":"All operations failed","outTime":"1728445289108980"}'

unfilled_limit_order_response = {
    "info": {
        "clOrdId": "e847386590ce4dBCdedee55fb0dc9ab7",
        "ordId": "1877153720438898689",
        "sCode": "0",
        "sMsg": "Order placed",
        "tag": "e847386590ce4dBC",
        "ts": "1728445940347",
    },
    "id": "1877153720438898689",
    "clientOrderId": "e847386590ce4dBCdedee55fb0dc9ab7",
    "timestamp": None,
    "datetime": None,
    "lastTradeTimestamp": None,
    "lastUpdateTimestamp": None,
    "symbol": "BTC/USDT",
    "type": "limit",
    "timeInForce": None,
    "postOnly": None,
    "side": "buy",
    "price": None,
    "stopLossPrice": None,
    "takeProfitPrice": None,
    "stopPrice": None,
    "triggerPrice": None,
    "average": None,
    "cost": None,
    "amount": None,
    "filled": None,
    "remaining": None,
    "status": None,
    "fee": None,
    "trades": [],
    "reduceOnly": False,
    "fees": [],
}

filled_market_order_response = {
    "info": {
        "clOrdId": "e847386590ce4dBC203f7abec8c7dcd9",
        "ordId": "1877236041473081344",
        "sCode": "0",
        "sMsg": "Order placed",
        "tag": "e847386590ce4dBC",
        "ts": "1728448393705",
    },
    "id": "1877236041473081344",
    "clientOrderId": "e847386590ce4dBC203f7abec8c7dcd9",
    "timestamp": None,
    "datetime": None,
    "lastTradeTimestamp": None,
    "lastUpdateTimestamp": None,
    "symbol": "BTC/USDT",
    "type": "market",
    "timeInForce": None,
    "postOnly": None,
    "side": "buy",
    "price": None,
    "stopLossPrice": None,
    "takeProfitPrice": None,
    "stopPrice": None,
    "triggerPrice": None,
    "average": None,
    "cost": None,
    "amount": None,
    "filled": None,
    "remaining": None,
    "status": None,
    "fee": None,
    "trades": [],
    "reduceOnly": False,
    "fees": [],
}

canceled_limit_order_response = {
    "info": {
        "accFillSz": "0",
        "algoClOrdId": "",
        "algoId": "",
        "attachAlgoClOrdId": "",
        "attachAlgoOrds": [],
        "avgPx": "",
        "cTime": "1728445940347",
        "cancelSource": "1",
        "cancelSourceReason": "Order was canceled by you",
        "category": "normal",
        "ccy": "",
        "clOrdId": "e847386590ce4dBCdedee55fb0dc9ab7",
        "fee": "0",
        "feeCcy": "BTC",
        "fillPx": "",
        "fillSz": "0",
        "fillTime": "",
        "instId": "BTC-USDT",
        "instType": "SPOT",
        "isTpLimit": "false",
        "lever": "",
        "linkedAlgoOrd": {"algoId": ""},
        "ordId": "1877153720438898689",
        "ordType": "limit",
        "pnl": "0",
        "posSide": "net",
        "px": "30000",
        "pxType": "",
        "pxUsd": "",
        "pxVol": "",
        "quickMgnType": "",
        "rebate": "0",
        "rebateCcy": "USDT",
        "reduceOnly": "false",
        "side": "buy",
        "slOrdPx": "",
        "slTriggerPx": "",
        "slTriggerPxType": "",
        "source": "",
        "state": "canceled",
        "stpId": "",
        "stpMode": "cancel_maker",
        "sz": "0.01",
        "tag": "e847386590ce4dBC",
        "tdMode": "cash",
        "tgtCcy": "",
        "tpOrdPx": "",
        "tpTriggerPx": "",
        "tpTriggerPxType": "",
        "tradeId": "",
        "uTime": "1728446795565",
    },
    "id": "1877153720438898689",
    "clientOrderId": "e847386590ce4dBCdedee55fb0dc9ab7",
    "timestamp": 1728445940347,
    "datetime": "2024-10-09T03:52:20.347Z",
    "lastTradeTimestamp": None,
    "lastUpdateTimestamp": 1728446795565,
    "symbol": "BTC/USDT",
    "type": "limit",
    "timeInForce": None,
    "postOnly": None,
    "side": "buy",
    "price": 30000.0,
    "stopLossPrice": None,
    "takeProfitPrice": None,
    "stopPrice": None,
    "triggerPrice": None,
    "average": None,
    "cost": 0.0,
    "amount": 0.01,
    "filled": 0.0,
    "remaining": 0.01,
    "status": "canceled",
    "fee": {"cost": 0.0, "currency": "BTC"},
    "trades": [],
    "reduceOnly": False,
    "fees": [{"cost": 0.0, "currency": "BTC"}],
}

trades_response = [
    {
        "info": {
            "fillSz": "0.001",
            "fillPxVol": "",
            "fillFwdPx": "",
            "fee": "-0.000001",
            "ordId": "1877236041473081344",
            "feeRate": "-0.001",
            "clOrdId": "e847386590ce4dBC203f7abec8c7dcd9",
            "posSide": "net",
            "fillMarkVol": "",
            "tag": "e847386590ce4dBC",
            "execType": "T",
            "fillIdxPx": "",
            "side": "buy",
            "fillPx": "62398.1",
            "fillPnl": "0",
            "instType": "SPOT",
            "fillPxUsd": "",
            "instId": "BTC-USDT",
            "billId": "1877236041573744642",
            "subType": "1",
            "fillTime": "1728448393707",
            "tradeId": "582529691",
            "fillMarkPx": "",
            "feeCcy": "BTC",
            "ts": "1728448393708",
        },
        "timestamp": 1728448393708,
        "datetime": "2024-10-09T04:33:13.708Z",
        "symbol": "BTC/USDT",
        "id": "582529691",
        "order": "1877236041473081344",
        "type": None,
        "takerOrMaker": "taker",
        "side": "buy",
        "price": 62398.1,
        "amount": 0.001,
        "cost": 62.3981,
        "fee": {"currency": "BTC", "cost": 1e-06},
        "fees": [{"currency": "BTC", "cost": 1e-06}],
    }
]


@pytest.fixture(scope="function")
def mock_okx_create_order_insufficient_funds():
    mock = MagicMock(spec=ccxt.okx)
    mock.create_order.side_effect = ccxt.errors.InsufficientFunds(insufficient_funds_response)
    return mock


@pytest.fixture(scope="function")
def mock_okx_create_order_unfilled_limit_order():
    mock = MagicMock(spec=ccxt.okx)
    mock.create_order.return_value = unfilled_limit_order_response
    return mock


@pytest.fixture(scope="function")
def mock_okx_create_order_market():
    mock = MagicMock(spec=ccxt.okx)
    mock.create_order.return_value = filled_market_order_response
    return mock


@pytest.fixture(scope="function")
def mock_okx_fetch_order_unfilled():
    mock = MagicMock(spec=ccxt.okx)
    mock.fetch_order.return_value = {
        "info": {
            "accFillSz": "0",
            "algoClOrdId": "",
            "algoId": "",
            "attachAlgoClOrdId": "",
            "attachAlgoOrds": [],
            "avgPx": "",
            "cTime": "1728445940347",
            "cancelSource": "",
            "cancelSourceReason": "",
            "category": "normal",
            "ccy": "",
            "clOrdId": "e847386590ce4dBCdedee55fb0dc9ab7",
            "fee": "0",
            "feeCcy": "BTC",
            "fillPx": "",
            "fillSz": "0",
            "fillTime": "",
            "instId": "BTC-USDT",
            "instType": "SPOT",
            "isTpLimit": "false",
            "lever": "",
            "linkedAlgoOrd": {"algoId": ""},
            "ordId": "1877153720438898689",
            "ordType": "limit",
            "pnl": "0",
            "posSide": "net",
            "px": "30000",
            "pxType": "",
            "pxUsd": "",
            "pxVol": "",
            "quickMgnType": "",
            "rebate": "0",
            "rebateCcy": "USDT",
            "reduceOnly": "false",
            "side": "buy",
            "slOrdPx": "",
            "slTriggerPx": "",
            "slTriggerPxType": "",
            "source": "",
            "state": "live",
            "stpId": "",
            "stpMode": "cancel_maker",
            "sz": "0.01",
            "tag": "e847386590ce4dBC",
            "tdMode": "cash",
            "tgtCcy": "",
            "tpOrdPx": "",
            "tpTriggerPx": "",
            "tpTriggerPxType": "",
            "tradeId": "",
            "uTime": "1728445940347",
        },
        "id": "1877153720438898689",
        "clientOrderId": "e847386590ce4dBCdedee55fb0dc9ab7",
        "timestamp": 1728445940347,
        "datetime": "2024-10-09T03:52:20.347Z",
        "lastTradeTimestamp": None,
        "lastUpdateTimestamp": 1728445940347,
        "symbol": "BTC/USDT",
        "type": "limit",
        "timeInForce": None,
        "postOnly": None,
        "side": "buy",
        "price": 30000.0,
        "stopLossPrice": None,
        "takeProfitPrice": None,
        "stopPrice": None,
        "triggerPrice": None,
        "average": None,
        "cost": 0.0,
        "amount": 0.01,
        "filled": 0.0,
        "remaining": 0.01,
        "status": "open",
        "fee": {"cost": 0.0, "currency": "BTC"},
        "trades": [],
        "reduceOnly": False,
        "fees": [{"cost": 0.0, "currency": "BTC"}],
    }
    return mock


@pytest.fixture(scope="function")
def mock_okx_fetch_open_orders():
    mock = MagicMock(spec=ccxt.okx)
    mock.fetch_open_orders.return_value = [
        {
            "info": {
                "accFillSz": "0",
                "algoClOrdId": "",
                "algoId": "",
                "attachAlgoClOrdId": "",
                "attachAlgoOrds": [],
                "avgPx": "",
                "cTime": "1728447102621",
                "cancelSource": "",
                "cancelSourceReason": "",
                "category": "normal",
                "ccy": "",
                "clOrdId": "e847386590ce4dBCdfc65825f98c8f14",
                "fee": "0",
                "feeCcy": "BTC",
                "fillPx": "",
                "fillSz": "0",
                "fillTime": "",
                "instId": "BTC-USDT",
                "instType": "SPOT",
                "isTpLimit": "false",
                "lever": "",
                "linkedAlgoOrd": {"algoId": ""},
                "ordId": "1877192719882797056",
                "ordType": "limit",
                "pnl": "0",
                "posSide": "net",
                "px": "30000",
                "pxType": "",
                "pxUsd": "",
                "pxVol": "",
                "quickMgnType": "",
                "rebate": "0",
                "rebateCcy": "USDT",
                "reduceOnly": "false",
                "side": "buy",
                "slOrdPx": "",
                "slTriggerPx": "",
                "slTriggerPxType": "",
                "source": "",
                "state": "live",
                "stpId": "",
                "stpMode": "cancel_maker",
                "sz": "0.01",
                "tag": "e847386590ce4dBC",
                "tdMode": "cash",
                "tgtCcy": "",
                "tpOrdPx": "",
                "tpTriggerPx": "",
                "tpTriggerPxType": "",
                "tradeId": "",
                "uTime": "1728447102621",
            },
            "id": "1877192719882797056",
            "clientOrderId": "e847386590ce4dBCdfc65825f98c8f14",
            "timestamp": 1728447102621,
            "datetime": "2024-10-09T04:11:42.621Z",
            "lastTradeTimestamp": None,
            "lastUpdateTimestamp": 1728447102621,
            "symbol": "BTC/USDT",
            "type": "limit",
            "timeInForce": None,
            "postOnly": None,
            "side": "buy",
            "price": 30000.0,
            "stopLossPrice": None,
            "takeProfitPrice": None,
            "stopPrice": None,
            "triggerPrice": None,
            "average": None,
            "cost": 0.0,
            "amount": 0.01,
            "filled": 0.0,
            "remaining": 0.01,
            "status": "open",
            "fee": {"cost": 0.0, "currency": "BTC"},
            "trades": [],
            "reduceOnly": False,
            "fees": [{"cost": 0.0, "currency": "BTC"}],
        }
    ]


@pytest.fixture(scope="function")
def mock_okx_fetch_order_filled():
    mock = MagicMock(spec=ccxt.okx)
    mock.fetch_order.return_value = {
        "info": {
            "accFillSz": "0.001",
            "algoClOrdId": "",
            "algoId": "",
            "attachAlgoClOrdId": "",
            "attachAlgoOrds": [],
            "avgPx": "62398.1",
            "cTime": "1728448393705",
            "cancelSource": "",
            "cancelSourceReason": "",
            "category": "normal",
            "ccy": "",
            "clOrdId": "e847386590ce4dBC203f7abec8c7dcd9",
            "fee": "-0.000001",
            "feeCcy": "BTC",
            "fillPx": "62398.1",
            "fillSz": "0.001",
            "fillTime": "1728448393707",
            "instId": "BTC-USDT",
            "instType": "SPOT",
            "isTpLimit": "false",
            "lever": "",
            "linkedAlgoOrd": {"algoId": ""},
            "ordId": "1877236041473081344",
            "ordType": "market",
            "pnl": "0",
            "posSide": "net",
            "px": "",
            "pxType": "",
            "pxUsd": "",
            "pxVol": "",
            "quickMgnType": "",
            "rebate": "0",
            "rebateCcy": "USDT",
            "reduceOnly": "false",
            "side": "buy",
            "slOrdPx": "",
            "slTriggerPx": "",
            "slTriggerPxType": "",
            "source": "",
            "state": "filled",
            "stpId": "",
            "stpMode": "cancel_maker",
            "sz": "0.001",
            "tag": "e847386590ce4dBC",
            "tdMode": "cash",
            "tgtCcy": "base_ccy",
            "tpOrdPx": "",
            "tpTriggerPx": "",
            "tpTriggerPxType": "",
            "tradeId": "582529691",
            "uTime": "1728448393711",
        },
        "id": "1877236041473081344",
        "clientOrderId": "e847386590ce4dBC203f7abec8c7dcd9",
        "timestamp": 1728448393705,
        "datetime": "2024-10-09T04:33:13.705Z",
        "lastTradeTimestamp": 1728448393707,
        "lastUpdateTimestamp": 1728448393711,
        "symbol": "BTC/USDT",
        "type": "market",
        "timeInForce": "IOC",
        "postOnly": None,
        "side": "buy",
        "price": 62398.1,
        "stopLossPrice": None,
        "takeProfitPrice": None,
        "stopPrice": None,
        "triggerPrice": None,
        "average": 62398.1,
        "cost": 62.3981,
        "amount": 0.001,
        "filled": 0.001,
        "remaining": 0.0,
        "status": "closed",
        "fee": {"cost": 1e-06, "currency": "BTC"},
        "trades": [],
        "reduceOnly": False,
        "fees": [{"cost": 1e-06, "currency": "BTC"}],
    }


@pytest.fixture(scope="function")
def mock_okx_fetch_order_cancelled():
    mock = MagicMock(spec=ccxt.okx)
    mock.fetch_order.return_value = canceled_limit_order_response
    return mock


@pytest.fixture(scope="function")
def mock_okx_fetch_close_orders():
    mock = MagicMock(spec=ccxt.okx)
    mock.fetch_closed_orders.return_value = [
        {
            "info": {
                "accFillSz": "0.001",
                "algoClOrdId": "",
                "algoId": "",
                "attachAlgoClOrdId": "",
                "attachAlgoOrds": [],
                "avgPx": "62398.1",
                "cTime": "1728448393705",
                "cancelSource": "",
                "cancelSourceReason": "",
                "category": "normal",
                "ccy": "",
                "clOrdId": "e847386590ce4dBC203f7abec8c7dcd9",
                "fee": "-0.000001",
                "feeCcy": "BTC",
                "fillPx": "62398.1",
                "fillSz": "0.001",
                "fillTime": "1728448393707",
                "instId": "BTC-USDT",
                "instType": "SPOT",
                "isTpLimit": "false",
                "lever": "",
                "linkedAlgoOrd": {"algoId": ""},
                "ordId": "1877236041473081344",
                "ordType": "market",
                "pnl": "0",
                "posSide": "",
                "px": "",
                "pxType": "",
                "pxUsd": "",
                "pxVol": "",
                "quickMgnType": "",
                "rebate": "0",
                "rebateCcy": "USDT",
                "reduceOnly": "false",
                "side": "buy",
                "slOrdPx": "",
                "slTriggerPx": "",
                "slTriggerPxType": "",
                "source": "",
                "state": "filled",
                "stpId": "",
                "stpMode": "cancel_maker",
                "sz": "0.001",
                "tag": "e847386590ce4dBC",
                "tdMode": "cash",
                "tgtCcy": "base_ccy",
                "tpOrdPx": "",
                "tpTriggerPx": "",
                "tpTriggerPxType": "",
                "tradeId": "582529691",
                "uTime": "1728448393708",
            },
            "id": "1877236041473081344",
            "clientOrderId": "e847386590ce4dBC203f7abec8c7dcd9",
            "timestamp": 1728448393705,
            "datetime": "2024-10-09T04:33:13.705Z",
            "lastTradeTimestamp": 1728448393707,
            "lastUpdateTimestamp": 1728448393708,
            "symbol": "BTC/USDT",
            "type": "market",
            "timeInForce": "IOC",
            "postOnly": None,
            "side": "buy",
            "price": 62398.1,
            "stopLossPrice": None,
            "takeProfitPrice": None,
            "stopPrice": None,
            "triggerPrice": None,
            "average": 62398.1,
            "cost": 62.3981,
            "amount": 0.001,
            "filled": 0.001,
            "remaining": 0.0,
            "status": "closed",
            "fee": {"cost": 1e-06, "currency": "BTC"},
            "trades": [],
            "reduceOnly": False,
            "fees": [{"cost": 1e-06, "currency": "BTC"}],
        }
    ]


@pytest.fixture(scope="function")
def mock_okx_fetch_balance():
    mock = MagicMock(spec=ccxt.okx)
    mock.fetch_balance.return_value = {
        "info": {
            "code": "0",
            "data": [
                {
                    "adjEq": "",
                    "borrowFroz": "",
                    "details": [
                        {
                            "accAvgPx": "",
                            "availBal": "1009.9",
                            "availEq": "",
                            "borrowFroz": "",
                            "cashBal": "1009.9",
                            "ccy": "USDT",
                            "clSpotInUseAmt": "",
                            "crossLiab": "",
                            "disEq": "1009.627327",
                            "eq": "1009.9",
                            "eqUsd": "1009.627327",
                            "fixedBal": "0",
                            "frozenBal": "0",
                            "imr": "",
                            "interest": "",
                            "isoEq": "0",
                            "isoLiab": "",
                            "isoUpl": "",
                            "liab": "",
                            "maxLoan": "",
                            "maxSpotInUse": "",
                            "mgnRatio": "",
                            "mmr": "",
                            "notionalLever": "",
                            "openAvgPx": "",
                            "ordFrozen": "0",
                            "rewardBal": "",
                            "smtSyncEq": "0",
                            "spotBal": "",
                            "spotInUseAmt": "",
                            "spotIsoBal": "0",
                            "spotUpl": "",
                            "spotUplRatio": "",
                            "stgyEq": "0",
                            "totalPnl": "",
                            "totalPnlRatio": "",
                            "twap": "0",
                            "uTime": "1728445895160",
                            "upl": "",
                            "uplLiab": "",
                        }
                    ],
                    "imr": "",
                    "isoEq": "",
                    "mgnRatio": "",
                    "mmr": "",
                    "notionalUsd": "",
                    "ordFroz": "",
                    "totalEq": "1009.627327",
                    "uTime": "1728447007264",
                    "upl": "",
                }
            ],
            "msg": "",
        },
        "USDT": {"free": 1009.9, "used": 0.0, "total": 1009.9},
        "timestamp": 1728447007264,
        "datetime": "2024-10-09T04:10:07.264Z",
        "free": {"USDT": 1009.9},
        "used": {"USDT": 0.0},
        "total": {"USDT": 1009.9},
    }
    return mock


@pytest.fixture(scope="function")
def mock_okx_fetch_my_trades():
    mock = MagicMock(spec=ccxt.okx)
    mock.fetch_my_trades.return_value = trades_response
    return mock


# public API
# exchange.client.load_markets()
# exchange.client.fetch_markets()
# exchange.client.fetch_currencies()
# exchange.client.fetch_ticker("BTC/USDT") / exchange.client.fetch_tickers()
# exchange.client.fetch_order_book("BTC/USDT")
# exchange.client.fetch_ohlcv("BTC/USDT", timeframe="1m", since=None, limit=10)
# exchagne.client.fetch_trades("BTC/USDT", since=None, limit=10)


class TestCCXT:
    def test_create_order_insufficient_funds(self, mock_okx_create_order_insufficient_funds):
        with pytest.raises(ccxt.errors.InsufficientFunds):
            mock_okx_create_order_insufficient_funds.create_order(
                symbol="BTC/USDT", type="limit", side="buy", amount=10_000, price=30_000
            )

    def test_create_order_unfilled_limit_order(self, mock_okx_create_order_unfilled_limit_order):
        order = mock_okx_create_order_unfilled_limit_order.create_order(
            symbol="BTC/USDT", type="limit", side="buy", amount=0.01, price=30_000
        )
        assert order["symbol"] == "BTC/USDT"
        assert order["side"] == "buy"
        assert order["type"] == "limit"
        assert order["price"] is None
        assert order["amount"] is None

    def test_fetch_order_unfilled(self, mock_okx_fetch_order_unfilled):
        order = mock_okx_fetch_order_unfilled.fetch_order("1877153720438898689", symbol="BTC/USDT")
        assert order["symbol"] == "BTC/USDT"
        assert order["side"] == "buy"
        assert order["type"] == "limit"
        assert order["price"] == 30_000.0
        assert order["amount"] == 0.01
        assert order["filled"] == 0.0
        assert order["remaining"] == 0.01
        assert order["status"] == "open"

    def test_fetch_order_canceled(self, mock_okx_fetch_order_canceled):
        order = mock_okx_fetch_order_canceled.fetch_order("1877153720438898689", symbol="BTC/USDT")
        assert order["status"] == "canceled"


# class TestCCXTExchange:
#     def test_create_order(self):
#         exchange = CCXTExchange()
#         order = exchange.client.create_order(symbol="BTC/USDT", type="market", side="buy", amount=0.001)
#         assert order
