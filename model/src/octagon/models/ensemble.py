"""Convex blend of logistic regression and calibrated GBM.

Weight is chosen on train-era OOS predictions only.
"""

import numpy as np

from octagon.eval.metrics import log_loss


def blend(p_lr: np.ndarray, p_gbm: np.ndarray, weight_lr: float) -> np.ndarray:
    return weight_lr * p_lr + (1.0 - weight_lr) * p_gbm


def tune_weight(y: np.ndarray, p_lr: np.ndarray, p_gbm: np.ndarray) -> float:
    """Pick the logistic weight on train-era out-of-sample predictions."""
    grid = np.linspace(0.0, 1.0, 21)
    losses = [log_loss(y, blend(p_lr, p_gbm, w)) for w in grid]
    return float(grid[int(np.argmin(losses))])
