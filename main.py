import json
import logging
import streamlit as st
import httpx
import pandas as pd
import mapr

st.set_page_config(page_title="Satellite images", layout="wide")

st.session_state.setdefault("logs", "")
st.session_state.setdefault("data", None)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_data(data):
    df = pd.DataFrame(data["collection"]["items"])
    # df.set_index("href", inplace=True)
    df["title"] = df["data"].apply(lambda x: x[0]["title"])
    df["description"] = df["data"].apply(lambda x: x[0]["description"])
    df["keywords"] = df["data"].apply(lambda x: ', '.join((x[0]["keywords"] if "keywords" in x[0] else [])))
    df["preview"] = df["links"].apply(lambda x: [l["href"] for l in x if l["rel"] == "preview"])
    df["asset"] = df["links"].apply(lambda x: [l["href"] for l in x if l["rel"] == "canonical"])
    df.drop("data", axis=1, inplace=True)
    df.drop("links", axis=1, inplace=True)
    return df


def query_nasa(search_term):
    params = { "media_type": "image", "q": search_term}
    r = httpx.get("https://images-api.nasa.gov/search", params=params)
    if r.status_code == 200:
        data = r.json()
        # st.json(data, expanded=False)
        return data


def main():

    with st.sidebar:
        mapr.get_credentials()


    isLive = st.toggle("Live", value=False)

    if isLive:
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


    st.title("Source")
    st.dataframe(st.session_state["data"], hide_index=True, height=200)

    st.title("Broadcast")

    assets = st.session_state.get("data", pd.DataFrame()).to_json(orient='records', lines=True).splitlines()
    # logger.info(len(assets))
    mapr.broadcast(assets)

    # row = st.columns(4)

    #
    # Image Download - service
    #
    #

    # for image_file in os.listdir("images"):
    #     st.image(image=os.path.join("images", image_file), caption=image_file)

    # images = []

    # st.code(st.session_state.get("logs", ""), language="text", height=300)


if __name__ == "__main__":
    main()
