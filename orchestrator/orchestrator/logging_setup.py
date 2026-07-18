import logging
import sys


def setup_logging(level=logging.INFO):
    root = logging.getLogger()
    if root.handlers:
        return  # already configured (e.g. re-imported in a notebook)
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    ))
    root.addHandler(handler)
