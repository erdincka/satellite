import logging
import os
import pandas as pd
import streamlit as st
import pages
import services
import settings
import utils
import vlm

st.set_page_config(page_title="Command and Control", layout="wide")

for op in services.HQ_SERVICES:
    st.session_state.setdefault(f"{op}_success", [])
    st.session_state.setdefault(f"{op}_fail", [])
st.session_state.setdefault("data", pd.DataFrame())

logging.basicConfig(level=logging.INFO, encoding="utf-8", format=f'%(asctime)s:%(levelname)s:%(filename)s:%(lineno)d:%(message)s')
logger = logging.getLogger(__name__)


def main():
    st.header("Command Center")
    # pages.build_sidebar()
    # Page Layout
    pages.hq_actionbar()

    pages.statusbar(services.HQ_SERVICES)

    # Main view
    pages.hq_broadcaster()

    pages.hq_responder()

    # with st.expander("Information"):
    #     st.image("./demo_light.png") # TODO: when st delivers runtime theme detection, use that to pick the right image
    # pages.hq_diagram()

    st.divider()

    "Request"
    st.dataframe(st.session_state["request_success"])
    "Response"
    st.dataframe(st.session_state["response_success"])

if __name__ == "__main__":
    logger.info("Running in HQ mode")
    main()
