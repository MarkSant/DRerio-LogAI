import logging
import random

import numpy as np
import torch


def set_seed(seed: int):
    """
    Sets the seed for random number generators in Python, NumPy, and PyTorch
    to ensure reproducibility.

    Args:
        seed (int): The seed value.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)  # for multi-GPU
        # The following two lines are often recommended for reproducibility,
        # but they can have a performance impact. For this application,
        # consistency is more important than performance.
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    logging.info(f"Set random seed to {seed} for reproducibility.")
