import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *


def load_shared_state():
    """
    Load all shared session state.
    Returns 12 values — always pads with None so unpacking never fails
    even if some managers were not yet initialised on the running machine.
    """
    vals = [
        st.session_state.get("user_manager"),
        st.session_state.get("user_data", {}),
        st.session_state.get("username", ""),
        st.session_state.get("execute_manager"),
        st.session_state.get("ri_pipeline_manager"),
        st.session_state.get("product_manager"),
        st.session_state.get("pipeline_manager"),
        st.session_state.get("leave_manager"),
        st.session_state.get("hr_manager"),
        st.session_state.get("cascade_manager"),
        st.session_state.get("validation_manager"),
        st.session_state.get("reporting_line_manager"),
    ]
    # Always return exactly 12 values, padded with None
    while len(vals) < 12:
        vals.append(None)
    return tuple(vals[:12])
