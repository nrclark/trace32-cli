""" Module for wrapping Trace32 into an easier-to-automate interface. """
from .t32run import Trace32Subprocess, Podbus, usb_reset
from .t32run import find_trace32_bin, find_trace32_dir

from .t32iface import Trace32Interface, ScriptFailure
from .t32api import ApiError, CallFailure, CommandFailure
from .t32api import EvalError

from .trace32_cli import main
from .version import __version__

# --------------------------------------------------------------------------- #

# pylint: disable=undefined-variable
del t32run
del trace32_cli
del t32api
del t32api_errors
del common
