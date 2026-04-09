"""Reasonability checks for query results and actuarial data."""

from typing import Optional


def check_query_result(columns: list[str], rows: list[list], context: str = "") -> list[str]:
    """Run contextual reasonability checks on query results. Returns list of warnings."""
    warnings = []

    if not rows:
        warnings.append("Query returned 0 rows. Verify filters and join conditions are correct.")
        return warnings

    col_lower = [c.lower() for c in columns]

    # Check for unexpected row count changes after joins
    if len(rows) == 1 and any(kw in context.lower() for kw in ["sum", "total", "count"]):
        pass  # Single aggregate row is expected
    elif len(rows) > 50000:
        warnings.append(f"Large result set ({len(rows):,} rows). Possible cartesian join or missing filter.")

    # Check for NULL values in key columns
    for i, col in enumerate(col_lower):
        null_count = sum(1 for row in rows if row[i] is None)
        if null_count > 0 and null_count == len(rows):
            warnings.append(f"Column '{columns[i]}' is entirely NULL. Check join conditions.")
        elif null_count > len(rows) * 0.5 and any(kw in col for kw in ["premium", "loss", "earned", "written", "policy"]):
            warnings.append(f"Column '{columns[i]}' has {null_count}/{len(rows)} NULL values ({null_count/len(rows)*100:.0f}%). Verify join logic.")

    # Actuarial-specific checks
    _check_financial_columns(columns, col_lower, rows, warnings)
    _check_ratios(columns, col_lower, rows, warnings)
    _check_duplicates(columns, col_lower, rows, warnings)

    return warnings


def _check_financial_columns(columns, col_lower, rows, warnings):
    """Check premium and loss columns for suspicious values."""
    for i, col in enumerate(col_lower):
        values = [row[i] for row in rows if row[i] is not None]
        if not values:
            continue

        try:
            numeric_vals = [float(v) for v in values]
        except (ValueError, TypeError):
            continue

        # Negative premium check
        if any(kw in col for kw in ["premium", "earned_prem", "written_prem", "ep", "wp"]):
            neg_count = sum(1 for v in numeric_vals if v < 0)
            if neg_count > 0:
                warnings.append(
                    f"Column '{columns[i]}' has {neg_count} negative values. "
                    f"Negative premium may indicate endorsements/cancellations — verify this is expected."
                )
            total = sum(numeric_vals)
            if total <= 0:
                warnings.append(
                    f"Column '{columns[i]}' sums to {total:,.2f} (non-positive). Check filters — may be excluding most records.")

        # Very large single loss
        if any(kw in col for kw in ["loss", "incurred", "paid", "claim"]):
            max_val = max(numeric_vals)
            if len(numeric_vals) > 1:
                mean_val = sum(numeric_vals) / len(numeric_vals)
                if max_val > mean_val * 100 and mean_val > 0:
                    warnings.append(
                        f"Column '{columns[i]}' has an outlier value of {max_val:,.2f} "
                        f"(mean: {mean_val:,.2f}). Possible catastrophe loss or data entry error.")


def _check_ratios(columns, col_lower, rows, warnings):
    """Check computed ratios for reasonability."""
    for i, col in enumerate(col_lower):
        if "ratio" not in col and "lr" not in col.split("_"):
            continue
        values = [row[i] for row in rows if row[i] is not None]
        if not values:
            continue
        try:
            numeric_vals = [float(v) for v in values]
        except (ValueError, TypeError):
            continue

        for v in numeric_vals:
            if v > 5.0:  # 500% loss ratio
                warnings.append(
                    f"Column '{columns[i]}' contains value {v:.2%} — extremely high. "
                    f"Could indicate catastrophe losses, small denominator, or join/aggregation error.")
                break
            if v < 0:
                warnings.append(
                    f"Column '{columns[i]}' contains negative value {v:.2%}. "
                    f"Check for sign errors in numerator or denominator.")
                break


def _check_duplicates(columns, col_lower, rows, warnings):
    """Check for potential duplicate rows from bad joins."""
    policy_cols = [i for i, c in enumerate(col_lower)
                   if any(kw in c for kw in ["policy_number", "policy_id", "pol_num", "polnum"])]

    for pi in policy_cols:
        values = [row[pi] for row in rows if row[pi] is not None]
        unique = set(values)
        if len(values) > len(unique) * 2 and len(unique) > 10:
            warnings.append(
                f"Column '{columns[pi]}' has {len(values)} rows but only {len(unique)} unique values. "
                f"Possible fan-out from join — check for many-to-many relationship.")


def format_warnings(warnings: list[str]) -> Optional[str]:
    if not warnings:
        return None
    lines = ["**Reasonability Checks:**"]
    for i, w in enumerate(warnings, 1):
        lines.append(f"  {i}. {w}")
    return "\n".join(lines)
