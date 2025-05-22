import os
import streamlit as st
import logging

import pages
import services
import settings
import utils


st.set_page_config(page_title="Unit XX - Mission Control", layout="wide")

for op in services.EDGE_SERVICES:
    st.session_state.setdefault(f"{op}_success", [])
    st.session_state.setdefault(f"{op}_fail", [])
st.session_state.setdefault("asset_broadcast", [])
st.session_state.setdefault("edge_asset_files", [])
st.session_state.setdefault("ai_response", None)


logging.basicConfig(level=logging.INFO, encoding="utf-8", format=f'%(asctime)s:%(levelname)s:%(filename)s:%(lineno)d:%(message)s')
logger = logging.getLogger(__name__)


def main():
    st.header("Mission Control")
    pages.edge_actionbar()

    pages.statusbar(services.EDGE_SERVICES)

    pages.edge_listen_for_assets()

    pages.edge_listen_for_responses()

    "Feed"
    pages.edge_requester()

    "Requests"
    st.dataframe(st.session_state["request_success"])

    "Responses"
    pages.edge_completed()

    # pages.edge_asset_list()


if __name__ == "__main__":
    logger.info("Starting app in Edge mode")
    main()
