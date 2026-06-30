from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-bip324-blog")

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "bip324-traffic-analysis" / "results"
OUT = ROOT / "personal_blog" / "static" / "images" / "bip324-traffic-analysis"

EVENT_ORDER = [
    "BIP324 handshake",
    "Block arrival",
    "Compact block arrival",
    "Block propagation wave",
    "Large transaction",
    "INV announcement",
    "Request-like burst",
    "TX-like burst",
    "Transaction relay exchange",
]

EVENT_GROUPS = {
    "handshake": ["BIP324 handshake"],
    "blocks": ["Block arrival", "Compact block arrival", "Block propagation wave"],
    "transactions": [
        "Large transaction",
        "INV announcement",
        "Request-like burst",
        "TX-like burst",
        "Transaction relay exchange",
    ],
}

GROUP_TITLES = {
    "handshake": "Handshake",
    "blocks": "Blocks",
    "transactions": "Transactions",
}

EVENT_TITLES = {
    "BIP324 handshake": "Handshake BIP324",
    "Block arrival": "Block arrival",
    "Compact block arrival": "Compact block arrival",
    "Block propagation wave": "Block propagation wave",
    "Large transaction": "Large transaction",
    "INV announcement": "INV announcement",
    "Request-like burst": "Request-like burst",
    "TX-like burst": "TX-like burst",
    "Transaction relay exchange": "Transaction relay exchange",
}

EVENT_SLUGS = {
    "BIP324 handshake": "handshake",
    "Block arrival": "block-arrival",
    "Compact block arrival": "compact-block-arrival",
    "Block propagation wave": "block-propagation-wave",
    "Large transaction": "large-transaction",
    "INV announcement": "inv-announcement",
    "Request-like burst": "request-like-burst",
    "TX-like burst": "tx-like-burst",
    "Transaction relay exchange": "transaction-relay-exchange",
}

MODE_ORDER = ["all flows", "bitcoin port", "BIP324 handshake filter"]

COLORS = {
    "TP": "#166534",
    "FP": "#b91c1c",
    "FN": "#d97706",
    "TN": "#475569",
}

CELL_LABELS = {
    "TP": "TP",
    "FP": "FP",
    "FN": "FN",
    "TN": "TN",
}


def read_validation() -> pd.DataFrame:
    frame = pd.read_csv(RESULTS / "notebook_detection_scope_comparison.csv")
    frame = frame[frame["event"].isin(EVENT_ORDER)].copy()
    frame["event"] = pd.Categorical(frame["event"], EVENT_ORDER, ordered=True)
    frame["mode"] = pd.Categorical(frame["mode"], MODE_ORDER, ordered=True)
    return frame.sort_values(["event", "mode"])


def measured_total(row: pd.Series) -> int:
    return int(row.true_positive + row.false_positive + row.false_negative)


def pct(value: int, total: int) -> float:
    return 100.0 * value / total if total else 0.0


def save_warnet_outcome_percentages(frame: pd.DataFrame) -> None:
    for slug, events in EVENT_GROUPS.items():
        save_warnet_outcome_group(frame, slug, events)


