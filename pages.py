import logging
import textwrap
from typing import Callable
import streamlit as st
import services
import settings

logger = logging.getLogger(__name__)

def build_sidebar():
    cols = st.sidebar.columns(2)
    cols[0].link_button(
        "DFUI",
        f"https://{settings.MAPR_USER}:{settings.MAPR_PASSWORD}@{settings.MY_HOSTNAME}:8443/app/dfui",
        type="tertiary",
        icon=":material/home:",
    )
    cols[1].link_button(
        "MCS",
        f"https://{settings.MAPR_USER}:{settings.MAPR_PASSWORD}@{settings.MY_HOSTNAME}:8443/app/mcs",
        type="tertiary",
        icon=":material/settings:",
    )

    # Debug info
    if st.session_state["isDebugging"]:
        st.sidebar.title("Debugging")
        st.sidebar.write(f"Cluster: {settings.MAPR_CLUSTER}")
        # st.sidebar.write("Session State:")
        st.sidebar.json(st.session_state)


@st.dialog("Asset Viewer", width='large')
def asset_viewer(asset):
    logger.info("Opening asset viewer for %s", asset['title'])
    with st.container():
        st.image(asset['preview'], caption=asset['title'])
        st.text(f"Description: {asset['description']}")
        st.text(f"Tags: {asset.get('keywords', None)}")


@st.fragment
def tiles(generator: Callable, source: str, wait_message: str = "Loading tiles...", limit: int = 5, columns: int = 5):
    index = 0
    with st.spinner(wait_message, show_time=True):
        grid = st.columns(columns)
        for item in generator() if limit == 0 else generator()[:-limit]:
            with grid[index%len(grid)].container(height=380, border=False):
                st.subheader(source, divider=True, anchor=False)
                st.image(item['preview'] if 'preview' in item else [], caption=item['title'], width=180)
                st.text(f"Description: {textwrap.shorten(item['description'], width=40)}")
                st.text(f"Tags: {textwrap.shorten(item.get('keywords', None), width=40)}")
                st.button(label="", icon=":material/open_in_new:", on_click=asset_viewer, args=(item,), key=f"{source}_{index}")
                index += 1


@st.fragment
def edge_dashboard():

    tiles(generator=services.asset_listener, source="NASA FEED", wait_message="Listening for assets...", columns=5, limit=0)

    # Metrics
    row = st.columns(len(services.EDGE_SERVICES))
    for index, service in enumerate(services.EDGE_SERVICES):
        row[index].metric(service.title(), len(st.session_state.get(f"{service}_success", [])), delta=-len(st.session_state.get(f"{service}_fail", 0)))


@st.fragment
def hq_dashboard():
    # st.button("Broadcast", on_click=services.publish_to_pipeline, type='primary', icon='📡')
    services.publish_to_pipeline()

    tiles(generator=services.pipeline_to_broadcast, source='NASA Feed', wait_message="Publishing assets...", columns=4, limit=0)

    for item in services.request_listener():
        st.success(f"Responded to: {item['title']}")

    # Metrics
    row = st.columns(len(services.HQ_SERVICES))
    for index, service in enumerate(services.HQ_SERVICES):
        row[index].metric(service.title(), len(st.session_state.get(f"{service}_success", [])), delta=-len(st.session_state.get(f"{service}_fail", 0)))

