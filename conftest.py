import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("STATE_DIR", os.path.join(os.path.dirname(__file__), "_state"))
