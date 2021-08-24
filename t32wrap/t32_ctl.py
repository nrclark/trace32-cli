#!/usr/bin/env python3

import argparse
import sys
import re

from .t32run import usb_reset, Trace32Subprocess
from .t32run import find_trace32_dir, find_trace32_bin, Podbus

from .t32api import Trace32Interface

# ---------------------------------------------------------------------------- #

def read(args):
    pass

def write(args):
    pass

def run(args):
    print(args)
    pass

# ---------------------------------------------------------------------------- #


def constant(input_string):
    """ Evaluate a string as a numerical constant and return it. Try to convert
    the string from a number of different formats. """

    value = input_string.strip().lower()

    if re.match("^[0-9]+[.]$", value):
        return int(value[:-1])

    if re.match("^[0-9]*[.][0-9]+$", value):
        return float(value)

    if re.match("^0?[b][10]+$", value):
        return int(value, 2)

    if re.match("^0?[x][a-f0-9]+$", value):
        return int(value, 16)

    value = re.sub("b$", "", value)

    if not re.match("^[0-9]+[kmgtp]*$", value):
        msg = f"[{input_string}] can't be evaluated as a numeric literal"
        raise argparse.ArgumentTypeError(msg)

    mult = 1
    multipliers = {
        'k': 1024,
        'm': 1024*1024,
        'g': 1024*1024*1024,
        't': 1024*1024*1024*1024,
        'p': 1024*1024*1024*1024*1024
    }

    while True:
        for suffix in multipliers:
            if value.endswith(suffix):
                mult = mult * multipliers[suffix]
                value = value[:-1]
                break
        else:
            break

    return int(value) * mult


def trace32_binary(input_string):
    """ Confirms that 'input_string' can be traced to a valid Trace32
    binary of the requested name. """

    value = input_string.strip()

    try:
        install_dir = find_trace32_dir(value)
        find_trace32_bin(value, install_dir)
        return value
    except Exception as err:
        sys.stderr.write(f"{str(err)}\n")
        raise argparse.ArgumentError(str(err))


def modify_add_argument(parent):
    """ Modifies the add_argument() method of an ArgumentParser argument-parser
    object to work around a bug in the interaction between argparse.SUPPRESS
    and the "%(default)s" operator. """

    parent._add_argument = parent.add_argument

    def make_arg(*args, **kwargs):
        result = parent._add_argument(*args, **kwargs)
        if result.default == argparse.SUPPRESS:
            if result.help:
                result.help = result.help.replace("%(default)s", str(None))

    parent.add_argument = make_arg


def common_options(toplevel=False):
    """ These options are shared by all commands in the utility. They're used
    to set up the Trace32 instance, or to tear it down/launch a target after
    programming. """

    argument_default = None if toplevel else argparse.SUPPRESS

    parser = argparse.ArgumentParser(add_help=False,
                                     argument_default = argument_default)

    group = parser.add_argument_group(title="common options")
    modify_add_argument(group)

    group.add_argument("-v", "--verbose", dest="verbosity", action="count",
                       default=0, help="""Be verbose. Specify multiple times
                       for more verbosity.""")

    group.add_argument("-H", "--header", metavar="FILE", help="""PRACTICE
                        script to run before taking any other action (default:
                        %(default)s).""", type=argparse.FileType('r'))

    group.add_argument("-F", "--footer", metavar="FILE", help="""PRACTICE
                        script to run after finishing all other actions
                        (default: None).""", type=argparse.FileType('r'))

    group.add_argument("-u", "--usb-reset", action="store_true", help="""
                        Reset the Trace32 USB debug adapter before launching
                        Trace32.""")

    group.add_argument("-p", "--protocol", metavar="PROTOCOL", choices=["usb",
                       "sim"], default="usb", help="""Protocol to use for
                       communicating with the target. Known protocols are:
                       [usb, sim] (default: usb).""")

    group.add_argument("-t", "--t32bin", metavar="TRACE32", default="t32marm",
                       type=trace32_binary, help="""Trace32 binary to use.
                       Controls the target architecture (default:
                       %(default)s).""")

    return parser


