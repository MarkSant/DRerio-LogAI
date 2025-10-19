import gc

import structlog

log = structlog.get_logger()


def cleanup_after_video_processing():
    """Force garbage collection after processing each video."""
    collected = gc.collect()
    log.debug("memory.gc.collected", objects=collected)
