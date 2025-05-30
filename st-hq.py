import asyncio
import logging
import pandas as pd
import streamlit as st
import pages
import services
import settings
import utils

st.set_page_config(page_title="Command and Control", layout="wide")

# Configure logging.
logging.basicConfig(level=logging.INFO, encoding="utf-8", format=f'%(asctime)s:%(levelname)s:%(filename)s:%(lineno)d:%(message)s')
logger = logging.getLogger(__name__)

# Initialize Streamlit session state variables.
for op in services.HQ_SERVICES:
    st.session_state.setdefault(f"{op}_success", [])
    st.session_state.setdefault(f"{op}_fail", [])
st.session_state.setdefault("data", pd.DataFrame())


def main():
    st.header("Command Center")

    # Initialize the data to use in the app.
    st.session_state["data"] = utils.load_data(st.session_state.get("isLive", False))

    # App status bar
    pages.hq_actionbar()

    # Run Services
    st.button("Broadcast some messages to start the flow", on_click=services.publish_to_pipeline, type='primary', icon='📡')
    with st.spinner("Downloading and broadcasting assets...", show_time=True):
        pages.hq_broadcaster()

    # pages.hq_responder()
    # st.dataframe(st.session_state["data"].to_dict(orient="records"))

    with st.spinner("Building dashboard...", show_time=True):
        pages.image_tiles()

    with st.sidebar:
        # Show counters for processed assets
        pages.statusbar(services.HQ_SERVICES)


if __name__ == "__main__":
    logger.info("Running in HQ mode")
    main()
