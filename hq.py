import logging
import pandas as pd
import streamlit as st
import pages
import services
import settings
import utils

st.set_page_config(page_title="Command and Control", layout="wide")

# Configure logging.  This is already done, but make it a dedicated function.
logging.basicConfig(level=logging.INFO, encoding="utf-8", format=f'%(asctime)s:%(levelname)s:%(filename)s:%(lineno)d:%(message)s')
logger = logging.getLogger(__name__)

# Initialize Streamlit session state variables.
for op in services.HQ_SERVICES:
    st.session_state.setdefault(f"{op}_success", [])
    st.session_state.setdefault(f"{op}_fail", [])
st.session_state.setdefault("data", pd.DataFrame())

@st.cache_data
def load_data(live: bool = True):
    if live:
        search_terms = ["missile", "earthquake", "tsunami", "oil", "flood", "iraq", "syria", "korea", "pacific"]
        query = st.segmented_control(label="Assets", options=search_terms)
        st.session_state["data"] = utils.nasa_feed(isLive=True, query=query) # pyright: ignore
    else:
        st.session_state["data"] = utils.nasa_feed(isLive=False, query="")


def main():
    st.header("Command Center")

    load_data(st.session_state.get("isLive", False))

    left, right = st.columns([2, 10], border=True)
    with left:
        pages.hq_actionbar()
        pages.statusbar(services.HQ_SERVICES)

    # HQ Services
    with right:
        pages.hq_broadcaster()

        pages.hq_responder()

    "Request"
    st.dataframe(st.session_state["request_success"])
    "Response"
    st.dataframe(st.session_state["response_success"])

if __name__ == "__main__":
    logger.info("Running in HQ mode")
    main()
