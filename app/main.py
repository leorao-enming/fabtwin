"""FabTwin Streamlit dashboard entry point.

P0 stub. This file must stay thin: it only calls into fabtwin's application
service layer (src/fabtwin/) and renders results. No formulas, no simulation
logic, no SPC math here — ever. See docs/adr/ for why.
"""

import streamlit as st

st.set_page_config(page_title="FabTwin", layout="wide")
st.title("FabTwin")
st.caption("P0 skeleton — simulator, SPC, and fault-diagnostics land in Gates T1-T4.")

st.warning(
    "This is a placeholder page. No simulation, SPC, or capability analysis "
    "has been implemented yet. Nothing shown here is a real result."
)
