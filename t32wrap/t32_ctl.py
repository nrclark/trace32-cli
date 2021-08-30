#!/usr/bin/env python3
"""CLI utility for launching and controlling a Trace32 instance to do useful
things."""

import argparse
import sys
import re
import os
import io
import time

from .t32run import usb_reset, Trace32Subprocess
from .t32run import find_trace32_dir, find_trace32_bin, Podbus

from .t32api import Trace32Interface

# --------------------------------------------------------------------------- #


def read(args, iface: Trace32Interface):
    """ Routine for reading data from the target's memory, and writing to
    stdout or to an outfile. """

    outfile = None
    received = 0

    if args.reference:
        length = os.path.getsize(args.reference)
    else:
        length = args.count

    while received < length:
        chunksize = min(args.blocksize, length - received)
        block = iface.read_memory(args.address + received, chunksize)
        assert len(block) == chunksize

        if outfile is None:
            if args.outfile is None:
                outfile = sys.stdout.buffer
            else:
                # pylint: disable=consider-using-with
                outfile = open(args.outfile, 'wb')

        outfile.write(block)
        received += chunksize

    if args.outfile is not None:
        outfile.close()


def write(args):
    """ Routine for writing data to the target's memory from stdin or an
    infile. """

    pass


def run(args, iface):
    """ Routine for running a PRACTICE/TRACE32 command or script. """

    if args.command:
        cmd = ' '.join(args.statement)
        iface.run_command(cmd, logfile=args.logdest)

    else:
        script = args.statement[0]
        iface.run_file(script, args.statement[1:], logfile=args.logdest)

# --------------------------------------------------------------------------- #


def dump_exception(exception, fileobj=sys.stderr):
    """ Print a compact representation of an Exception (suitable for messages
    from a CLI tool) to fileobj. If fileobj is None, return the string
    instead. of printing it."""

    exception_type = str(type(exception))
    exception_type = exception_type.split()[-1]
    exception_type = re.sub("[^A-Za-z0-9_.-]", "", exception_type)
    result = f"Error type: {exception_type}\nError: {str(exception)}"
    if fileobj is None:
        return result

    fileobj.write(result + "\n")
    return None


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
        'm': 1024 * 1024,
        'g': 1024 * 1024 * 1024,
        't': 1024 * 1024 * 1024 * 1024,
        'p': 1024 * 1024 * 1024 * 1024 * 1024
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
        raise argparse.ArgumentError(None, str(err))


def path_readable(filename):
    """ Confirms that filename is a file that can be opened and read. Raises
    an ArgumentError otherwise. """

    try:
        open(filename, 'rb').close()
    except Exception as err:
        sys.stderr.write(f"{str(err)}\n")
        raise argparse.ArgumentError(None, str(err))

    return filename


def path_writeable(filename):
    """ Confirms that filename is a file that can be opened for writing. Raises
    an ArgumentError otherwise. """

    try:
        if os.path.exists(filename):
            open(filename, "r+b").close()
        else:
            open(filename, 'w+b').close()
            os.remove(filename)

    except Exception as err:
        sys.stderr.write(f"{str(err)}\n")
        raise argparse.ArgumentError(None, str(err))

    return filename


def modify_add_argument(parent):
    """ Modifies the add_argument() method of an ArgumentParser argument-parser
    object to work around a bug in the interaction between argparse.SUPPRESS
    and the "%(default)s" operator. """

    add_argument = parent.add_argument

    def make_arg(*args, **kwargs):
        result = add_argument(*args, **kwargs)
        if result.default == argparse.SUPPRESS:
            if result.help:
                result.help = result.help.replace("%(default)s", str(None))

    parent.add_argument = make_arg


class FlagCount(argparse._CountAction):
    """ Custom vesion of _CountAction (used by argparse to implement the
    'count' action) that is cumulative across subparsers. """
    # pylint: disable=protected-access,too-few-public-methods

    _flag_count = 0

    def __call__(self, parser, namespace, values, option_string=None):
        FlagCount._flag_count += 1
        setattr(namespace, self.dest, type(self)._flag_count)


