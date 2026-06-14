"""Redirect stdout/stderr to a file in addition to the console."""

import sys
import os


class _Tee:
    def __init__(self, original, file_handle):
        self.original = original
        self.file = file_handle

    def write(self, data):
        self.original.write(data)
        self.file.write(data)
        self.file.flush()

    def flush(self):
        self.original.flush()
        self.file.flush()


def setup_logging(suffix="console"):
    path = os.path.join(os.getcwd(), f'{suffix}_output.log')
    log_file = open(path, 'w', encoding='utf-8')
    sys.stdout = _Tee(sys.stdout, log_file)
    sys.stderr = _Tee(sys.stderr, log_file)
    print(f"[Logging] Output also written to {path}")
