import logging
import os
from random import random
import textwrap
from typing import Callable
import streamlit as st
import pandas as pd
import services
import settings
import utils

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
    st.sidebar.write(f"Cluster: {settings.MAPR_CLUSTER}")
    # st.sidebar.json(st.session_state)
    for key in st.session_state:
        value = st.session_state[key] if isinstance(st.session_state[key], bool) else len(st.session_state[key]) if isinstance(st.session_state[key], list) else len(st.session_state[key].index) if isinstance(st.session_state[key], pd.DataFrame) else st.session_state[key]
        st.sidebar.write(f"{key}: {value}")


@st.dialog("Asset Viewer", width='large')
def asset_viewer(asset: dict):
    logger.info("Opening asset viewer for %s", asset['title'])

    st.image(asset['preview'], caption=asset['title'])
    st.text(f"Description: {asset['description']}")
    st.text(f"Keywords: {asset.get('keywords', None)}")
    if "analysis" in asset:
        st.text(f"Category: {asset.get('analysis', None)}")
    if "object" in asset:
        st.text(f"Detected: {asset.get('object', None)}")
        st.chat_input(key="question", placeholder="Ask a question...", on_submit=questions_to_image, args=(asset["preview"].split('/')[-1], asset["description"],))
        st.session_state["ai_response"] = st.chat_message("ai")


@st.fragment
def tiles(generator: Callable, source: str, wait_message: str = "Loading tiles...", limit: int = 5, columns: int = 5, withImages: bool=False):
    index = 0
    with st.spinner(wait_message, show_time=True):
        grid = st.columns(columns)
        for item in generator() if limit == 0 else generator()[:-limit]:
            with grid[index%len(grid)].container(height=380, border=False):
                # st.subheader(source, divider=True, anchor=False)
                st.button(label=source.upper(), on_click=asset_viewer, args=(item,), key=f"{source}_{index}", type='tertiary')
                "---"
                if withImages:
                    st.image(item['preview'] if 'preview' in item else [], caption=item['title'], width=180)
                else:
                    st.text(item['title'][:20], help=item['title'])
                st.text(f"Category: {item['analysis']}")
                st.text(f"Description: {item['description'][:20]}{'...' if len(item['description']) > 20 else ''}", help=item['description'])
                st.text(f"Keywords: {item.get('keywords', '')[:20]}{'...' if len(item['description']) > 20 else ''}", help=item.get('keywords', None))
                if "object" in item:
                    st.text(f"Detected: {item['object']}")
                # st.button(label="", icon=":material/open_in_new:", on_click=asset_viewer, args=(item,), key=f"{source}_{index}")
                index += 1


@st.dialog(title="Demo flow", width="large")
def hq_diagram():
    st.image("./app_light.png") # TODO: when st delivers runtime theme detection, use that to pick the right image


@st.fragment
def hq_actionbar():
    # Connectivity status
    utils.stream_replication_status(settings.HQ_STREAM)
    # utils.volume_mirror_status()
    row = st.columns(4)
    row[0].toggle("Live Feed", key="isLive", help="Toggle live data fetching from NASA")
    # row[1].write(f"Volume Mirror: {':white_check_mark' if st.session_state.get('volume_mirror', False) else ':exclamation:'}")
    # row[2].toggle("Stream replication", key="stream_replication", help="Enable or disable stream replication", on_change=utils.toggle_stream_replication, args=(True,))
    row[2].write(f"Stream Replication: {':white_check_mark:'if st.session_state.get('stream_replication', False) else ':exclamation:'}")
    row[3].write(f"Mount Status: {':white_check_mark:' if os.path.exists(settings.MAPR_MOUNT) else ':exclamation:'}")

    if st.session_state["isLive"]:
        search_terms = ["missile", "earthquake", "tsunami", "oil", "flood", "iraq", "syria"]
        query = st.segmented_control(label="Assets", options=search_terms)
        st.session_state["data"] = utils.nasa_feed(isLive=True, query=query) # pyright: ignore
    else:
        st.session_state["data"] = utils.nasa_feed(isLive=False, query="")

    st.session_state["data"]
    # st.toast(f"Data loaded with {len(st.session_state['data'].index)} items.")

