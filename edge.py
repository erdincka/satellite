import streamlit as st
import logging

st.set_page_config(page_title="Unit XX - Mission Control", layout="wide")

logging.basicConfig(level=logging.INFO, encoding="utf-8", format='%(levelname)s:%(filename)s:%(lineno)d:%(message)s')
logger = logging.getLogger(__name__)


def main():
    st.title("Living at the edge")


if __name__ == "__main__":
    logger.info("Starting app in Edge mode")
    main()
