import streamlit as st
import logging

import pages
import services
import utils


st.set_page_config(page_title="Unit XX - Mission Control", layout="wide")

for op in services.EDGE_SERVICES:
    st.session_state.setdefault(f"{op}_success", [])
    st.session_state.setdefault(f"{op}_fail", [])
st.session_state.setdefault("asset_broadcast", [])


logging.basicConfig(level=logging.INFO, encoding="utf-8", format='%(asctime)s:%(levelname)s:%(filename)s:%(lineno)d:%(message)s')
logger = logging.getLogger(__name__)


def main():
    st.title("Unit X - Mission Control")


    utils.stream_replication_status()

    row = st.columns(4)
    row[0].toggle("Stream replication", key="stream_replication", help="Enable or disable stream replication", on_change=utils.toggle_stream_replication)
    row[1].write(f"Volume Mirror: {':white_check_mark' if st.session_state.get('volume_mirror', False) else ':exclamation:'}")
    row[-1].button("Start volume mirroring", on_click=utils.toggle_volume_mirror)

    pages.edge_dashboard()
    # with st.spinner("Requesting assets...", show_time=True):
    for asset in services.asset_request():
        st.toast("Asset requested: {}".format(asset['title']))
    
    with st.spinner("Listening for responses...", show_time=True):
        pages.tiles(generator=services.response_listener, source="ASSET RESPONSE", wait_message="Waiting for asset responses...", columns=5, limit=0)

    st.dataframe([
        { 
            'Title': a['title'].title(),
            'Description': a['description'],
            'Status': a['status'] if 'status' in a else 'broadcast',
        } for a in st.session_state["asset_broadcast"] ],
        hide_index=True,
        selection_mode="multi-row",
        on_select="rerun",
        key="selected_assets",
        height=200
    )


if __name__ == "__main__":
    logger.info("Starting app in Edge mode")
    main()
