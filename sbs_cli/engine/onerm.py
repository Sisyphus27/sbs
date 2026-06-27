"""Estimated 1RM = mean of Epley, Brzycki, Wathan (top-3 authoritative formulas)."""
import math
from statistics import mean


def epley(weight: float, reps: float) -> float:
    return weight * (1 + reps / 30)


def brzycki(weight: float, reps: float) -> float:
    return weight * 36 / (37 - reps)


def wathan(weight: float, reps: float) -> float:
    return weight * 100 / (48.8 + 53.8 * math.exp(-0.075 * reps))


def estimate_1rm(weight: float, reps: float) -> float:
    """Mean of the three formulas. Most accurate at reps <= 10."""
    return mean((epley(weight, reps), brzycki(weight, reps), wathan(weight, reps)))
