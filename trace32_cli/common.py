#!/usr/bin/env python3
""" Common functions used by multiple source-files in this library. """

import shutil
import os
import tempfile
import atexit
import sys
import signal


def delete_path(path):
    """ Deletes a file or folder, and all children. No action if the path
    doesn't exist. """

    if os.path.isdir(path):
        shutil.rmtree(path)

    elif os.path.exists(path):
        os.remove(path)


def make_tempdir():
    """ Makes a self-deleting temporary directory. Tries to put the
    tempdir in a subdirectory of $TMPDIR, $TMP, $TEMP, or $XDG_RUNTIME_DIR
    if any of those environment variables are set. Otherwise, Python's default
    location is used for tempfile.TemporaryDirectory(). """
    # pylint: disable=consider-using-with

    for varname in ["TMPDIR", "TMP", "TEMP", "XDG_RUNTIME_DIR"]:
        if varname in os.environ and os.path.isdir(os.environ[varname]):
            tempdir_base = os.environ.get(varname)
            return tempfile.TemporaryDirectory(dir=tempdir_base)

    return tempfile.TemporaryDirectory()


def register_cleanup(function, *args, **kwargs):
    """ Registers a function with atexit and the system exception handler.
    Function will be called once at exit, regardless of whether the exit was
    intentional or not. """

    def cleanup():
        # pylint: disable=missing-docstring
        if not cleanup.called:
            function(*args, **kwargs)
            cleanup.called = True

    cleanup.called = False
    atexit.register(cleanup)
    old_hook = sys.excepthook

    def new_hook(exception_type, value, traceback):
        cleanup()
        return old_hook(exception_type, value, traceback)

    sys.excepthook = new_hook


def register_handler(signum, function, *args, **kwargs):
    """ Registers a function with a signal handler. Calls the original signal
    handler (if possible) after running the user-supplied addition. """

    old_handler = signal.getsignal(signum)

    def handler(signum, frame):
        # pylint: disable=missing-docstring
        result = function(*args, **kwargs)

        if callable(old_handler):
            return old_handler(signum, frame)

        return result

    signal.signal(signum, handler)
