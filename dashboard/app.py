"""Streamlit dashboard for OptiMind optimization results visualization."""

import os
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000/api/v1")


def call_optimize_api(source: str, problem_type: str | None = None) -> dict[str, Any]:
    """Call the OptiMind optimization API."""
    payload: dict[str, Any] = {"source": source}
    if problem_type and problem_type != "auto":
        payload["problem_type"] = problem_type
    try:
        response = requests.post(
            f"{API_BASE_URL}/optimize", json=payload, timeout=300
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        st.error(f"API call failed: {exc}")
        return {"status": "error", "errors": [str(exc)]}


def render_execution_graph(stages: list[str]) -> None:
    """Render the pipeline execution trace as a horizontal flow."""
    if not stages:
        st.info("No pipeline stages were executed.")
        return
    cols = st.columns(len(stages))
    stage_icons = {
        "data_intelligence": "1. Data",
        "knowledge_retrieval": "2. Knowledge",
        "modeling": "3. Model",
        "verification": "4. Verify",
        "solver": "5. Solve",
        "decision": "6. Decision",
    }
    for col, stage in zip(cols, stages, strict=False):
        col.markdown(f"**{stage_icons.get(stage, stage)}**")


def render_variable_summaries(report: dict[str, Any]) -> None:
    """Render decision variable summaries as a table and bar chart."""
    summaries = report.get("variable_summaries", [])
    if not summaries:
        st.info("No variable summaries available.")
        return
    rows: list[dict[str, Any]] = []
    for var in summaries:
        val = var.get("value", 0.0)
        if isinstance(val, dict):
            for idx, v in val.items():
                rows.append({
                    "variable": f"{var['name']}[{idx}]",
                    "value": float(v),
                    "description": var.get("description", ""),
                })
        else:
            rows.append({
                "variable": var["name"],
                "value": float(val),
                "description": var.get("description", ""),
            })
    df = pd.DataFrame(rows)
    st.subheader("Decision Variables")
    st.dataframe(df, use_container_width=True)
    if len(df) > 0:
        chart_df = df.set_index("variable")["value"]
        st.bar_chart(chart_df)


def render_constraint_statuses(report: dict[str, Any]) -> None:
    """Render constraint binding and slack status."""
    constraints = report.get("constraint_statuses", [])
    if not constraints:
        st.info("No constraint status available.")
        return
    rows: list[dict[str, Any]] = []
    for con in constraints:
        rows.append({
            "constraint": con["name"],
            "slack": con.get("slack"),
            "is_binding": con.get("is_binding", False),
            "is_violated": con.get("is_violated", False),
        })
    df = pd.DataFrame(rows)
    st.subheader("Constraint Status")
    st.dataframe(df, use_container_width=True)


def render_sensitivity(report: dict[str, Any]) -> None:
    """Render sensitivity analysis results."""
    results = report.get("sensitivity_results", [])
    if not results:
        st.info("No sensitivity analysis available.")
        return
    rows: list[dict[str, Any]] = []
    for s in results:
        rows.append({
            "parameter": s.get("parameter_name", ""),
            "current_value": s.get("current_value"),
            "allow_increase": s.get("allowable_increase"),
            "allow_decrease": s.get("allowable_decrease"),
            "shadow_price": s.get("shadow_price"),
        })
    df = pd.DataFrame(rows)
    st.subheader("Sensitivity Analysis")
    st.dataframe(df, use_container_width=True)


def render_scenarios(report: dict[str, Any]) -> None:
    """Render scenario comparison results."""
    scenarios = report.get("scenario_comparisons", [])
    if not scenarios:
        st.info("No scenario comparison available.")
        return
    rows: list[dict[str, Any]] = []
    for sc in scenarios:
        rows.append({
            "scenario": sc.get("scenario_name", ""),
            "baseline": sc.get("baseline_objective"),
            "scenario_obj": sc.get("scenario_objective"),
            "delta": sc.get("objective_delta"),
            "delta_pct": sc.get("objective_delta_pct"),
        })
    df = pd.DataFrame(rows)
    st.subheader("Scenario Comparison")
    st.dataframe(df, use_container_width=True)
    if len(df) > 1:
        chart_df = df[["scenario", "baseline", "scenario_obj"]].set_index("scenario")
        st.line_chart(chart_df)


def render_risks(report: dict[str, Any]) -> None:
    """Render risk assessment items."""
    risks = report.get("risk_items", [])
    if not risks:
        st.info("No risk items identified.")
        return
    st.subheader("Risk Assessment")
    for risk in risks:
        sev = risk.get("severity", "medium").lower()
        color = {"high": "#e74c3c", "medium": "#f39c12", "low": "#27ae60"}.get(
            sev, "#3498db"
        )
        st.markdown(
            f"<div style='border-left:4px solid {color}; padding:8px; margin:4px 0;'>"
            f"<strong>{risk.get('category', '')}</strong> "
            f"- <span style='color:{color}'>{risk.get('severity', '')}</span>"
            f"<br>{risk.get('description', '')}"
            f"<br><em>Mitigation:</em> {risk.get('mitigation', 'N/A')}"
            f"</div>",
            unsafe_allow_html=True,
        )


def render_recommendations(report: dict[str, Any]) -> None:
    """Render business recommendations."""
    recs = report.get("recommendations", [])
    if not recs:
        st.info("No recommendations available.")
        return
    st.subheader("Recommendations")
    for rec in recs:
        pri = rec.get("priority", "medium").lower()
        color = {"high": "#e74c3c", "medium": "#f39c12", "low": "#3498db"}.get(
            pri, "#3498db"
        )
        st.markdown(
            f"<div style='border-left:4px solid {color}; padding:8px; margin:4px 0;'>"
            f"<strong>{rec.get('title', rec.get('category', ''))}</strong> "
            f"- <span style='color:{color}'>{rec.get('priority', '')}</span>"
            f"<br>{rec.get('description', '')}"
            f"<br><em>Expected Impact:</em> {rec.get('expected_impact', 'N/A')}"
            f"</div>",
            unsafe_allow_html=True,
        )


def main() -> None:
    """Main Streamlit dashboard entrypoint."""
    st.set_page_config(
        page_title="OptiMind - Optimization Copilot",
        page_icon=":brain:",
        layout="wide",
    )
    st.title("OptiMind - Optimization Copilot")
    st.markdown("AI-native Decision Intelligence Platform for Operations Research")

    # Sidebar configuration
    with st.sidebar:
        st.header("Configuration")

        # File upload or path input
        input_method = st.radio(
            "Input method",
            options=["Upload file", "Enter path"],
            help="Choose how to provide your data",
        )

        source_path = ""
        if input_method == "Upload file":
            uploaded = st.file_uploader(
                "Upload CSV",
                type=["csv"],
                help="Upload a CSV file with your optimization data",
            )
            if uploaded is not None:
                # Save to temp location
                temp_dir = Path(".temp_uploads")
                temp_dir.mkdir(exist_ok=True)
                temp_path = temp_dir / uploaded.name
                temp_path.write_bytes(uploaded.getvalue())
                source_path = str(temp_path.resolve())
                st.success(f"Uploaded: {uploaded.name}")
        else:
            source_path = st.text_input(
                "Data Source (CSV path)",
                value="",
                help="Path to the CSV data file",
            )

        problem_type = st.selectbox(
            "Problem Type",
            options=[
                "auto",
                "facility_location",
                "assignment",
                "transportation",
                "knapsack",
                "network_flow",
                "scheduling",
                "inventory",
            ],
            help="Select a problem type or let OptiMind auto-detect",
        )

        # Show sample data hint
        with st.expander("Need sample data?"):
            st.code("tests/fixtures/facility_location.csv")
            st.write("This file contains a demo facility location problem.")

        pt = problem_type if problem_type != "auto" else None
        optimize_btn = st.button(
            "Run Optimization", type="primary", disabled=not source_path
        )

    # Main content area
    if optimize_btn and source_path:
        with st.spinner("Running optimization pipeline..."):
            result = call_optimize_api(source_path, pt)

        if result.get("status") == "error":
            st.error("Optimization failed.")
            for err in result.get("errors", []):
                st.write(f"- {err}")
            return

        st.success("Optimization completed!")

        # Summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Status", result.get("status", "unknown").capitalize())
        with col2:
            pt_display = result.get("problem_type", "N/A")
            st.metric("Problem Type", pt_display.replace("_", " ").title())
        with col3:
            report = result.get("analysis_report", {}) or {}
            obj_val = report.get("objective_value")
            st.metric(
                "Objective Value",
                f"{obj_val:.2f}" if obj_val is not None else "N/A",
            )

        st.divider()
        render_execution_graph(result.get("execution_graph", []))

        st.divider()
        report = result.get("analysis_report", {}) or {}
        if report.get("executive_summary"):
            st.subheader("Executive Summary")
            st.write(report["executive_summary"])

        render_variable_summaries(report)
        render_constraint_statuses(report)
        render_sensitivity(report)
        render_scenarios(report)
        render_risks(report)
        render_recommendations(report)

        if result.get("errors"):
            st.subheader("Warnings")
            for err in result["errors"]:
                st.warning(err)
    else:
        st.info("Configure your optimization in the sidebar and click 'Run Optimization'.")


if __name__ == "__main__":
    main()