def save_warnet_outcome_group(frame: pd.DataFrame, slug: str, events: list[str]) -> None:
    scoped = frame[(frame["mode"] == "BIP324 handshake filter") & (frame["event"].isin(events))].copy()
    scoped = scoped.sort_values("event", ascending=False)

    height = max(3.8, 1.15 * len(scoped) + 2.0)
    fig, ax = plt.subplots(figsize=(13, height))
    y_positions = range(len(scoped))
    left = [0.0] * len(scoped)
    labels = [
        ("TP", "true_positive"),
        ("FP", "false_positive"),
        ("FN", "false_negative"),
    ]

    for label, column in labels:
        values = []
        for _, row in scoped.iterrows():
            total = measured_total(row)
            values.append(pct(int(row[column]), total))
        ax.barh(y_positions, values, left=left, color=COLORS[label], label=label)
        left = [current + value for current, value in zip(left, values)]

    ax.set_yticks(list(y_positions), scoped["event"])
    ax.set_xlim(0, 100)
    ax.set_xlabel("Measured outcome share (%)")
    ax.set_title(f"Warnet outcomes: {GROUP_TITLES[slug]} (BIP324-handshake scope)", fontsize=18, pad=16)
    ax.grid(axis="x", color="#e2e8f0", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", labelsize=13)
    ax.xaxis.label.set_size(13)
    ax.legend(ncols=3, loc="lower center", bbox_to_anchor=(0.5, -0.24), frameon=False, fontsize=13)

    for y, (_, row) in zip(y_positions, scoped.iterrows()):
        total = measured_total(row)
        text = (
            f"n={total}  "
            f"TP={int(row.true_positive)} ({pct(int(row.true_positive), total):.1f}%)  "
            f"FP={int(row.false_positive)} ({pct(int(row.false_positive), total):.1f}%)  "
            f"FN={int(row.false_negative)} ({pct(int(row.false_negative), total):.1f}%)"
        )
        ax.text(101.0, y, text, va="center", fontsize=12, color="#334155")

    ax.text(
        0,
        -1.05,
        "TN is not plotted because this evaluator does not enumerate negative windows or negative flows.",
        fontsize=11,
        color="#475569",
    )
    fig.subplots_adjust(left=0.25, right=0.66, bottom=0.24, top=0.86)
    path = OUT / f"warnet-outcomes-{slug}.svg"
    fig.savefig(path, format="svg")
    plt.close(fig)
    clean_svg(path)


def save_warnet_confusion_matrices(frame: pd.DataFrame) -> None:
    scoped = frame[frame["mode"] == "BIP324 handshake filter"].copy()
    scoped = scoped.sort_values("event")
    for _, row in scoped.iterrows():
        save_warnet_confusion_event(row)


def save_warnet_confusion_event(row: pd.Series) -> None:
    fig, ax = plt.subplots(figsize=(7.4, 6.4))
    vv = int(row.true_positive)
    vf = int(row.false_positive)
    fv = int(row.false_negative)
    total = vv + vf + fv
    values = [[vv, fv], [vf, 0]]
    labels = [["TP", "FN"], ["FP", "TN"]]
    percentages = [[pct(vv, total), pct(fv, total)], [pct(vf, total), 0.0]]

    ax.imshow(percentages, cmap="Blues", vmin=0, vmax=100)
    ax.set_title(EVENT_TITLES.get(str(row.event), str(row.event)), fontsize=17, pad=18, wrap=True)
    ax.set_xticks([0, 1], ["Predicted: True", "Predicted: False"])
    ax.set_yticks([0, 1], ["Actual: True", "Actual: False"])
    ax.tick_params(length=0, labelsize=13, pad=10)

    for y in [0, 1]:
        for x in [0, 1]:
            label = labels[y][x]
            value = values[y][x]
            percentage = percentages[y][x]
            text_color = "#ffffff" if percentage >= 45.0 else "#0f172a"
            cell_text = f"{CELL_LABELS[label]}\n{value}\n{percentage:.1f}%"
            ax.text(
                x,
                y,
                cell_text,
                ha="center",
                va="center",
                fontsize=15,
                color=text_color,
                fontweight="700",
                linespacing=1.25,
            )

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color("#334155")
        spine.set_linewidth(1.0)

    fig.suptitle("Warnet confusion matrix", fontsize=22, y=0.985)
    fig.supxlabel("Predicted category", fontsize=15, y=0.045)
    fig.supylabel("Actual category", fontsize=15, x=0.02)
    fig.subplots_adjust(
        left=0.14,
        right=0.97,
        bottom=0.18,
        top=0.80,
    )
    path = OUT / f"warnet-confusion-{EVENT_SLUGS[str(row.event)]}.svg"
    fig.savefig(path, format="svg")
    plt.close(fig)
    clean_svg(path)


def save_warnet_flow_scope() -> None:
    scope = pd.read_csv(RESULTS / "notebook_dataset_scope.csv")
    scope["label"] = scope["name"].map(
        {
            "data_to_analysis-all-flows": "All flows",
            "data_to_analysis-bitcoin-port": "Bitcoin port",
            "data_to_analysis-bip324-handshake": "BIP324 handshake filter",
        }
    )
    scope["inspected_flows"] = scope.apply(
        lambda row: row["candidate_flow_count"]
        if row["name"] == "data_to_analysis-bip324-handshake"
        else row["flow_count"],
        axis=1,
    )

    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    labels = list(scope["label"])
    values = list(scope["inspected_flows"])
    colors = ["#1d4ed8", "#0f766e", "#7c3aed"]
    starts = [1] * len(values)
    widths = [max(value - 1, 0) for value in values]
    bars = ax.barh(labels, widths, left=starts, color=colors, height=0.58)
    ax.set_xscale("log")
    ax.set_xlabel("Flows inspected by event rules (log scale)")
    ax.set_title("Warnet flow scope reduction", fontsize=17, pad=14)
    ax.grid(axis="x", color="#e2e8f0", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", labelsize=11)
    ax.tick_params(axis="y", labelsize=12)
    ax.bar_label(bars, labels=[f"{int(value)} flows" for value in values], padding=6, fontsize=12)
    ax.set_xlim(1, max(values) * 1.8)

    fig.tight_layout()
    path = OUT / "warnet-flow-scope.svg"
    fig.savefig(path, format="svg")
    plt.close(fig)
    clean_svg(path)


def clean_svg(path: Path) -> None:
    lines = path.read_text().splitlines()
    path.write_text("\n".join(line.rstrip() for line in lines) + "\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frame = read_validation()
    save_warnet_confusion_matrices(frame)
    save_warnet_flow_scope()


if __name__ == "__main__":
    main()
