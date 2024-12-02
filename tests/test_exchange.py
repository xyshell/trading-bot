from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import ccxt

from tradingbot.exchange.ccxt import CCXTExchange
from tradingbot.model import Account
from tradingbot.order import Order


insufficient_funds_response = 'okx {"code":"1","data":[{"clOrdId":"e847386590ce4dBC41721bb12450fd4a","ordId":"","sCode":"51008","sMsg":"Order failed. Insufficient USDT balance in account. ","tag":"e847386590ce4dBC","ts":"1728445289108"}],"inTime":"1728445289108394","msg":"All operations failed","outTime":"1728445289108980"}'

create_limit_order_resp = {
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

create_market_order_resp = {
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

fetch_order_canceled_limit_order_resp = {
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

fetch_order_unfilled_limit_order_resp = {
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

fetch_order_filled_market_order_buy_resp = {
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

fetch_order_filled_market_order_sell_resp = {
    "info": {
        "accFillSz": "0.001",
        "algoClOrdId": "",
        "algoId": "",
        "attachAlgoClOrdId": "",
        "attachAlgoOrds": [],
        "avgPx": "62922",
        "cTime": "1728801454900",
        "cancelSource": "",
        "cancelSourceReason": "",
        "category": "normal",
        "ccy": "",
        "clOrdId": "e847386590ce4dBC6d586b89297ca55",
        "fee": "-0.062922",
        "feeCcy": "USDT",
        "fillPx": "62922",
        "fillSz": "0.001",
        "fillTime": "1728801454901",
        "instId": "BTC-USDT",
        "instType": "SPOT",
        "isTpLimit": "false",
        "lever": "",
        "linkedAlgoOrd": {"algoId": ""},
        "ordId": "1889082809332547584",
        "ordType": "market",
        "pnl": "0",
        "posSide": "net",
        "px": "",
        "pxType": "",
        "pxUsd": "",
        "pxVol": "",
        "quickMgnType": "",
        "rebate": "0",
        "rebateCcy": "BTC",
        "reduceOnly": "false",
        "side": "sell",
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
        "tradeId": "584090326",
        "uTime": "1728801454903",
    },
    "id": "1889082809332547584",
    "clientOrderId": "e847386590ce4dBC6d586b89297ca55",
    "timestamp": 1728801454900,
    "datetime": "2024-10-13T06:37:34.900Z",
    "lastTradeTimestamp": 1728801454901,
    "lastUpdateTimestamp": 1728801454903,
    "symbol": "BTC/USDT",
    "type": "market",
    "timeInForce": "IOC",
    "postOnly": None,
    "side": "sell",
    "price": 62922.0,
    "stopLossPrice": None,
    "takeProfitPrice": None,
    "stopPrice": None,
    "triggerPrice": None,
    "average": 62922.0,
    "cost": 62.922,
    "amount": 0.001,
    "filled": 0.001,
    "remaining": 0.0,
    "status": "closed",
    "fee": {"cost": 0.062922, "currency": "USDT"},
    "trades": [],
    "reduceOnly": False,
    "fees": [{"cost": 0.062922, "currency": "USDT"}],
}

fetch_open_orders_resp = [
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

fetch_closed_orders_resp = [
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

fetch_balance_resp = {
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

cancel_order_resp = {
    "info": {
        "clOrdId": "e847386590ce4dBCdfc65825f98c8f14",
        "ordId": "1877192719882797056",
        "sCode": "0",
        "sMsg": "",
        "ts": "1728796370694",
    },
    "id": "1877192719882797056",
    "clientOrderId": "e847386590ce4dBCdfc65825f98c8f14",
    "timestamp": None,
    "datetime": None,
    "lastTradeTimestamp": None,
    "lastUpdateTimestamp": None,
    "symbol": "BTC/USDT",
    "type": None,
    "timeInForce": None,
    "postOnly": None,
    "side": None,
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

fetch_my_trades_resp = [
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
    mock.create_order.return_value = create_limit_order_resp
    return mock


@pytest.fixture(scope="function")
def mock_okx_create_order_market():
    mock = MagicMock(spec=ccxt.okx)
    mock.create_order.return_value = create_market_order_resp
    return mock


@pytest.fixture(scope="function")
def mock_okx_fetch_order_unfilled():
    mock = MagicMock(spec=ccxt.okx)
    mock.fetch_order.return_value = fetch_order_unfilled_limit_order_resp
    return mock


@pytest.fixture(scope="function")
def mock_okx_fetch_open_orders():
    mock = MagicMock(spec=ccxt.okx)
    mock.fetch_open_orders.return_value = fetch_open_orders_resp


@pytest.fixture(scope="function")
def mock_okx_fetch_order_filled():
    mock = MagicMock(spec=ccxt.okx)
    mock.fetch_order.return_value = fetch_order_filled_market_order_buy_resp


@pytest.fixture(scope="function")
def mock_okx_fetch_order_canceled():
    mock = MagicMock(spec=ccxt.okx)
    mock.fetch_order.return_value = fetch_order_canceled_limit_order_resp
    return mock


@pytest.fixture(scope="function")
def mock_okx_fetch_close_orders():
    mock = MagicMock(spec=ccxt.okx)
    mock.fetch_closed_orders.return_value = fetch_closed_orders_resp


@pytest.fixture(scope="function")
def mock_okx_fetch_balance():
    mock = MagicMock(spec=ccxt.okx)
    mock.fetch_balance.return_value = fetch_balance_resp
    return mock


@pytest.fixture(scope="function")
def mock_okx_fetch_my_trades():
    mock = MagicMock(spec=ccxt.okx)
    mock.fetch_my_trades.return_value = fetch_my_trades_resp
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

    def test_fetch_order_status(self):  # fetch_order_status returns 'open' or 'closed'
        mock_obx = MagicMock(spec=ccxt.okx)
        mock_obx.fetch_order_status.return_value = "closed"
        msg = mock_obx.fetch_order_status("1877153720438898689", symbol="BTC/USDT")
        assert msg == "closed"

        mock_obx.fetch_order_status.return_value = "open"
        msg = mock_obx.fetch_order_status("1877153720438898689", symbol="BTC/USDT")
        assert msg == "open"


class TestCCXTExchange:
    @patch("tradingbot.exchange.ccxt.CCXTExchange.client")
    def test_new2filled(self, mock_client):
        exchange = CCXTExchange()
        mock_client.create_order.return_value = create_market_order_resp
        mock_client.fetch_order_status.return_value = "closed"
        mock_client.fetch_order.return_value = fetch_order_filled_market_order_buy_resp

        exchange.strategy = MagicMock()
        exchange.strategy.account = Account.create({"USDT": 1000})
        exchange.strategy.open_order = []
        now = pd.Timestamp("2024-01-01 00:00:00")
        new_order = Order(action="BUY", ticker="USDT/BTC", size_type="PCTG", size=0.5, type="LIMIT", param={"price": 62398.1})
        assert new_order.status is Order.Status.NEW
        exchange.execute(now=now, order=new_order, check=False)
        exchange.update_order(now=now, order=new_order)
        mock_client.create_order.assert_called_once_with(
            symbol="BTC/USDT", type="limit", side="buy", amount=0.00801306450036139, price=62398.1
        )
        assert new_order.id_ is not None
        assert new_order.status is Order.Status.FILLED
        assert new_order not in exchange.strategy.open_order

    @patch("tradingbot.exchange.ccxt.CCXTExchange.client")
    def test_new2pending(self, mock_client):
        exchange = CCXTExchange()
        mock_client.create_order.return_value = create_market_order_resp
        mock_client.fetch_order.return_value = fetch_order_unfilled_limit_order_resp

        exchange.strategy = MagicMock()
        exchange.strategy.account = Account.create({"USDT": 1000})
        exchange.strategy.open_order = []
        now = pd.Timestamp("2024-01-01 00:00:00")
        new_order = Order(action="BUY", ticker="USDT/BTC", size_type="PCTG", size=0.5, type="LIMIT", param={"price": 62398.1})
        assert new_order.status is Order.Status.NEW
        exchange.execute(now=now, order=new_order)
        mock_client.create_order.assert_called_once_with(
            symbol="BTC/USDT", type="limit", side="buy", amount=0.00801306450036139, price=62398.1
        )
        assert new_order.status is Order.Status.PENDING
        assert new_order.id_ is not None
        exchange.update_order(now=now, order=new_order)
        assert new_order.status is Order.Status.PENDING
        assert new_order in exchange.strategy.open_order

    @patch("tradingbot.exchange.ccxt.CCXTExchange.client")
    def test_pending2filled(self, mock_client):
        exchange = CCXTExchange()
        mock_client.create_order.return_value = create_market_order_resp
        mock_client.fetch_order_status.return_value = "closed"
        mock_client.fetch_order.return_value = fetch_order_filled_market_order_buy_resp

        exchange.strategy = MagicMock()
        exchange.strategy.account = Account.create({"USDT": 1000})
        now = pd.Timestamp("2024-01-01 00:00:00")
        open_order = Order(
            action="BUY",
            ticker="USDT/BTC",
            size_type="PCTG",
            size=0.5,
            type="LIMIT",
            param={"price": 62398.1},
            status=Order.Status.PENDING,
            id_="1877153720438898689",
        )
        exchange.strategy.open_order = [open_order]
        exchange.execute(now=now, order=open_order)
        mock_client.create_order.assert_not_called()
        assert open_order.status is Order.Status.PENDING
        assert open_order.id_ is not None
        exchange.update_order(now=now, order=open_order)
        assert open_order.status is Order.Status.FILLED
        assert open_order not in exchange.strategy.open_order

    @patch("tradingbot.exchange.ccxt.CCXTExchange.client")
    def test_pending2canceled_by_strategy(self, mock_client):
        exchange = CCXTExchange()
        mock_client.cancel_order.return_value = cancel_order_resp
        mock_client.fetch_order_status.return_value = "canceled"
        mock_client.fetch_order.return_value = fetch_order_filled_market_order_buy_resp

        order = Order(
            action="BUY",
            ticker="USDT/BTC",
            size_type="PCTG",
            size=0.5,
            type="LIMIT",
            param={"price": 62398.1},
            status=Order.Status.PENDING,
            id_="1877153720438898689",
        )

        exchange.strategy = MagicMock()
        exchange.strategy.open_order = [order]
        exchange.strategy.order_history = []
        order.status = Order.Status.CANCELED
        now = pd.Timestamp("2024-01-01 00:00:00")

        exchange.execute(now=now, order=order)
        mock_client.cancel_order.assert_called_once()
        assert order.status is Order.Status.CANCELED
        assert order in exchange.strategy.open_order

        exchange.update_order(now=now, order=order)
        assert order not in exchange.strategy.open_order
        assert order in [order for _, order in exchange.strategy.order_history]

    @patch("tradingbot.exchange.ccxt.CCXTExchange.client")
    def test_pending2canceled_by_me(self, mock_client):
        exchange = CCXTExchange()
        mock_client.cancel_order.return_value = cancel_order_resp
        mock_client.fetch_order.return_value = fetch_order_canceled_limit_order_resp

        order = Order(
            action="BUY",
            ticker="USDT/BTC",
            size_type="PCTG",
            size=0.5,
            type="LIMIT",
            param={"price": 62398.1},
            status=Order.Status.PENDING,
            id_="1877153720438898689",
        )
        exchange.strategy = MagicMock()
        exchange.strategy.open_order = [order]
        exchange.strategy.order_history = []

        now = pd.Timestamp("2024-01-01 00:00:00")
        exchange.execute(now=now, order=order)
        mock_client.cancel_order.assert_not_called()
        assert order.status is Order.Status.PENDING
        assert order in exchange.strategy.open_order

        exchange.update_order(now=now, order=order)
        assert order.status is Order.Status.CANCELED
        assert order not in exchange.strategy.open_order
        assert order in [order for _, order in exchange.strategy.order_history]

    @patch("tradingbot.exchange.ccxt.CCXTExchange.client")
    def test_new2rejected(self, mock_client):
        exchange = CCXTExchange()
        mock_client.create_order.side_effect = ccxt.InsufficientFunds(insufficient_funds_response)
        mock_client.fetch_order.return_value = fetch_order_filled_market_order_buy_resp

        exchange.strategy = MagicMock()
        exchange.strategy.account = Account.create({"USDT": 1000})
        now = pd.Timestamp("2024-01-01 00:00:00")
        order = Order(
            action="BUY",
            ticker="USDT/BTC",
            size_type="PCTG",
            size=0.5,
            type="LIMIT",
            param={"price": 62398.1},
            status=Order.Status.NEW,
        )
        exchange.strategy.open_order = [order]
        exchange.strategy.order_history = []

        exchange.execute(now=now, order=order)
        mock_client.create_order.assert_called_once()
        assert order.id_ is None
        assert order.status is Order.Status.REJECTED

        exchange.update_order(now=now, order=order)
        assert order.status is Order.Status.REJECTED
        assert order not in exchange.strategy.open_order
        assert order in [order for _, order in exchange.strategy.order_history]
        mock_client.fetch_order_status.assert_not_called()

    # def test_create_order_market(self):
    #     exchange = CCXTExchange()
    #     order = exchange.client.create_order(symbol="BTC/USDT", type="market", side="sell", amount=0.001)
    #     assert order

    # def test_create_order_limit(self):
    #     exchange = CCXTExchange()
        
    #     # # spot
    #     # order = exchange.client.create_order(symbol="BTC/USDT", type="limit", side="buy", amount=0.001, price=30_100)
    #     # assert order
        
    #     # perpetual future
    #     symbol = "BTC/USDT:USDT"
    #     exchange.client.set_leverage(10, symbol, params={"mgnMode": "isolated", "posSide": "long"})
    #     # ccxt.base.errors.ExchangeError: okx {"code":"59101","data":[],"msg":"Leverage can't be modified. Please cancel all pending isolated margin orders before adjusting the leverage."}
    #     order = exchange.client.create_order(symbol=symbol, type="limit", side="buy", amount=0.01, price=30_100, 
    #                                          params={"posSide": "long", "marginMode": "isolated", "hedged": False})
    #     assert order

    # def test_fetch_order(self):
    #     exchange = CCXTExchange()
    #     with pytest.raises(ccxt.errors.OrderNotFound):
    #         exchange.client.fetch_order("1877153720438898689", symbol="BTC/USDT")

    #     order = exchange.client.fetch_order("1877236041473081344", symbol="BTC/USDT")
    #     assert order["status"] == "closed"

    #     with pytest.raises(ccxt.errors.OrderNotFound):  # canceling a closed order raises OrderNotFound
    #         exchange.client.cancel_order("1877236041473081344", symbol="BTC/USDT")

    #     order = exchange.client.fetch_order("1877192719882797056", symbol="BTC/USDT")
    #     assert order["status"] == "open"

    # def test_fetch_order_status(self):
    #     exchange = CCXTExchange()
    #     with pytest.raises(ccxt.errors.OrderNotFound):
    #         exchange.client.fetch_order_status("1877153720438898689", symbol="BTC/USDT")

    #     msg = exchange.client.fetch_order_status("1877236041473081344", symbol="BTC/USDT")
    #     assert msg == "closed"

    #     msg = exchange.client.fetch_order_status("1877192719882797056", symbol="BTC/USDT")
    #     assert msg == "open"

    # def test_fetch_ticker(self):
    #     exchange = CCXTExchange()
    #     ticker = exchange.client.fetch_ticker("BTC/USDT")
    #     assert ticker

    # def test_cancel_order(self):
    #     exchange = CCXTExchange()
    #     order = exchange.client.cancel_order("1877192719882797056", symbol="BTC/USDT")
    #     assert order

    # def test_fetch_balance(self):
    #     exchange = CCXTExchange()
    #     balance = exchange.client.fetch_balance()
    #     balance = exchange.client.fetch_balance({"ccy": "BTC"})
    #     balance = exchange.client.fetch_balance({"ccy": "BTC,ETH"})
        
    #     balance['info']['data'][0]['totalEq']  # total equity
    #     balance['info']['data'][0]['details'][1]  # detail by coin
    #     {
    #         'accAvgPx': '46416.262714480996', 
    #         'availBal': '0.02040934245', 
    #         'availEq': '0.02040934245', 
    #         'borrowFroz': '', 
    #         'cashBal': '0.02040934245', 
    #         'ccy': 'BTC', 
    #         'clSpotInUseAmt': '', 
    #         'crossLiab': '', 
    #         'disEq': '1811.6926736452192', 
    #         'eq': '0.02040934245', 
    #         'eqUsd': '1848.6659935155299', 
    #         'fixedBal': '0', 
    #         'frozenBal': '0', 
    #         'imr': '0', 
    #         'interest': '', 
    #         'isoEq': '0', 
    #         'isoLiab': '', 
    #         'isoUpl': '0', 
    #         'liab': '', 
    #         'maxLoan': '', 
    #         'maxSpotInUse': '', 
    #         'mgnRatio': '', 
    #         'mmr': '0', 
    #         'notionalLever': '0', 
    #         'openAvgPx': '74238.00254099998', 
    #         'ordFrozen': '0', 
    #         'rewardBal': '0', 
    #         'smtSyncEq': '0', 
    #         'spotBal': '0.02040934245', 
    #         'spotCopyTradingEq': '0', 
    #         'spotInUseAmt': '', 
    #         'spotIsoBal': '0', 
    #         'spotUpl': '333.51717685229113', 
    #         'spotUplRatio': '0.2201217287598091', 
    #         'stgyEq': '0', 
    #         'totalPnl': '901.3405925265206', 
    #         'totalPnlRatio': '0.9514582756733003', 
    #         'twap': '0', 
    #         'uTime': '1731690061466', 
    #         'upl': '0', 
    #         'uplLiab': ''
    #     }
    #     balance['timestamp'], balance['datetime']  # record time
    #     balance['free'], balance['used'], balance['total']  # free, used, total by coin
    #     ticker = "USDT/BTC"
    #     coin_detail = balance.get(util.get_base_ticker(ticker))
    #     coin_detail['free'], coin_detail['used'], coin_detail['total']
    #     assert balance