def create_parser():
    """ Generates and returns an argparse instance for the CLI tool. """
    parent_common = [common_options(True)]
    child_common = [common_options(False)]

    top_parser = argparse.ArgumentParser(parents=parent_common)
    top_parser.description = """Command-line tool that uses Lauterbach Trace32
    to control a target device."""

    subparsers = top_parser.add_subparsers(title='Available commands',
                                           dest="subcommand",
                                           metavar="COMMAND",
                                           help="DESCRIPTION")

    # ----------------------------------------------------------------------- #

    parser = subparsers.add_parser("read", help="""Read raw data from target
                                   memory""", parents=child_common,
                                   argument_default=None)

    parser.format_help()

    parser.add_argument("ADDRESS", help="""Target address to read from the
                        target. Hexadecimal addresses should start with a "0x"
                        prefix.""", type=constant)

    parser.add_argument("OUTFILE", nargs="?", help="""Output file to write
                        (default: stdout).""")

    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument("-r", "--reference", metavar="FILE", required=False,
                       help="""Read a number of bytes equal to the size of
                       FILE. Can be used for readbacks or other similar
                       operations.""", type=argparse.FileType('r'))

    group.add_argument("-c", "--count", help="""Number of bytes to read,
                       starting at ADDRESS and counting upwards (default:
                       %(default)s).""", type=constant)

    # ----------------------------------------------------------------------- #

    parser = subparsers.add_parser("write", help="""Write raw data to target
                                   memory""", parents=child_common)

    parser.description = """ Write a file to the target's memory. Optionally
    check the result of the write operation using one of three modes: full,
    partial, and checksum. In [full] verification mode, the write is fully
    verified. In [partial] verification mode, 1/16 of all writes are verified.
    In [checksum] verification mode, Trace32 uploads a temporary program into
    SPADDRESS and uses it to checksum the target region. """

    parser.add_argument("ADDRESS", help="""Target address to read from the
                        target. Hexadecimal addresses should start with a "0x"
                        prefix.""", type=constant)

    parser.add_argument("INFILE", nargs="?", help="""Input file to write
                        (default: stdin).""", type=argparse.FileType('rb'),
                        default=sys.stdin.buffer)

    parser.add_argument("-c", "--check", required=False, metavar="MODE",
                        default="none", choices=("full", "checksum", "partial",
                        "none"), help="""Checking mode for written data. Known
                        modes are: [%(choices)s]. (default: %(default)s).""")

    parser.add_argument("-s", "--scratchpad", required=False,
                        metavar="SPADDRESS", help="""Address for the 64kB
                        scratchpad region needed on-target for 'checksum'
                        verification mode. Ignored unless -c/--check=checksum
                        is used. (default: %(default)s).""", type=constant)

    # ----------------------------------------------------------------------- #

    parser = subparsers.add_parser('run', help='Run a PRACTICE command',
                                   parents=child_common)

    parser.add_argument("statement", metavar="STATEMENT", help="""Statement to
                        evaluate/run. All positional argumentss are combined
                        into a single %(metavar)s.""", nargs='*')

    parser.description = """Evaluate a Trace32/PRACTICE statement. Return the
    result if it can be parsed with EVAL, or else try to run it as a
    command."""

    # ----------------------------------------------------------------------- #

    parser = subparsers.add_parser("gdb", help="""Run GDB with a Trace32
                                   backend""", parents=child_common)

    parser = subparsers.add_parser("serve", help="""Run Trace32 as a headless
                                   server""", parents=child_common)

    return top_parser


def run_parser(parser):
    """ Run the argparse instance, and do any postprocessing that's required
    on the arguments. """

    args = parser.parse_args()
    return args


# ---------------------------------------------------------------------------- #

def create_commenter(verbosity, prefix="# ", dest=sys.stdout):

    def comment(message: str, level: int=1):
        if verbosity >= level:
            dest.write(prefix + message + "\n")

    return comment

# ---------------------------------------------------------------------------- #


def main():
    parser = create_parser()
    args = run_parser(parser)
    args.log = create_commenter(args.verbosity)

    if args.subcommand is None:
        parser.error(f"COMMAND not specified.")

    if args.subcommand in ['gdb', 'serve']:
        parser.error(f"subcommand [{args.subcommand}] isn't implemented yet.")

    commands = {
        'read': read,
        'write': write,
        'run': run
    }

    args.progname = parser.prog

    if args.usb_reset:
        args.log("Resetting TRACE32 USB debugger.")
        usb_reset()
        args.log("Reset completed OK.", level=2)


    if args.protocol.lower() == "usb":
        sp_kwargs = {"podbus": Podbus.USB}
    else:
        sp_kwargs = {"sim": Podbus.SIM}

    args.log("Launching TRACE32.")
    with Trace32Subprocess(args.t32bin, **sp_kwargs) as proc:
        args.log("Trace32 launched OK.", level=2)

        with Trace32Interface(port=proc.port, tempdir=proc.tempdir) as iface:
            args.log("Remote interface connected OK.", level=2)

            if args.header:
                args.log(f"Running header script [{args.header.name}].")

                if args.header.seekable():
                    iface.run_scriptfile(args.header.name, logfile=sys.stdout)
                else:
                    iface.run_script(args.header.read(), logfile=sys.stdout)

                args.log(f"Header script completed OK.")

            args.log(f"Launching command [{args.subcommand}].", level=2)
            result = commands[args.subcommand](args)
            args.log(f"Command [{args.subcommand}] completd OK.", level=2)

            if args.footer:
                args.log(f"Running footer script [{args.header.name}].")

                if args.footer.seekable():
                    iface.run_scriptfile(args.footer.name, logfile=sys.stdout)
                else:
                    iface.run_script(args.footer.read(), logfile=sys.stdout)

                args.log(f"Footer script completed OK.")

    return result

    print(args)


if __name__ == "__main__":
    main()
