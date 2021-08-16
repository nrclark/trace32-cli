#!/usr/bin/env python3

import argparse
import sys

from  .t32api import Trace32API
from  .t32run import Trace32Subprocess

def create_parser():
    """ Generates and returns an argparse instance for the CLI tool. """

    parser = argparse.ArgumentParser()
    parser.description = """ Wrap Trace32 with a CLI-friendly porcelain that
    uses the C API as a backend to an internally-controlled Trace32 instance.
    Provide the ability to read/write single addresses, to read/write files
    to/from memory, to run single commands or PRACTICE scripts, and to run a
    REPL that can interact with Trace32. """

    parser.add_argument("infile", metavar="INFILE", nargs="?",
                        default=sys.stdin, help="""PRACTICE script to run. If
                        not provided, the script will be read from stdin. """)

    parser.add_argument('-p', "--prefix", dest="prefix", help="""PRACTICE
                        script to run right after launching trace32, before
                        doing anything else. This script can be used to
                        configure JTAG/debug settings. """)

    parser.add_argument('-c', "--command", dest="command",
                        help="""Single-statement command to run. Prints the
                        result and exits.""")

    return parser


def run_parser(parser):
    """ Run the argparse instance, and do any postprocessing that's required
    on the arguments. """

    args = parser.parse_args()
    return args


def main():
    t32_runner = Trace32Subprocess("t32marm")
    t32_runner.run()

    parser = create_parser()
    args = run_parser(parser)

    def connect(self, node="localhost", port=20000, packlen=None):


    api = Trace32API()

    print(args)

if __name__ == "__main__":
    main()
