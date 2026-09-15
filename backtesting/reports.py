from __future__ import annotations

from typing import Any


def format_grid_results(results: list[dict[str, Any]], limit: int = 10) -> str:
    lines = ["Optimization Results", ""]
    for rank, item in enumerate(results[:limit], start=1):
        metrics = item["metrics"]
        lines.append(
            f"{rank}. objective={item['objective']:.4f} "
            f"trades={metrics.get('total_trades', 0):.0f} "
            f"pf={metrics.get('profit_factor', 0):.4f} "
            f"avg_r={metrics.get('average_r', 0):.4f} "
            f"dd={metrics.get('max_drawdown', 0):.2f} "
            f"params={item['parameters']}"
        )
    return "\n".join(lines)


def format_comparison_results(results: dict[str, dict[str, float]]) -> str:
    lines = ["Variant Comparison", ""]
    for name, metrics in results.items():
        lines.append(
            f"{name}: trades={metrics.get('total_trades', 0):.0f}, "
            f"pf={metrics.get('profit_factor', 0):.4f}, "
            f"avg_r={metrics.get('average_r', 0):.4f}, "
            f"net={metrics.get('net_profit', 0):.2f}, "
            f"dd={metrics.get('max_drawdown', 0):.2f}"
        )
    return "\n".join(lines)


def format_out_of_sample_result(result: Any) -> str:
    lines = [
        "Out-of-Sample Validation",
        "",
        f"Selected Parameters: {result.selected_parameters}",
        "",
        _metrics_line("Train", result.train_metrics),
        _metrics_line("Validation", result.validation_metrics),
        _metrics_line("Test", result.test_metrics),
        "",
        f"Robustness: {result.robustness.get('status')}",
        f"Objective Decay: {result.robustness.get('objective_decay', 0):.4f}",
    ]
    reasons = result.robustness.get("reasons", [])
    if reasons:
        lines.append("Reasons:")
        lines.extend(f"- {reason}" for reason in reasons)
    return "\n".join(lines)


def format_walk_forward_result(result: dict[str, Any]) -> str:
    summary = result.get("summary", {})
    lines = [
        "Walk-Forward Validation",
        "",
        f"Status: {summary.get('status')}",
        f"Windows: {summary.get('windows', 0)}",
        f"Pass Rate: {summary.get('pass_rate', 0):.4f}" if isinstance(summary.get("pass_rate", 0), float) else f"Pass Rate: {summary.get('pass_rate', 0)}",
        f"Average Objective: {summary.get('average_objective', 0):.4f}" if isinstance(summary.get("average_objective", 0), float) else f"Average Objective: {summary.get('average_objective', 0)}",
        f"Average Validation Trades: {summary.get('average_validation_trades', 0):.2f}" if isinstance(summary.get("average_validation_trades", 0), float) else f"Average Validation Trades: {summary.get('average_validation_trades', 0)}",
        "",
    ]
    for window in result.get("windows", []):
        lines.append(
            f"Window {window['window']}: "
            f"{_metrics_line('validation', window['validation_metrics'])}, "
            f"params={window['selected_parameters']}"
        )
    return "\n".join(lines)


def _metrics_line(label: str, metrics: dict[str, float]) -> str:
    return (
        f"{label}: trades={metrics.get('total_trades', 0):.0f}, "
        f"pf={metrics.get('profit_factor', 0):.4f}, "
        f"avg_r={metrics.get('average_r', 0):.4f}, "
        f"net={metrics.get('net_profit', 0):.2f}, "
        f"dd={metrics.get('max_drawdown', 0):.2f}"
    )
