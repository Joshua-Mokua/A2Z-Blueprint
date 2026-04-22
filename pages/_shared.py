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


def get_user_proposition():
    """Return proposition tag if the logged-in user is a proposition head, else None."""
    try:
        from pathlib import Path as _Path
        import json as _json
        import streamlit as _st
        ud = _st.session_state.get("user_data", {})
        role = ud.get("role", "")
        cfg_path = _Path(__file__).parent.parent / "data" / "proposition_config.json"
        if not cfg_path.exists():
            return None
        cfg = _json.loads(cfg_path.read_text())
        for tag, prop in cfg.get("propositions", {}).items():
            if prop.get("active", True) and prop.get("head_role", "") == role:
                return tag
        return None
    except Exception:
        return None


def get_proposition_filter(module_data, tag_field="proposition_tag"):
    """
    If user is a proposition head, return only items matching their tag.
    Otherwise return all items (normal view).
    tag_field: the field name in each record that holds the proposition tag.
    """
    import streamlit as _st
    ud   = _st.session_state.get("user_data", {})
    prop_tag = get_user_proposition()
    if not prop_tag:
        return module_data, None   # not a proposition head — see everything
    filtered = [item for item in module_data
                if item.get(tag_field) == prop_tag]
    return filtered, prop_tag


def safe_html(text: str) -> str:
    """Escape user-supplied text before embedding in HTML.
    Always use this when inserting user data into unsafe_allow_html blocks."""
    if not isinstance(text, str):
        text = str(text)
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;")
            .replace("/", "&#x2F;"))

