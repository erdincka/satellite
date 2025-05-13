import streamlit as st
import httpx


REST_URL = f"https://{st.session_state.get('maprhost')}:8443/rest"
STREAM = "satellite"
TOPIC = "broadcast"

user = st.session_state.get('mapruser', 'mapr')
password = st.session_state.get('maprpass', 'mapr')

def get_credentials():
    st.write("Data Fabric")
    st.text_input("Host", placeholder="Hostname/IP", key="maprhost")
    st.text_input("User", placeholder="mapr", key="mapruser")
    st.text_input("Password", placeholder="mapr", type="password", key="maprpass")
    st.button("Connect", on_click=connect_and_configure)


def connect_and_configure():
    """
    Try connection to Data Fabric and configure for required settings, i.e., streams and volumes, for the app
    """

    try:
        # Create stream
        s = httpx.post(f"{REST_URL}/stream/create?path={STREAM}&ttl=3600", auth=(user, password), verify=False)

        if s.status_code == 200:
            st.info(s.json())
        else:
            st.error(s.text)

    except Exception as error:
        st.error(error)

    # if r.status_code == 200:
    #     st.sidebar.write("Connected")
    #     st.sidebar.code(r.json())
    # else:
    #     st.sidebar.error("Connection failed")

def broadcast(items: list):
    for item in items:
        s = httpx.post(f"{REST_URL}/stream/create?path={STREAM}&ttl=3600", auth=(user, password), verify=False)

        if s.status_code == 200:
            st.info(s.json())
        else:
            st.error(s.text)
