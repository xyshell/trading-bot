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

dashboard = st.Page(
    "report/dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True
)
bugs = st.Page("report/bugs.py", title="Bug report", icon=":material/bug_report:")
alerts = st.Page(
    "report/alerts.py", title="System alerts", icon=":material/notification_important:"
)

search = st.Page("tool/search.py", title="Search", icon=":material/search:")
history = st.Page("tool/history.py", title="History", icon=":material/history:")

page_config = st.Page(
    "setting/config.py", title="Config", icon=":material/manufacturing:",
)

if st.session_state.logged_in:
    pg = st.navigation(
        {
            "Report": [dashboard, bugs, alerts],
            "Tool": [search, history],
            "Setting": [page_config],
        },
        expanded=True,
    )
# else:
#     pg = st.navigation([login_page])

pg.run()