import os
import pathlib
import logging
import time
import toml

import streamlit as st

logger = logging.getLogger(__name__)


def _flatten_dict(d, parent_key="", sep="."):
    flat_dict = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            flat_dict.update(_flatten_dict(v, new_key, sep))
        else:
            flat_dict[new_key] = v
    return flat_dict


def display_config(config, flavor="form"):
    # display the configuration in a form
    if flavor == "form":
        with st.form("config_form", clear_on_submit=True):
            # general
            sec_general = "general"
            st.subheader(sec_general, divider=True)
            config_general = config[sec_general]
            if "log_dir" not in config_general:
                config_general["log_dir"] = pathlib.Path(__file__).parent.parent.parent / "log"
            if "strategy_dir" not in config_general:
                config_general["strategy_dir"] = pathlib.Path(__file__).parent.parent.parent / "strategy"
            for key, value in config_general.items():
                col1, col2 = st.columns([1, 4])
                with col1:
                    st.text(f"{key}:")
                with col2:
                    config[sec_general][key] = st.text_input(
                        key,
                        value,
                        label_visibility="collapsed",
                    )

            # source
            sec_source = "source"
            st.subheader(sec_source, divider=True)
            config_source = config[sec_source]
            config_source_flat = _flatten_dict(config_source, sep=".")
            for key, value in config_source_flat.items():
                col1, col2 = st.columns([1, 4])
                with col1:
                    st.text(f"{key}:")
                with col2:
                    config_source[key.split(".")[0]][key.split(".")[1]] = st.text_input(
                        key,
                        value,
                        label_visibility="collapsed",
                        type="password" if "secret" in key or "password" in key else "default",
                    )

            # exchange
            sec_exchange = "exchange"
            st.subheader(sec_exchange, divider=True)
            config_exchange = config[sec_exchange]
            config_exchange_flat = _flatten_dict(config_exchange, sep=".")
            for key, value in config_exchange_flat.items():
                col1, col2 = st.columns([1, 4])
                with col1:
                    st.text(f"{key}:")
                with col2:
                    config_exchange[key.split(".")[0]][key.split(".")[1]] = st.text_input(
                        key,
                        value,
                        label_visibility="collapsed",
                        type="password" if "secret" in key or "password" in key else "default",
                    )

            # notification
            sec_notification = "notification"
            if sec_notification in config:
                st.subheader(sec_notification, divider=True)
                config_notification = config[sec_notification]
                config_notification_flat = _flatten_dict(config_notification, sep=".")
                for key, value in config_notification_flat.items():
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        st.text(f"{key}:")
                    with col2:
                        config_notification[key.split(".")[0]][key.split(".")[1]] = st.text_input(
                            key, value, label_visibility="collapsed", type="password" if "token" in key else "default"
                        )

            col1, col2 = st.columns([1, 1], gap="small")
            with col1:

                @st.dialog("Configuration saved successfully!")
                def show_dialog():
                    st.write(f"Saved to: {st.session_state['config_file_path']}")
                    button_ok = st.button("Ok", use_container_width=True, type="primary")
                    if button_ok:
                        st.rerun()

                button_save = st.form_submit_button("Save", use_container_width=True, type="primary", on_click=show_dialog)
                if button_save:
                    with open(config_file_path, "w") as f:
                        toml.dump(config, f)
            with col2:
                button_reset = st.form_submit_button("Reset", use_container_width=True, type="secondary")
                if button_reset:
                    st.rerun()

    elif flavor == "raw":
        with open(st.session_state["config_file_path"], "r") as f:
            st.code(f.read(), language="toml")


# Load the configuration
default_config_file = pathlib.Path(__file__).parent.parent.parent / "config.toml"  # tradingbot/config.toml
if "config_file_path" not in st.session_state:
    st.session_state["config_file_path"] = default_config_file

TB_CONFIG_FILE = os.environ.get("TB_CONFIG_FILE")
config_file_path = default_config_file if not TB_CONFIG_FILE else pathlib.Path(TB_CONFIG_FILE)

if not config_file_path.exists():
    st.warning(
        f"Config file not found at: {config_file_path}, please either:\n"
        f"1. Add a config file to the above path;\n"
        f"2. Override the TB_CONFIG_FILE environment variable with the correct path to the config file;\n"
        f"3. Create a new config file using the template"
    )
    if st.button("Create a new config file"):
        with st.status("Creating a new config file..."):
            time.sleep(0.01)
            st.write("Loading from template...")
            config_template = toml.load(pathlib.Path(__file__).parent.parent.parent / "config_example.toml")
            st.write("Saving to new file...")
            with open(config_file_path, "w") as f:
                toml.dump(config_template, f)

        st.success(f"New config file created at: {config_file_path}")
        progress_bar = st.progress(0, text="Reloading...")
        for percent_complete in range(100):
            progress_bar.progress(percent_complete + 1, text="Reloading...")
            time.sleep(0.01)
        time.sleep(0.5)
        st.rerun()
else:
    st.session_state["config_file_path"] = config_file_path
    config = toml.load(config_file_path)

    tab_form, tab_raw = st.tabs(["📋Form", "⚙️Raw"])
    with tab_form:
        display_config(config, "form")
    with tab_raw:
        display_config(config, "raw")
