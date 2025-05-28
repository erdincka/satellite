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


def main():
    st.header("Command Center")

    # Initialize the data to use in the app.
    utils.load_data(st.session_state.get("isLive", False))

    # App status bar
    pages.hq_actionbar()

    # Run Services
    st.button("Broadcast some messages to start the flow", on_click=services.publish_to_pipeline, type='primary', icon='📡')
    pages.hq_broadcaster()
    #
    # pages.hq_responder()

    # st.dataframe(st.session_state["data"].to_dict(orient="records"))
    # pages.image_tiles(st.session_state["data"].to_dict(orient="records"), "Feed")
    pages.image_tiles(st.session_state["pipeline_success"], "Pipeline")
    pages.image_tiles(st.session_state["download_success"], "Download")
    pages.image_tiles(st.session_state["broadcast_success"], "Broadcast")

    # DEBUG
    # "Request"
    # st.dataframe(st.session_state["request_success"])
    # "Response"
    # st.dataframe(st.session_state["response_success"])

    # Show counters for processed assets
    pages.statusbar(services.HQ_SERVICES)

if __name__ == "__main__":
    logger.info("Running in HQ mode")
    main()