@st.fragment
def hq_broadcaster():
    # st.button("Broadcast", on_click=services.publish_to_pipeline, type='primary', icon='📡')
    services.publish_to_pipeline(int(10*random()))

    # tiles(generator=services.pipeline_to_broadcast, source='Broadcast', wait_message="Publishing assets...", columns=4, limit=0, withImages=True)
    for _ in services.pipeline_to_broadcast(): pass
    tiles(generator=lambda: [b for b in st.session_state['broadcast_success']], source='Broadcast', wait_message="Publishing assets...", columns=4, limit=0, withImages=True)


@st.fragment
def hq_responder():
    # for item in services.request_listener():
    #     st.success(f"Responded to: {item['title']}")
    tiles(generator=services.request_listener, source="Asset Request", wait_message="Checking for requests...", columns=4, limit=0, withImages=True)


@st.fragment
def edge_actionbar():
    row = st.columns(4)
    utils.stream_replication_status(settings.EDGE_STREAM)
    row[0].toggle("Stream replication", key="stream_replication", help="Enable or disable stream replication", on_change=utils.toggle_stream_replication, args=(False,))
    # row[1].write(f"Volume Mirror: {':white_check_mark' if st.session_state.get('volume_mirror', False) else ':exclamation:'}")
    row[2].write(f"Mount Status: {':white_check_mark:' if os.path.exists(settings.MAPR_MOUNT) else ':exclamation:'}")
    row[3].button("Mirror files", on_click=utils.start_volume_mirror, icon=":material/download:")


@st.fragment(run_every=30)
def edge_listen_for_responses():
    tiles(generator=services.response_listener, source="Asset Response", wait_message="Checking for responses...", columns=5, limit=0, withImages=True)


def edge_asset_viewer():
    view_assets = st.session_state["view_assets"]["selection"]["rows"]
    if len(view_assets) == 0: # no selection
        return
    asset = st.session_state["response_success"][view_assets[0]]
    logger.info("Object detection in: %s", asset['preview'].split('/')[-1])
    asset["object"] = utils.extract_objects(filename=asset["preview"].split('/')[-1])
    logger.info("Detected: %s", asset["object"])
    asset_viewer(asset)


@st.fragment
def edge_completed():
    st.dataframe(st.session_state["response_success"],
        selection_mode="single-row",
        on_select=edge_asset_viewer,
        key="view_assets"
    )


@st.fragment(run_every=30)
def edge_listen_for_assets():
    # tiles(generator=services.asset_listener, source="Broadcast", wait_message="Listening for assets...", columns=5, limit=0, withImages=False)
    with st.spinner("Listening for assets...", show_time=True):
        for asset in services.asset_listener():
            st.toast(f"Received asset: {asset['title']}")


# @st.fragment
# def edge_asset_list():
#     root = f"{settings.MAPR_MOUNT}/{settings.EDGE_ASSETS}"
#     logger.info("Listing files in %s", root)
#     files = []
#     for file in os.listdir(root):
#         logger.info(file)
#         files.append(file)
#     st.session_state["edge_asset_files"] = files
#     st.dataframe(st.session_state["edge_asset_files"])


@st.fragment
def edge_requester():
    st.dataframe([
        {
            'Status': a['status'] if 'status' in a else 'broadcast',
            'Title': a['title'].title(),
            'Description': a['description'],
            'Category': a['analysis'] if 'analysis' in a else 'Not analyzed',
        } for a in st.session_state["asset_broadcast"] ],
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        key="selected_assets",
        height=200
    )

    # st.dataframe(st.session_state["selected_assets"])
    for asset in services.asset_request():
        st.toast("Asset requested: {}".format(asset['title']))


@st.fragment
def statusbar(services: list):
    # Metrics
    row = st.columns(len(services))
    for index, service in enumerate(services):
        row[index].metric(service.title(), len(st.session_state.get(f"{service}_success", [])), delta=-len(st.session_state.get(f"{service}_fail", 0)))


def questions_to_image(filename: str, description: str):
    response = utils.ask_question(filename, description)
    logger.info("AI response: %s", response)
    st.session_state["ai_response"].write(response if response else "No response")
