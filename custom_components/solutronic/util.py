"""Validation helpers shared by telemetry, storage and setup."""

import math

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL


def as_float(value, default=None):
    """Return a finite number, excluding booleans and invalid device values."""
    if isinstance(value, bool):
        return default
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def as_energy(value):
    """Return a nonnegative energy reading, or None when invalid."""
    result = as_float(value)
    return result if result is not None and result >= 0 else None


def scan_interval(options):
    """Preserve valid polling intervals and recover from malformed options."""
    result = as_float(options.get(CONF_SCAN_INTERVAL), DEFAULT_SCAN_INTERVAL)
    return result if result > 0 else DEFAULT_SCAN_INTERVAL
