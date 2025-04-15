import datetime
import os
import importlib
import sys

import pandas as pd
import streamlit as st

from tradingbot.bot import Bot
from tradingbot.reporter import Reporter
import tradingbot.util as util
from tradingbot.strategy import Strategy
from tradingbot.config import get_config


config = get_config()

@st.cache_data
def get_utc_now():
    return util.utc_now_factory()


with st.sidebar:
    strategy_dir = st.text_input("Strategy directory: ", value=config.general.strategy_dir, disabled=True, help="Configured in Setting -> Config -> general -> strategy_dir")


    # load subclasses of Strategy in the strategy directory
    strategy_dir = get_config().general.strategy_dir
    py_files = [
        f for f in os.listdir(strategy_dir)
        if f.endswith(".py") and not f.startswith("_")
    ]
    for file in py_files:
        module_name = file[:-3]  # exclude .py extension
        module_path = os.path.join(strategy_dir, file)
        if module_name not in sys.modules:
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        else:
            module = sys.modules[module_name]
    
    strategy_cls = [kls for kls in Strategy.__subclasses__() if not kls.__module__.startswith("tradingbot.strategy")]
    strategy = {f"{kls.__name__} @ {kls.__module__}": kls for kls in strategy_cls}

    strategy_key = st.radio("Strategy: ", strategy)
    strategy_cls = strategy[strategy_key]

st.subheader(f"{strategy_cls.__name__}: {strategy_cls.__doc__}")
cols = st.columns(len(strategy_cls.param))
for i, (key, value) in enumerate(strategy_cls.param.items()):
    with cols[i]:
        if isinstance(value, str):
            strategy_cls.param[key] = st.text_input(key, value=value)
        elif isinstance(value, (int, float)):
            strategy_cls.param[key] = st.number_input(key, value=value)
        elif isinstance(value, bool):
            strategy_cls.param[key] = st.checkbox(key, value=value)

st.divider()

col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    currency = st.text_input("Currency", value="USDT")
    commission = st.number_input("Commission", value=0.001, min_value=0.0, max_value=1.0, format="%.4f", step=0.0001)
with col2:
    start_date = st.date_input("Start", value=util.utc_now_factory() - pd.Timedelta(days=30))
    end_date = st.date_input("End", value=util.utc_now_factory())
with col3:
    start_time = st.time_input("", value=datetime.time(0, 0))
    end_time = st.time_input("", value=get_utc_now().time())

start = pd.Timestamp.combine(start_date, start_time)
end = pd.Timestamp.combine(end_date, end_time)

st.divider()

if st.button("Run"):
    bot = Bot(mode="backtest", start=start, end=end)
    bot.add_strategy(strategy_cls())
    with st.spinner("Running..."):
        bot.run()

    display_report = Reporter.get_display_report(bot.strategy)
    st.write(display_report.to_dict())
    st.pyplot(bot.strategy.plot())
