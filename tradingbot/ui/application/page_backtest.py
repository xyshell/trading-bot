import datetime
import os
import importlib
import sys

import pandas as pd
import streamlit as st

import tradingbot.util as util
from tradingbot.strategy import Strategy
from tradingbot.config import Config
tbconfig = Config()

with st.sidebar:
    strategy_dir = st.text_input("Strategy directory: ", value=tbconfig.general.strategy_dir, disabled=True, help="Configured in Setting -> Config -> general -> strategy_dir")

    # Iterate through the directory and import all .py files
    for filename in os.listdir(strategy_dir):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]  # Remove .py extension
            module_path = os.path.join(strategy_dir, filename)
            
            # Check if the module is already in sys.modules
            if module_name not in sys.modules:
                # Dynamically import the module if not already imported
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            else:
                # If the module is already imported, reuse it from sys.modules
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
            strategy_cls.param[key] = st.text_input(key, value)
        elif isinstance(value, (int, float)):
            strategy_cls.param[key] = st.number_input(key, value)
        elif isinstance(value, bool):
            strategy_cls.param[key] = st.checkbox(key, value)

st.divider()

col1, col2, col3, col4 = st.columns([1] * 4)
with col1:
    capital = st.number_input("Capital", value=10_000)
with col2:
    currency = st.text_input("Currency", value="USDT")
with col3:
    commission = st.number_input("Commission", value=0.001, min_value=0.0, max_value=1.0, format="%.4f", step=0.0001)

col1, col2, col3, col4 = st.columns([1] * 4)
with col1:
    start_date = st.date_input("Start", value=util.utc_now_factory() - pd.Timedelta(days=30))
with col2:
    start_time = st.time_input("", value=datetime.time(0, 0))
with col3:
    end_date = st.date_input("End", value=util.utc_now_factory())
with col4:
    end_time = st.time_input("", value=util.utc_now_factory().time())

start = pd.Timestamp.combine(start_date, start_time)
end = pd.Timestamp.combine(end_date, end_time)

st.write(end)
st.divider()