# plot_demo.py
"""Plot recent hourly traffic and the full selected history of daily traffic."""

from datetime import timedelta, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator
import pandas as pd

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
MAX_PLOT_DAYS = 14  # Hourly detail only. The daily overview always uses the full CSV.
JST = timezone(timedelta(hours=9), name="JST")
LABELS = {"wp": "WordPress (wp)", "doktor": "Doktor"}
TRAFFIC = [("requests", "All requests", "#183A53", "-"),
           ("monitor_requests", "Identified monitoring", "#A46A18", "--"),
           ("other_requests", "Other requests", "#20857C", "-")]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "text.color": "#293640",
                     "axes.labelcolor": "#293640", "pdf.fonttype": 42, "ps.fonttype": 42})


def _window(frame, days=None):
    if frame.empty:
        raise ValueError("The input table is empty")
    first, last = frame["day"].min(), frame["day"].max()
    shortened = False
    if days is not None:
        if days < 1:
            raise ValueError("MAX_PLOT_DAYS must be positive or None")
        cutoff = last - pd.Timedelta(days=days - 1)
        shortened = first < cutoff
        frame = frame.loc[frame["day"] >= cutoff].copy()
    caption = f"{frame['day'].min():%d %b %Y} to {last:%d %b %Y}, JST (UTC+09:00)."
    if shortened:
        caption += f"\nLatest {days} days shown; CSVs retain the full period."
    present = set(frame["service"])
    services = [name for name in LABELS if name in present] + sorted(present.difference(LABELS))
    return frame, caption, services


def _axis(ax, label):
    ax.set_title(LABELS.get(label, label), loc="left", fontsize=10, fontweight="semibold", pad=6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#C4CDD2")
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#E1E6E9", linewidth=0.7)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))


def _heading(fig, title, caption):
    fig.suptitle(title, x=0.10, y=0.97, ha="left", fontsize=14)
    fig.text(0.10, 0.97 - 24 / (72 * fig.get_figheight()), caption, va="top", fontsize=9.5, color="#52636E")


def _save(fig, output_dir, name):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = tuple(output_dir / f"{name}.{suffix}" for suffix in ("png", "pdf"))
    for path in paths:
        fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return paths


def plot_hourly(hourly: pd.DataFrame, output_dir: Path = OUTPUT_DIR):
    frame = hourly.copy()
    frame["time"] = pd.to_datetime(frame["time_utc"], utc=True)
    frame["day"] = frame["time"].dt.tz_convert(JST).dt.tz_localize(None).dt.normalize()
    frame, caption, services = _window(frame, MAX_PLOT_DAYS)
    fig, grid = plt.subplots(len(services), 1, figsize=(8, 2.1 * len(services) + 1), sharex=True, squeeze=False)
    axes = grid[:, 0]
    extra = 0.06 if "\n" in caption else 0
    fig.subplots_adjust(left=0.10, right=0.98, bottom=0.17, top=0.74 - extra, hspace=0.32)
    _heading(fig, "Hourly web requests", caption)
    for ax, service in zip(axes, services):
        data = frame.loc[frame["service"] == service].sort_values("time")
        _axis(ax, service)
        for column, label, color, linestyle in TRAFFIC:
            ax.plot(data["time"].dt.tz_convert(JST), data[column], label=label, color=color,
                    linestyle=linestyle, linewidth=1.9 if column == "requests" else 1.5)
        maximum = data["requests"].max()
        ax.set_ylim(0, max(1, maximum * 1.12) if pd.notna(maximum) else 1)
        if pd.isna(maximum):
            ax.set_yticks([])
            ax.text(0.5, 0.5, "Hourly counts unknown", transform=ax.transAxes, ha="center")
        ax.set_ylabel("Requests per hour")
        ax.margins(x=0.01)
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper left", bbox_to_anchor=(0.09, 0.86 - extra),
               ncol=3, frameon=False, fontsize=9.5, handlelength=2, columnspacing=1.3)
    axes[-1].xaxis.set_major_locator(mdates.AutoDateLocator(tz=JST, minticks=5, maxticks=9))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M", tz=JST))
    axes[-1].set_xlabel("Hour beginning (JST, UTC+09:00)", labelpad=7)
    return _save(fig, output_dir, "01_hourly_traffic")


def plot_daily(daily: pd.DataFrame, output_dir: Path = OUTPUT_DIR):
    frame = daily.assign(day=pd.to_datetime(daily["date_local"]))
    frame, caption, services = _window(frame)
    fig, grid = plt.subplots(len(services), 1, figsize=(8, 1.7 * len(services) + 1), sharex=True, squeeze=False)
    axes = grid[:, 0]
    fig.subplots_adjust(left=0.10, right=0.98, bottom=0.16, top=0.73, hspace=0.35)
    _heading(fig, "Daily web requests across the full period", caption)
    for ax, service in zip(axes, services):
        data = frame.loc[frame["service"] == service].sort_values("day")
        _axis(ax, service)
        for column, label, color, linestyle in TRAFFIC:
            ax.plot(data["day"], data[column], label=label, color=color, linestyle=linestyle,
                    linewidth=1.5, marker="o" if len(data) <= 14 else None, markersize=3)
        maximum = data["requests"].max()
        ax.set_ylim(0, max(1, maximum * 1.12) if pd.notna(maximum) else 1)
        if pd.isna(maximum):
            ax.set_yticks([])
            ax.text(0.5, 0.5, "Daily totals unavailable", transform=ax.transAxes, ha="center")
        ax.set_ylabel("Requests per day")
        ax.margins(x=0.01)
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper left", bbox_to_anchor=(0.09, 0.85),
               ncol=3, frameon=False, fontsize=9.5, handlelength=2, columnspacing=1.3)
    span = (frame["day"].max() - frame["day"].min()).days
    locator = mdates.DayLocator(interval=max(1, (span + 6) // 7)) if span <= 31 else mdates.AutoDateLocator(minticks=4, maxticks=7)
    axes[-1].xaxis.set_major_locator(locator)
    axes[-1].xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    axes[-1].set_xlabel("Local date (JST)", labelpad=7)
    return _save(fig, output_dir, "02_daily_traffic")


if __name__ == "__main__":
    paths = plot_hourly(pd.read_csv(OUTPUT_DIR / "hourly.csv")) + plot_daily(pd.read_csv(OUTPUT_DIR / "daily.csv"))
    for path in paths:
        print(f"Saved {path.resolve()}")