def common_options(toplevel=False):
    """ These options are shared by all commands in the utility. They're used
    to set up the Trace32 instance, or to tear it down/launch a target after
    programming. """

    argument_default = None if toplevel else argparse.SUPPRESS

    parser = argparse.ArgumentParser(add_help=False,
                                     argument_default=argument_default)

    group = parser.add_argument_group(title="common options")
    modify_add_argument(group)

    group.add_argument("-v", "--verbose", dest="verbosity", action=FlagCount,
                       help="""Be verbose. Specify multiple times
                       for more verbosity.""")

    group.add_argument("-H", "--header", metavar="FILE", default=[],
                       action='append', help="""PRACTICE script to run before
                       taking any other action (default: %(default)s).""",
                       type=path_readable)

    group.add_argument("-F", "--footer", metavar="FILE", default=[],
                       action='append', help="""PRACTICEscript to run after
                       finishing all other actions (default: None).""",
                       type=path_readable)

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

    parser.add_argument("address", metavar="ADDRESS", help="""Target address to
                        read from the target. Hexadecimal addresses should
                        start with a "0x" prefix.""", type=constant)

    parser.add_argument("-b", "--blocksize", help="""Maximum blocksize to use
                        for read operations (default: %(default)s).""",
                        default="1M", type=constant)

    parser.add_argument("-o", "--outfile", help="""Output file to write
                        (default: stdout).""", type=path_writeable)

    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument("-r", "--reference", metavar="FILE", required=False,
                       help="""Read a number of bytes equal to the size of
                       FILE. Can be used for readbacks or other similar
                       operations.""", type=path_readable)

    group.add_argument("-c", "--count", help="""Number of bytes to read,
                       starting at ADDRESS and counting upwards.""",
                       type=constant)

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

    check_modes = ("full", "checksum", "partial", "none")
    parser.add_argument("-c", "--check", required=False, metavar="MODE",
                        default="none", choices=check_modes, help="""Checking
                        mode for written data. Known modes are: [%(choices)s].
                        (default: %(default)s).""")

    parser.add_argument("-s", "--scratchpad", required=False,
                        metavar="SPADDRESS", help="""Address for the 64kB
                        scratchpad region needed on-target for 'checksum'
                        verification mode. Ignored unless -c/--check=checksum
                        is used. (default: %(default)s).""", type=constant)

    # ----------------------------------------------------------------------- #

    parser = subparsers.add_parser('run', help='Run a PRACTICE command',
                                   parents=child_common)

    parser.description = """Evaluate a Trace32/PRACTICE statement. Return the
    result if it can be parsed with EVAL, or else try to run it as a
    command."""

    parser.add_argument("-c", "--command", action="store_true",
                        help="""Evaluate STATEMENT as a PRACTICE
                        command/TRACE32 statement instead of as a script
                        filename.""")

    parser.add_argument("statement", metavar="STATEMENT", help="""Script file
                        to run (and arguments to provide to the script). If
                        used with -c/--command, all STATEMENT words are joined
                        to make a single TRACE32 expression. """, nargs="+")

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


# --------------------------------------------------------------------------- #

def create_commenter(verbosity: int, prefix: str = "# ",
                     dest: io.IOBase = sys.stdout):

    """Returns a function that can be used for standardized logging of messages
    from the CLI. All messages are associated with a verbosity (default 1) that
    gets compared against the commenter's requested verbosity at creation-time.
    Messages are only printed if the requested verbosity is high enough. """

    def comment(message: str, level: int = 1):
        if verbosity >= level:
            dest.write(prefix + message + "\n")

    return comment

# --------------------------------------------------------------------------- #


def _cli():
    """ Function that implements the CLI. This is made separate from main()
    to allow for standardized exception handling. """

    parser = create_parser()
    args = run_parser(parser)

    if (args.subcommand == 'read') and not args.outfile:
        args.logdest = sys.stderr
    else:
        args.logdest = sys.stdout

    args.log = create_commenter(args.verbosity, dest=args.logdest)

    if args.subcommand is None:
        parser.error("COMMAND not specified.")

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
        args.log("TRACE32 launched OK.", level=2)

        with Trace32Interface(port=proc.port, tempdir=proc.tempdir) as iface:
            args.log("Remote interface connected OK.", level=2)

            for script in args.header:
                args.log(f"Running header script [{script}].")
                start = time.monotonic()
                iface.run_file(script, logfile=args.logdest)
                stop = time.monotonic()
                args.log("Header script completed OK.")
                args.log("(runtime: %.2f sec)" % (stop - start), level=3)

            args.log(f"Launching command [{args.subcommand}].", level=2)
            start = time.monotonic()
            result = commands[args.subcommand](args, iface)
            stop = time.monotonic()
            args.log(f"Command [{args.subcommand}] completd OK.", level=2)
            args.log("(runtime: %.2f sec)" % (stop - start), level=3)

            for script in args.footer:
                args.log(f"Running footer script [{script}].")
                start = time.monotonic()
                iface.run_file(script, logfile=args.logdest)
                stop = time.monotonic()
                args.log("Footer script completed OK.")
                args.log("(runtime: %.2f sec)" % (stop - start), level=3)

        args.log("Disconnected OK.", level=2)
        args.log("Terminating TRACE32.", level=2)

    args.log("TRACE32 terminated OK.", level=1)
    return result


def main():
    """ Main function for launching the CLI. """

    if os.environ.get("DEBUG", "").lower() in ["1", "yes", "true"]:
        return _cli()

    try:
        # pylint: disable=broad-except
        return _cli()

    except Exception as err:
        dump_exception(err)
        sys.exit(1)


if __name__ == "__main__":
    main()
