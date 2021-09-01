""" Module for wrapping Trace32 into an easier-to-automate interface. """

import os

# --------------------------------------------------------------------------- #

__script_dir = os.path.abspath(os.path.dirname(__file__))
__version_file = os.path.join(__script_dir, "VERSION")

if os.path.exists(__version_file):
    __version__ = open(__version_file).read().strip()
else:
    __version__ = "(unspecified)"
