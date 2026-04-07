import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *



def load_shared_state():
    """Load all shared state variables. Call at top of each page."""
    um    = st.session_state.get("user_manager")
    ud    = st.session_state.get("user_data", {})
    uname = st.session_state.get("username", "")
    em    = st.session_state.get("execute_manager")
    ri_pm = st.session_state.get("ri_pipeline_manager")
    prod_m= st.session_state.get("product_manager")
    pm    = st.session_state.get("pipeline_manager")
    vm_obj= st.session_state.get("validation_manager")
    lm    = st.session_state.get("leave_manager")
    ssm   = st.session_state.get("staff_status_manager")
    return um, ud, uname, em, ri_pm, prod_m, pm, vm_obj, lm, ssm
