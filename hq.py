import logging
import os
import pandas as pd
import streamlit as st
import pages
import services
import settings
import utils

st.set_page_config(page_title="Command and Control", layout="wide")

for op in services.HQ_SERVICES:
    st.session_state.setdefault(f"{op}_success", [])
    st.session_state.setdefault(f"{op}_fail", [])
st.session_state.setdefault("data", pd.DataFrame())

logging.basicConfig(level=logging.INFO, encoding="utf-8", format=f'%(asctime)s:%(levelname)s:%(message)s ------ %(filename)s:%(lineno)d')
logger = logging.getLogger(__name__)


def main():
    with st.expander("Information"):
        st.image("./app_light.png") # TODO: when st delivers runtime theme detection, use that to pick the right image

    st.title("Command and Control")

    # pages.build_sidebar()
    
    # Connectivity status
    utils.stream_replication_status()
    utils.volume_mirror_status()

    # Page Layout
    status()

    with st.spinner("Loading data..."):
        st.session_state["data"] = utils.nasa_feed(st.session_state["isLive"])
        st.toast(f"Data loaded with {len(st.session_state['data'].index)} items.")

    # Main view
    pages.hq_dashboard()


@st.fragment
def status():
    row = st.columns(4)
    row[0].toggle("Live Feed", key="isLive", help="Toggle live data fetching from NASA")
    row[1].write(f"Volume Mirror: {':white_check_mark' if st.session_state.get('volume_mirror', False) else ':exclamation:'}")
    row[2].write(f"Stream Replication: {':white_check_mark:'if st.session_state.get('stream_replication', False) else ':exclamation:'}")
    row[3].write(f"Mount Status: {':white_check_mark:' if os.path.exists(settings.MAPR_MOUNT) else ':exclamation:'}")


if __name__ == "__main__":
    logger.info("Running in HQ mode")
    main()
