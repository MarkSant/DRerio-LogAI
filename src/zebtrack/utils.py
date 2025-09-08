import hashlib
import random

import numpy as np
import structlog
import torch

log = structlog.get_logger()


class IntegrityError(Exception):
    """Custom exception for file integrity errors."""

    pass


def calculate_sha256(filepath: str) -> str:
    """
    Calculates the SHA256 hash of a file.

    Args:
        filepath: The path to the file.

    Returns:
        The hex digest of the hash, or an empty string if the file cannot be read.
    """
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            # Read and update hash in chunks of 4K
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except IOError:
        log.error("file.hash.read_error", filepath=filepath)
        return ""


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
    log.info("reproducibility.seed.set", seed=seed)
