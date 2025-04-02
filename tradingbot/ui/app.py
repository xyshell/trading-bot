import streamlit as st

st.set_page_config(layout="wide")
    
if "logged_in" not in st.session_state:
    st.session_state.logged_in = True

# def login():
#     if st.button("Log in"):
#         st.session_state.logged_in = True
#         st.rerun()

# def logout():
#     if st.button("Log out"):
#         st.session_state.logged_in = False
#         st.rerun()

# login_page = st.Page(login, title="Log in", icon=":material/login:")
# logout_page = st.Page(logout, title="Log out", icon=":material/logout:")

page_market = st.Page("application/page_market.py", title="Market", icon=":material/monitoring:", default=True, url_path="/market")
page_backtest = st.Page("application/page_backtest.py", title="Backtest", icon=":material/analytics:", url_path="/backtest")
page_data = st.Page("application/page_data.py", title="Data", icon=":material/database:", url_path="/data")

# bugs = st.Page("application/bugs.py", title="Bug report", icon=":material/bug_report:")
# alerts = st.Page("application/alerts.py", title="System alerts", icon=":material/notification_important:")

search = st.Page("task/page_search.py", title="Search", icon=":material/search:")
history = st.Page("task/page_history.py", title="History", icon=":material/history:")

page_config = st.Page("setting/page_config.py", title="Config", icon=":material/manufacturing:", url_path="/config")

if st.session_state.logged_in:
    pg = st.navigation(
        {
            "Application": [
                page_market, 
                page_backtest,
                page_data
            ],
            "Task": [search, history],
            "Setting": [page_config],
        },
        expanded=True,
    )
# else:
#     pg = st.navigation([login_page])  # 

pg.run()