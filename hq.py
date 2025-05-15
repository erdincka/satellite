import json
import logging
import os
import streamlit as st
import httpx
import pandas as pd
import mapr
import settings
import streams
import iceberger

st.set_page_config(page_title="Command and Control", layout="wide")
st.session_state.setdefault("isMonitoring", settings.isMonitoring)
st.session_state.setdefault("isDebugging", settings.isDebugging)
st.session_state.setdefault("data", None)
st.session_state.setdefault("bcast_success", [])
st.session_state.setdefault("bcast_fail", [])
st.session_state.setdefault("dload_success", [])
st.session_state.setdefault("dload_fail", [])

logging.basicConfig(level=logging.INFO, encoding="utf-8", format='%(levelname)s:%(filename)s:%(lineno)d:%(message)s')
logger = logging.getLogger(__name__)

def parse_data(data):
    df = pd.DataFrame(data["collection"]["items"])
    # df.set_index("href", inplace=True)
    df["title"] = df["data"].apply(lambda x: x[0]["title"])
    df["description"] = df["data"].apply(lambda x: x[0]["description"])
    df["keywords"] = df["data"].apply(lambda x: ', '.join((x[0]["keywords"] if "keywords" in x[0] else [])))
    df["preview"] = df["links"].apply(lambda x: [link["href"] for link in x if link["rel"] == "preview"][0])
    df.drop("data", axis=1, inplace=True)
    # df.drop("links", axis=1, inplace=True)
    return df


def query_nasa(search_term):
    params = { "media_type": "image", "q": search_term}
    r = httpx.get("https://images-api.nasa.gov/search", params=params)
    if r.status_code == 200:
        data = r.json()
        # st.json(data, expanded=False)
        return data

def analyze_image(filename: str):
    logger.info("Analyzing %s", filename)
    return "Not implemented"


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
    st.sidebar.toggle("Live", key="isLive", value=False)
    st.sidebar.toggle("Monitor Topic", key="isMonitoring", value=False)
    st.sidebar.toggle("Debug", key="isDebugging", value=False)

    if st.session_state["isMonitoring"]:
        st.sidebar.title("Monitoring")
        st.sidebar.slider(
            "Check for updates every: (seconds)",
            0.5,
            5.0,
            value=2.0,
            key="run_every",
            step=0.5,
            help="Check every X seconds",
        )
    # Debug info
    if st.session_state["isDebugging"]:
        st.sidebar.title("Debugging")
        st.sidebar.write(f"Cluster: {settings.MAPR_CLUSTER}")
        st.sidebar.write(f"HQ Stream: {settings.HQ_STREAM}")
        st.sidebar.write(
            f"Broadcast Topic: {settings.HQ_STREAM}:{settings.BROADCAST_TOPIC}"
        )
        st.sidebar.write("Session State:")
        st.sidebar.json(st.session_state)


def main():
    build_sidebar()

    if st.session_state["isLive"]:
        search_terms = ["missile", "earthquake", "tsunami", "oil", "flood", "iraq", "syria"]
        search_term = st.segmented_control(label="Assets", options=search_terms)
        with st.spinner("Querying NASA", show_time=True):
            data = query_nasa(search_term)
        st.session_state["data"] = parse_data(data)

    else:
        with st.spinner("Loading file", show_time=True):
            with open("images.json", "r") as f:
                data = json.loads(f.read())
                st.session_state["data"] = parse_data(data)


    # st.title("Source")
    # st.dataframe(st.session_state["data"], hide_index=True, height=200)
    counters = st.columns(4, border=True)
    counters[0].write("Published")
    counters[0].badge(str(len(st.session_state["bcast_success"])), icon=":material/check:", color="green")
    counters[1].write("Failed to publish")
    counters[1].badge(str(len(st.session_state["bcast_fail"])), icon=":material/close:", color="red")
    counters[2].write("Downloaded")
    counters[2].badge(str(len(st.session_state["dload_success"])), icon=":material/close:", color="green")
    counters[3].write("Failed to download")
    counters[3].badge(str(len(st.session_state["dload_fail"])), icon=":material/close:", color="red")

    # Broadcast assets
    assets = st.session_state.get("data", pd.DataFrame()).to_json(orient='records', lines=True).splitlines() # pyright: ignore[reportOptionalMemberAccess]
    # logger.info(len(assets))
    for success, item in mapr.broadcast(assets[:10]):
        i = json.loads(item)
        if success:
            logger.info("Published: %s", i["title"])
            st.session_state["bcast_success"].append(i)
        else:
            logger.info("Failed to publish: %s", i["title"])
            st.session_state["bcast_fail"].append(i)

    # HQ workflow starts here by consuming broadcasted assets
    for msg in streams.consume(f"{settings.HQ_STREAM}", "broadcast"):
        item = json.loads(msg)
        logger.info("Received: %s", item["title"])
        logger.info(item)
        logger.debug("Downloading from: %s", item["preview"])
        filename = mapr.save_from_url(item["preview"], st.session_state["isLive"])
        if filename:
            st.session_state["dload_success"].append(item)
            # Run AI narration on the image
            item["analysis"] = analyze_image(filename)
            # Update the table with the analysis
            if iceberger.write("hq", "asset_table", [item]):
                if streams.produce(settings.HQ_STREAM, settings.ASSET_TOPIC, json.dumps(item)):
                    logger.info("Published: %s", item["title"])
                    st.session_state["bcast_success"].append(item)
            else:
                st.error("Failed to publish")
        else:
            st.session_state["dload_fail"].append(item)

    logger.info("Done with processing HQ assets")



    # for image_file in os.listdir("images"):
    #     st.image(image=os.path.join("images", image_file), caption=image_file)

    # images = []

    # st.code(st.session_state.get("logs", ""), language="text", height=300)

if __name__ == "__main__":
    logger.info("Running in HQ mode")
    main()
