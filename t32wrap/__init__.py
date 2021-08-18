""" Module for wrapping Trace32 into an easier-to-automate interface. """

from .t32run import Trace32Subprocess, Podbus

from .t32api import Trace32Interface
from .t32api import ApiError, CallFailure, CommandFailure, ScriptFailure
from .t32api import EvalError

from .t32wrap import main

# pylint: disable=undefined-variable
del t32run
del t32wrap
del t32api
del t32api_errors
del common
