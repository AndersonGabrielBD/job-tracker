import os
import sys

_LAYER_PYTHON_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "lambda", "common_layer", "python")
)
if _LAYER_PYTHON_PATH not in sys.path:
    sys.path.insert(0, _LAYER_PYTHON_PATH)
