import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, "vendor", "tgws"))
sys.path.insert(0, _here)

from app.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
