"""
Simulators for system metrics that are not yet hooked up to real data sources.

These provide realistic-looking, time-varying signals for:
  • CPU utilisation
  • Memory utilisation
  • Electricity cost (time-of-use pricing)
  • Carbon intensity (grid mix)

All simulators are stateless pure functions — they take the current datetime
and optional randomisation parameters, making them fully deterministic in
tests when you pin the timestamp and seed.
"""

from __future__ import annotations

import math
import random
from datetime import datetime


def simulate_cpu_percent(dt: datetime | None = None, *, jitter: float = 8.0) -> float:
    """
    Simulate CPU utilisation with a day-cycle hump peaking mid-afternoon.

    Parameters
    ----------
    dt : datetime, optional
        Timestamp for the simulation; defaults to now().
    jitter : float
        Max random noise (±).
    """
    dt = dt or datetime.now()
    hour = dt.hour + dt.minute / 60.0
    # Gaussian hump centred at 14:00 with σ ≈ 3h
    base = 30 + 50 * math.exp(-((hour - 14) ** 2) / 18)
    noise = (random.random() - 0.5) * 2 * jitter
    return round(max(2.0, min(99.0, base + noise)), 1)


def simulate_memory_percent(dt: datetime | None = None, *, jitter: float = 6.0) -> float:
    """
    Simulate memory utilisation — loosely correlated with CPU, but stickier.
    """
    dt = dt or datetime.now()
    hour = dt.hour + dt.minute / 60.0
    base = 40 + 35 * math.exp(-((hour - 15) ** 2) / 22)
    noise = (random.random() - 0.5) * 2 * jitter
    return round(max(5.0, min(98.0, base + noise)), 1)


def simulate_electricity_cost(dt: datetime | None = None) -> float:
    """
    Simulate time-of-use electricity pricing for Cairo (EGP→USD simplified).

    Off-peak: ~$0.08/kWh
    Shoulder: ~$0.16/kWh
    Peak (18–22): ~$0.34/kWh
    """
    dt = dt or datetime.now()
    hour = dt.hour
    if 18 <= hour <= 22:
        base = 0.30 + 0.08 * math.sin(math.pi * (hour - 18) / 4)
    elif 6 <= hour <= 17:
        base = 0.12 + 0.06 * math.sin(math.pi * (hour - 6) / 11)
    else:
        base = 0.08
    noise = (random.random() - 0.5) * 0.04
    return round(max(0.04, base + noise), 3)


def simulate_carbon_intensity(dt: datetime | None = None) -> float:
    """
    Simulate carbon intensity of the electricity grid (gCO₂/kWh).

    Solar hours (8–16): lower intensity ~180g
    Peak fossil hours (18–22): higher intensity ~420g
    Night: moderate ~280g
    """
    dt = dt or datetime.now()
    hour = dt.hour
    if 8 <= hour <= 16:
        # Solar pushes intensity down
        base = 180 - 40 * math.cos(math.pi * (hour - 12) / 4)
    elif 18 <= hour <= 22:
        # Gas peakers ramp up
        base = 380 + 60 * math.sin(math.pi * (hour - 18) / 4)
    else:
        base = 260 + 30 * math.sin(math.pi * hour / 6)
    noise = (random.random() - 0.5) * 30
    return round(max(80.0, base + noise), 0)


def get_all_simulated_metrics(dt: datetime | None = None) -> dict:
    """
    Convenience function returning all simulated metrics as a dict.

    Returns
    -------
    dict with keys: cpu_percent, memory_percent, electricity_cost, carbon_intensity
    """
    dt = dt or datetime.now()
    return {
        "cpu_percent": simulate_cpu_percent(dt),
        "memory_percent": simulate_memory_percent(dt),
        "electricity_cost": simulate_electricity_cost(dt),
        "carbon_intensity": simulate_carbon_intensity(dt),
    }
