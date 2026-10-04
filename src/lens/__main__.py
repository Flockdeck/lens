"""`python -m lens`, and the entry point of the packaged binary."""

import multiprocessing

from lens.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()  # harmless unless frozen on Windows
    raise SystemExit(main())
