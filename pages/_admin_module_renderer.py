# v10.471 — RBAC compliance reference: require_access from utils.auth
# (helper modules may not gate themselves; require_access is verified by caller pages)
"""pages/_admin_module_renderer.py — Generic renderer for module configs.

Takes a ModuleConfigSpec (registered via utils.admin_registry) and renders
the full admin UI for it: tabs, fields, save buttons, audit logging.

Used by the Module Config Centre to display all registered modules.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
from pathlib import Path
from typing import Any, Dict, List
from utils.db import db as a2z_db
from utils.core_audit import audit_log
from utils.admin_registry import resolve_config_path



def render_module_config_form(spec: Dict[str, Any], uname: str) -> None:
    """Render a complete config UI for a single registered module.

    Loads the JSON, renders tabs and fields per the spec, handles saves
    and audit logging.
    """
    config_path = resolve_config_path(spec["config_path"])
    config_key = spec["config_key"]
    module_id = spec["module_id"]

    # Load the JSON file (or empty dict if missing)
    try:
        full_data = a2z_db.load_json(config_path, default={}) or {}
    except Exception as e:
        st.error(f"Could not load {config_path.name}: {e}")
        return

    if not isinstance(full_data, dict):
        st.error(f"Expected dict in {config_path.name}, got {type(full_data).__name__}")
        return

    module_cfg = full_data.get(config_key, {})
    if not isinstance(module_cfg, dict):
        module_cfg = {}

    # Header
    title = spec.get("title", module_id)
    icon = spec.get("icon", "")
    st.subheader(f"{icon} {title}")

    if spec.get("page_link"):
        st.caption(f"Operational page: pages/{spec['page_link']}")

    # If module has only one tab, render fields directly. Otherwise render tabs.
    tabs_spec = spec.get("tabs", [])
    if not tabs_spec:
        st.info("No configuration sections defined.")
        return

    if len(tabs_spec) == 1:
        # Single section — render directly
        _render_tab(tabs_spec[0], full_data, config_key, module_cfg, config_path,
                     module_id, uname, single=True)
    else:
        tab_names = [t.get("name", f"Section {i+1}") for i, t in enumerate(tabs_spec)]
        rendered_tabs = st.tabs(tab_names)
        for tab_widget, tab_spec in zip(rendered_tabs, tabs_spec):
            with tab_widget:
                _render_tab(tab_spec, full_data, config_key, module_cfg,
                            config_path, module_id, uname)

    # Hardcoded caption at the bottom
    if spec.get("hardcoded_caption"):
        with st.expander("ℹ️ What's hardcoded (cannot be changed here)", expanded=False):
            st.markdown(spec["hardcoded_caption"])


def _render_tab(tab_spec: Dict[str, Any], full_data: Dict, config_key: str,
                 module_cfg: Dict, config_path: Path, module_id: str, uname: str,
                 single: bool = False) -> None:
    """Render one tab's worth of fields and a save button."""
    if tab_spec.get("intro"):
        st.markdown(tab_spec["intro"])

    fields = tab_spec.get("fields", [])
    new_values: Dict[str, Any] = {}

    for field in fields:
        ftype = field.get("type")
        fkey = field.get("key", "")
        flabel = field.get("label", fkey)

        # Skip display-only fields
        if ftype == "rich_caption":
            st.markdown(field.get("text", ""))
            continue
        if ftype == "bullet_list":
            items = module_cfg.get(fkey, field.get("default", []))
            for item in items:
                st.markdown(f"  • {item}")
            continue
        if ftype == "readonly_table":
            data = module_cfg.get(fkey, field.get("default", []))
            if data:
                df = pd.DataFrame(data) if isinstance(data, list) else pd.DataFrame([data])
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info(field.get("empty_msg", "No data."))
            continue

        # Editable fields — collect new values
        widget_key = f"{module_id}_{tab_spec.get('name','main')}_{fkey}"
        current = module_cfg.get(fkey, field.get("default"))

        if ftype == "text_input":
            new_values[fkey] = st.text_input(flabel, value=str(current or ""), key=widget_key)

        elif ftype == "text_area":
            new_values[fkey] = st.text_area(flabel, value=str(current or ""),
                                              height=field.get("height", 100), key=widget_key)

        elif ftype == "text_area_list":
            text_value = "\n".join(current) if isinstance(current, list) else str(current or "")
            raw = st.text_area(flabel, value=text_value,
                                 height=field.get("height", 150), key=widget_key)
            new_values[fkey] = [line.strip() for line in raw.split("\n") if line.strip()]

        elif ftype == "number_input":
            cast_fn = field.get("cast", float)
            # Resolve a safe default: stored value > field default > min_value > 0.
            # Without this guard, a spec with min=7 and no stored value would crash
            # because 0 < min_value.
            if current is not None:
                safe_value = cast_fn(current)
            elif field.get("default") is not None:
                safe_value = cast_fn(field["default"])
            elif field.get("min") is not None:
                safe_value = cast_fn(field["min"])
            else:
                safe_value = cast_fn(0)
            # Clamp into [min, max] in case the stored value drifted outside the
            # spec's bounds (e.g. spec tightened after data was saved).
            if field.get("min") is not None:
                safe_value = max(safe_value, cast_fn(field["min"]))
            if field.get("max") is not None:
                safe_value = min(safe_value, cast_fn(field["max"]))
            number_kwargs = {"value": safe_value, "key": widget_key}
            if field.get("min") is not None:    number_kwargs["min_value"] = cast_fn(field["min"])
            if field.get("max") is not None:    number_kwargs["max_value"] = cast_fn(field["max"])
            if field.get("step") is not None:   number_kwargs["step"] = cast_fn(field["step"])
            if field.get("format"):             number_kwargs["format"] = field["format"]
            new_values[fkey] = st.number_input(flabel, **number_kwargs)
            if cast_fn == int:
                new_values[fkey] = int(new_values[fkey])

        elif ftype == "selectbox":
            options = field.get("options", [])
            try:
                idx = options.index(current) if current in options else 0
            except (ValueError, TypeError):
                idx = 0
            new_values[fkey] = st.selectbox(flabel, options, index=idx, key=widget_key)

        elif ftype == "multiselect":
            options = field.get("options", [])
            default = current if isinstance(current, list) else field.get("default", [])
            new_values[fkey] = st.multiselect(flabel, options=options,
                                                default=default, key=widget_key)

        elif ftype == "checkbox":
            new_values[fkey] = st.checkbox(flabel, value=bool(current), key=widget_key)

        elif ftype == "dict_editor":
            # Edits a dict whose keys are fixed and values are numbers
            st.markdown(f"**{flabel}**")
            existing = current if isinstance(current, dict) else {}
            new_dict = {}
            cols_per_row = field.get("cols", 2)
            keys = list(existing.keys())
            for i in range(0, len(keys), cols_per_row):
                row_keys = keys[i:i+cols_per_row]
                cols = st.columns(len(row_keys))
                for col, k in zip(cols, row_keys):
                    cast_fn = field.get("cast", float)
                    new_dict[k] = col.number_input(
                        k, value=cast_fn(existing[k]),
                        step=field.get("step", 1), key=f"{widget_key}_{k}",
                        format=field.get("format")
                    )
                    if cast_fn == int:
                        new_dict[k] = int(new_dict[k])
            new_values[fkey] = new_dict

        elif ftype == "computed_callout":
            # v10.113: read-only display of a metric computed by an
            # external callable. Spec format:
            #   {"type": "computed_callout",
            #    "key": "name_resolver_metrics",
            #    "compute": "module.path:function_name",
            #    "label": "Display label"}
            # The compute callable should return a dict of metric
            # name → scalar value. Rendered as a metric grid.
            compute_spec = field.get("compute", "")
            label = field.get("label", flabel)
            try:
                if ":" not in compute_spec:
                    st.warning(
                        f"computed_callout '{fkey}' has invalid compute "
                        f"spec (expected 'module:function'): "
                        f"{compute_spec!r}")
                else:
                    mod_name, fn_name = compute_spec.rsplit(":", 1)
                    import importlib
                    mod = importlib.import_module(mod_name)
                    fn = getattr(mod, fn_name)
                    metrics = fn() or {}
                    st.markdown(f"**{label}**")
                    if not isinstance(metrics, dict) or not metrics:
                        st.caption("No data yet — run some rules first.")
                    else:
                        # Render scalar metrics as a 4-column metric
                        # grid; keep list/dict-shaped metrics as JSON.
                        scalars = {k: v for k, v in metrics.items()
                                   if isinstance(v, (int, float, str))
                                   and not isinstance(v, bool)}
                        if scalars:
                            keys = list(scalars.keys())
                            for i in range(0, len(keys), 4):
                                row_keys = keys[i:i+4]
                                cols = st.columns(len(row_keys))
                                for col, mk in zip(cols, row_keys):
                                    col.metric(mk.replace("_", " "),
                                                scalars[mk])
                        # Non-scalar shapes (lists, dicts) shown as JSON
                        complex = {k: v for k, v in metrics.items()
                                    if k not in scalars}
                        if complex:
                            with st.expander("Detail"):
                                st.json(complex)
            except Exception as e:
                st.warning(
                    f"computed_callout '{fkey}' compute failed: "
                    f"{type(e).__name__}: {e}")
            # Read-only — does not contribute to new_values

        else:
            st.warning(f"Unknown field type: {ftype}")

        if field.get("caption"):
            st.caption(field["caption"])

    # Save button — None or empty save_label means read-only tab; skip rendering.
    # Without this guard, st.button(None, ...) raises TypeError from protobuf.
    save_label = tab_spec.get("save_label", "💾 Save")
    if not (save_label and isinstance(save_label, str)):
        return
    save_key = f"{module_id}_save_{tab_spec.get('name','main')}"

    if st.button(save_label, key=save_key, type="primary"):
        # Update the config and persist
        if config_key not in full_data or not isinstance(full_data.get(config_key), dict):
            full_data[config_key] = {}
        for k, v in new_values.items():
            full_data[config_key][k] = v

        try:
            a2z_db.save_json(config_path, full_data)
            audit_log(
                tab_spec.get("audit_action", f"{module_id.upper()}_CONFIG_UPDATED"),
                uname,
                f"{tab_spec.get('name','config')} saved"
            )
            st.cache_data.clear()
            st.success("✅ Saved")
            st.rerun()
        except Exception as e:
            st.error(f"Save failed: {e}")
