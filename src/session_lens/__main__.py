"""`python -m session_lens`, and the entry point of the packaged binary."""

import multiprocessing

from session_lens.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()  # harmless unless frozen on Windows
    raise SystemExit(main())
