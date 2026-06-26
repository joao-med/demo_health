import streamlit as st
from dotenv import load_dotenv
import os
import sys

# Ensure CWD is the app directory so all relative paths (DB, data/) resolve correctly
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(_APP_DIR)

load_dotenv()

st.set_page_config(
    page_title="OpenHealth Analytics",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _init_database():
    """Generate synthetic data and build DuckDB on first run (Streamlit Cloud)."""
    if os.path.exists("openhealth.duckdb"):
        return
    with st.spinner("Initialising demo database — this takes about 30 seconds on first run..."):
        sys.path.insert(0, _APP_DIR)
        import generate_data
        import setup_db
        generate_data.main()
        setup_db.main()


_init_database()


def _load_passwords():
    pw = {"admin": "admin123"}
    try:
        secrets_pw = st.secrets.get("passwords", {})
        if secrets_pw:
            return dict(secrets_pw)
    except Exception:
        pass
    pw["admin"] = os.getenv("ADMIN_PASSWORD", "admin123")
    for entry in os.getenv("STAKEHOLDER_PASSWORDS", "").split(","):
        if ":" in entry:
            k, v = entry.split(":", 1)
            pw[k.strip()] = v.strip()
    return pw


PASSWORDS = _load_passwords()


def login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## OpenHealth Analytics")
        st.markdown("Population Health Dashboard")
        st.divider()

        role = st.selectbox(
            "Account",
            ["admin", "health_plan_A", "health_plan_B", "employer_C", "clinic_D"],
        )
        password = st.text_input("Password", type="password", placeholder="Password")

        if st.button("Sign in", use_container_width=True, type="primary"):
            expected = PASSWORDS.get(role)
            if expected and password == expected:
                st.session_state.logged_in = True
                st.session_state.role = "admin" if role == "admin" else "stakeholder"
                st.session_state.stakeholder_id = (
                    None if role == "admin" else role
                )
                st.rerun()
            else:
                st.error("Invalid password")

        st.caption("Demo credentials: admin / admin123  |  health_plan_A / pass1")


CHAT_BUBBLE = """
<style>
#chat-bubble {
    position: fixed;
    bottom: 28px;
    right: 28px;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    font-family: sans-serif;
}
#chat-btn {
    width: 54px;
    height: 54px;
    border-radius: 50%;
    background: #1a6ef5;
    color: white;
    border: none;
    font-size: 24px;
    cursor: pointer;
    box-shadow: 0 4px 14px rgba(0,0,0,0.25);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.2s;
}
#chat-btn:hover { background: #1558c7; }
#chat-popup {
    display: none;
    margin-bottom: 10px;
    background: white;
    border: 1px solid #e0e0e0;
    border-radius: 12px;
    padding: 18px 20px;
    width: 240px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.15);
    font-size: 14px;
    color: #333;
    text-align: center;
}
#chat-popup .badge {
    display: inline-block;
    background: #f0f4ff;
    color: #1a6ef5;
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 12px;
    margin-bottom: 8px;
    font-weight: 600;
    letter-spacing: 0.3px;
}
</style>
<div id="chat-bubble">
    <div id="chat-popup">
        <div class="badge">AI Assistant</div>
        <p style="margin:8px 0 0 0; line-height:1.5;">
            <b>To be developed</b><br>
            <span style="color:#888; font-size:12px;">
                Clinical insights and natural language queries coming soon.
            </span>
        </p>
    </div>
    <button id="chat-btn" onclick="
        var p = document.getElementById('chat-popup');
        p.style.display = p.style.display === 'block' ? 'none' : 'block';
    " title="AI Assistant">&#128172;</button>
</div>
"""


def main():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        login_page()
        return

    pop_health = st.Page(
        "pages/1_population_health.py",
        title="Population Health",
        icon="🏥",
        default=True,
    )
    cardiovascular = st.Page(
        "pages/2_cardiovascular.py",
        title="Cardiovascular Risk",
        icon="🫀",
    )
    geographic = st.Page(
        "pages/3_geographic.py",
        title="Geographic Distribution",
        icon="🌍",
    )
    statistical = st.Page(
        "pages/4_statistical_analysis.py",
        title="Statistical Analysis",
        icon="📊",
    )
    preventive = st.Page(
        "pages/5_preventive_care.py",
        title="Preventive Care",
        icon="🩺",
    )

    pg = st.navigation({"Analytics": [pop_health, cardiovascular, geographic, statistical, preventive]})

    with st.sidebar:
        st.divider()
        label = (
            "Admin - all stakeholders"
            if st.session_state.role == "admin"
            else st.session_state.stakeholder_id
        )
        st.caption(f"Signed in as: **{label}**")
        if st.button("Sign out", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()

    pg.run()

    st.markdown(CHAT_BUBBLE, unsafe_allow_html=True)


main()
