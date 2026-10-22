"""Plotly charts for the dashboard. Colors: validated categorical slots, one axis per chart."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from buzzscope.models import Report

VOLUME = "#2a78d6"  # slot 1
KIND_COLORS = {"event": "#eb6834", "unrelated": "#1baf7a", "noise": "#8a8984"}  # slot 2, slot 3, neutral
KIND_NAMES = {"event": "事件", "unrelated": "撞名／無關", "noise": "正常波動"}
INK = "#52514e"
GRID = "rgba(82,81,78,0.15)"


def _layout(fig: go.Figure, title: str, height: int = 320) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0, font=dict(size=15, color="#0b0b0b")),
        height=height,
        margin=dict(l=8, r=8, t=48, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=INK, size=12),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, rangemode="tozero")
    return fig


def volume_chart(series: pd.DataFrame, report: Report) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=series.index,
            y=series["count"],
            name="每日文章數",
            mode="lines",
            line=dict(color=VOLUME, width=2),
            hovertemplate="%{y} 篇<extra></extra>",
        )
    )
    by_kind: dict[str, list] = {}
    for f in report.findings:
        if f.spike_date in series.index:
            by_kind.setdefault(f.kind, []).append(f)
    for kind, items in by_kind.items():
        fig.add_trace(
            go.Scatter(
                x=[f.spike_date for f in items],
                y=[int(series.loc[f.spike_date, "count"]) for f in items],
                name=KIND_NAMES[kind],
                mode="markers",
                marker=dict(color=KIND_COLORS[kind], size=12, line=dict(color="#ffffff", width=2)),
                customdata=[f.cause[:40] for f in items],
                hovertemplate="%{customdata}<extra>" + KIND_NAMES[kind] + "</extra>",
            )
        )
    return _layout(fig, "聲量趨勢與異常點")


def sentiment_chart(series: pd.DataFrame) -> go.Figure:
    # Post-weighted 7-day mean: days with no posts don't break the line, and a day with
    # 1 post doesn't count as much as a day with 60.
    weighted = (series["sentiment"].fillna(0) * series["count"]).rolling(7, min_periods=1).sum()
    total = series["count"].rolling(7, min_periods=1).sum()
    smooth = (weighted / total.where(total >= 3)).round(3)
    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color=GRID, width=1))
    fig.add_trace(
        go.Scatter(
            x=series.index,
            y=smooth,
            name="情緒（7 日加權平均）",
            mode="lines",
            connectgaps=True,
            line=dict(color=VOLUME, width=2),
            hovertemplate="%{y:+.2f}<extra></extra>",
        )
    )
    fig = _layout(fig, "情緒走勢（-1 負面 ～ +1 正面，字典法）", height=260)
    fig.update_yaxes(range=[-1, 1], rangemode="normal")
    fig.update_layout(showlegend=False)
    return fig
