#!/usr/bin/env python3
"""CLI utility for launching and controlling a Trace32 instance to do useful
things."""

import argparse
import sys
import re
import os
import io
import time

from .t32api import CallFailure

from .t32run import usb_reset, Trace32Subprocess
from .t32run import find_trace32_dir, find_trace32_bin, Podbus

from .t32iface import Trace32Interface, CommandFailure
from .version import __version__

# --------------------------------------------------------------------------- #


class Reporter:
    """ Class for printing the progress on a read/write operation. Logs
    the number of bytes processed, and also the % complete (if known). """
    # pylint: disable=too-many-instance-attributes

    def __init__(self, size=None, poll=0.25, prefix="", outfile=sys.stdout):
        self.size = size
        self.total = 0
        self.prefix = prefix
        self.outfile = outfile
        self.poll = poll
        self.next_time = 0
        self.prev_progress = None
        self.rounded = False

    def stringify_size(self, value):
        """ Returns a normalized/formatted version of 'value' for human
        consumption. """

        if value == 1:
            return "1 byte"

        suffixes = ["bytes", "kB", "MB", "GB"]

        for suffix in suffixes:
            if value < 1024:
                if not self.rounded and (round(value) == value):
                    return f"{round(value)} {suffix}"

                self.rounded = True
                return "%.1f %s" % (float(round(value, 1)), suffix)
            value = value / 1024

        return f"{round(value * 1024)} {suffix}"

    def __call__(self, count=0):
        """ Adds count to the total progress. Prints the total progress to
        self.outfile. """

        self.total += count

        current_time = time.monotonic()
        if current_time < self.next_time:
            return

        self.next_time = current_time + self.poll
        progress_string = f"{self.prefix}{self.stringify_size(self.total)}"

        if self.size is not None:
            percentage = float(round(100.0 * self.total / self.size, 1))
            progress_string += " (%.1f%%)" % percentage

        progress_string += " "

        if self.prev_progress:
            if self.prev_progress == progress_string:
                return

            eraser = "\r" + " " * len(self.prev_progress) + "\r"
            self.outfile.write(eraser + progress_string)
        else:
            self.outfile.write(progress_string)

        self.prev_progress = progress_string
        self.outfile.flush()


def read(args, iface: Trace32Interface):
    """ Routine for reading data from the target's memory, and writing to
    stdout or to an outfile. """

    outfile = None
    received = 0

    if args.reference:
        length = os.path.getsize(args.reference)
    else:
        length = args.count

    reporter = None

    if args.logdest.isatty() and not args.quiet:
        reporter = Reporter(length, prefix="read: ", outfile=args.logdest)
        reporter(0)

    while received < length:
        chunksize = min(args.blocksize, length - received)
        address = args.address + received

        args.log(f"Reading {chunksize} bytes from {hex(address)}", level=3)
        for retries in range(1, 9):
            try:
                block = iface.read_memory(address, chunksize)
                break
            except CallFailure as err:
                msg = f"Read attempt {retries} failed. Retrying read "
                msg += f"from {hex(address)}."
                args.log(msg, level=2)
        else:
            raise err

        assert len(block) == chunksize

        if outfile is None:
            if args.outfile is None:
                outfile = sys.stdout.buffer
            else:
                # pylint: disable=consider-using-with
                outfile = open(args.outfile, 'wb')

        outfile.write(block)
        received += chunksize

        if reporter:
            reporter(len(block))

    if args.outfile is not None:
        outfile.close()


def api_write_block(infile: io.IOBase, address: int, iface: Trace32Interface,
                    args: argparse.Namespace):

    """ Read a block of data from infile, and write it to an address in the
    target's memory using C API calls. Optionally do a readback if args.check
    is 'full'. Retry reads, writes, and readbacks up to 8 times. """

    block = infile.read(args.blocksize)

    if not block:
        return 0

    args.log(f"Writing {len(block)} bytes to {hex(address)} via API", level=3)

    for block_tries in range(1, 9):
        for call_tries in range(1, 9):
            try:
                iface.write_memory(address, block)
                break
            except CallFailure as err:
                msg = f"Write attempt {call_tries} failed. Retrying write "
                msg += f"to {hex(address)}."
                args.log(msg, level=2)
        else:
            raise err

        if args.check != "full":
            break

        msg = f"Verifying {len(block)} bytes at {hex(address)}"
        args.log(msg, level=3)

        for call_tries in range(1, 9):
            try:
                readback = iface.read_memory(address, len(block))
                break
            except CallFailure as err:
                msg = f"Read attempt {call_tries} failed. Retrying read "
                msg += f"from {hex(address)}."
                args.log(msg, level=2)
        else:
            raise err

        if readback == block:
            break

        msg = f"Readback attempt {block_tries} mismatch. Retrying block "
        msg += f"for {hex(address)}."
        args.log(msg, level=2)
    else:
        raise IOError(f"Hit retry limit on write/verify to {hex(address)}")

    return len(block)


def cmd_write_block(infile: io.IOBase, address: int, iface: Trace32Interface,
                    args: argparse.Namespace):

    """ Write data to memory using PRACTICE DATA.LOAD.BINARY commands. Knows
    how to use "sparse" and "checksum" modes. """

    if infile.seekable() and os.path.isfile(infile.name):
        position = infile.tell()
        length = infile.seek(0, os.SEEK_END)

        size = min(args.blocksize, length - position)
        if size == 0:
            return 0

        infile.seek(position + size, os.SEEK_SET)
        command = f'Data.LOAD.Binary "{infile.name}"'
        command += f' {hex(address)}++{hex(size - 1)}'
        command += f" /SKIP {hex(position)}"

    else:
        buffer_file = os.path.join(iface.tempdir, "buffer.bin")
        block = infile.read(args.blocksize)
        size = len(block)
        if size == 0:
            return 0

        with open(buffer_file, "wb") as outfile:
            outfile.write(block)

        command = f'Data.LOAD.Binary "{buffer_file}"'
        command += f' {hex(address)}++{hex(size - 1)}'

    if args.check == "sparse":
        command += " /PVerify"
    else:
        scratchpad_avoid(address, size, args.scratchpad)
        command += f" /CHECKLOAD {hex(args.scratchpad)}++0xFFFF"

    args.log(f"Writing {size} bytes to {hex(address)} via CMD", level=3)
    args.log(f"Running [{command}]", level=3)
    logfile = args.logdest if (args.verbosity >= 3) else None

    for retries in range(1, 9):
        try:
            iface.run_command(command, logfile=logfile)
            return size
        except (CallFailure, CommandFailure) as err:
            msg = f"Write attempt {retries} failed. Retrying command "
            msg += f"for {hex(address)}."
            args.log(msg, level=1)

    raise err


def write(args, iface: Trace32Interface):
    """ Routine for writing data to the target's memory from stdin or an
    infile. """

    if args.infile is not sys.stdin.buffer:
        args.log(f"Using file [{args.infile.name}] as input.", level=1)
    else:
        args.log("Using stdin as input.", level=1)

    infile = args.infile
    address = args.address
    length = None

    if infile.seekable() and os.path.isfile(infile.name):
        length = infile.seek(0, os.SEEK_END)
        infile.seek(0, os.SEEK_SET)

    msg = f"Writing to {hex(address)} with a verify-mode of [{args.check}]."
    args.log(msg, level=1)

    if args.check in ("none", "full"):
        writer = api_write_block
    elif args.check in ("sparse", "checksum"):
        writer = cmd_write_block
    else:
        raise ValueError(f"Unknown checker mode [{args.check}]")

    count = None
    total = 0
    reporter = None

    if args.logdest.isatty() and not args.quiet:
        reporter = Reporter(length, prefix="written: ", outfile=args.logdest)
        reporter(0)

    while True:
        count = writer(infile, address + total, iface, args)
        reporter(count)

        if count == 0:
            break

        total += count


def run(args, iface: Trace32Interface):
    """ Routine for running a PRACTICE/TRACE32 command or script. """

    if args.command:
        cmd = ' '.join(args.statement)
        args.log(f"Running command [{cmd}]", level=2)
        iface.run_command(cmd, logfile=args.logdest)

    else:
        script = args.statement[0]
        args.log(f"Running script [{script}] with args {args.statement[1:]}",
                 level=2)
        iface.run_file(script, args.statement[1:], logfile=args.logdest)

# --------------------------------------------------------------------------- #


def scratchpad_avoid(start, length, scratchpad, scratchpad_size=64*1024):
    """ Checks to see if a scratchpad overlaps with the region of memory that
    starts at [start] and ihas a size of [length]. Throws an exception if it
    does. This function can be used to ensure that a checksum scratchpad won't
    accidentally clobber the memory that it's trying to checkum. """
    # pylint: disable=chained-comparison

    for index in (scratchpad, scratchpad + scratchpad_size):
        if (index >= start) and (index < (start + length)):
            msg = "Scratchpad overlaps with target region 0x%X-0x%X"
            msg %= (length, (start + length - 1))
            raise argparse.ArgumentError(None, msg)


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


def make_count(storage: dict, key):
    """ Creates an argparse action that's based on 'count', except it stores
    into an externally-provided dict. This ensures that the action works
    when mixed in-between a subparser and a main parser."""

    if key not in storage:
        storage[key] = 0

    # pylint: disable=protected-access

    class GlobalCounter(argparse._CountAction):
        # pylint: disable=missing-class-docstring,too-few-public-methods
        def __call__(self, parser, namespace, values, option_string=None):
            storage[key] += 1
            setattr(namespace, self.dest, storage[key])

    return GlobalCounter


def make_append(storage: dict, key):
    """ Creates an argparse action that'sn based on 'append', except it stores
    into an externally-provided dict. This ensures that the action works
    when mixed in-between a subparser and a main parser. """

    if key not in storage:
        storage[key] = []

    # pylint: disable=protected-access
    class GlobalAppender(argparse._AppendAction):
        # pylint: disable=missing-class-docstring,too-few-public-methods
        def __call__(self, parser, namespace, values, option_string=None):
            storage[key].append(values)
            setattr(namespace, self.dest, storage[key])

    return GlobalAppender


def common_options(storage: dict, toplevel: bool = False):
    """ These options are shared by all commands in the utility. They're used
    to set up the Trace32 instance, or to tear it down/launch a target after
    programming. """

    argument_default = None if toplevel else argparse.SUPPRESS

    parser = argparse.ArgumentParser(add_help=False,
                                     argument_default=argument_default)

    group = parser.add_argument_group(title="common options")
    modify_add_argument(group)

    group.add_argument("-v", "--verbose", dest="verbosity", help="""Be verbose.
                       Specify multiple times for more verbosity.""",
                       action=make_count(storage, 'verbose'))

    group.add_argument("-H", "--header", metavar="FILE", type=path_readable,
                       action=make_append(storage, 'headers'), help="""PRACTICE
                       script to run before taking any other action
                       (default: %(default)s).""", )

    group.add_argument("-F", "--footer", metavar="FILE", type=path_readable,
                       action=make_append(storage, 'footers'), help="""PRACTICE
                       script to run after finishing all other actions
                       (default: None).""")

    group.add_argument("-u", "--usb-reset", action="store_true", help="""
                        Reset the Trace32 USB debug adapter before launching
                        Trace32.""")

    group.add_argument("-p", "--protocol", metavar="PROTOCOL", choices=["usb",
                       "sim"], default="usb", help="""Protocol to use for
                       communicating with the target. Known protocols are:
                       [usb, sim] (default: usb).""")

    group.add_argument("-t", "--t32bin", metavar="TRACE32BIN",
                       default="t32marm", type=trace32_binary, help="""Trace32
                       binary to use. Controls the target architecture
                       (default: %(default)s).""")

    return parser


def create_parser():
    """ Generates and returns an argparse instance for the CLI tool. """
    storage = {}
    parent_common = [common_options(storage, True)]
    child_common = [common_options(storage, False)]

    top_parser = argparse.ArgumentParser(parents=parent_common)
    top_parser.description = """Command-line tool that uses Lauterbach Trace32
    to control a target device."""

    top_parser.add_argument('-V', '--version', action='version',
                            version='%(prog)s ' + __version__)

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

    parser.add_argument("-q", "--quiet", action="store_true", help="""Suppress
                        progress reporting.""")

    # ----------------------------------------------------------------------- #

    parser = subparsers.add_parser("write", help="""Write raw data to target
                                   memory""", parents=child_common)

    parser.description = """ Write a file to the target's memory. Optionally
    check the result of the write operation using one of three modes: full,
    sparse, and checksum. In [full] verification mode, the write is fully
    verified. In [sparse] verification mode, 1/16 of all writes are verified.
    In [checksum] verification mode, Trace32 uploads a temporary program into
    SPADDRESS and uses it to checksum the target region. """

    parser.add_argument("address", metavar="ADDRESS", help="""Target address to
                        read from the target. Hexadecimal addresses should
                        start with a "0x" prefix.""", type=constant)

    parser.add_argument("infile", metavar="INFILE", nargs="?", help="""Input
                        file to write (default: stdin).""",
                        type=argparse.FileType('rb'), default=sys.stdin.buffer)

    check_modes = ("full", "checksum", "sparse", "none")
    parser.add_argument("-c", "--check", required=False, metavar="MODE",
                        default="full", choices=check_modes,
                        help="""Verification mode for written data. Known modes
                        are: [%(choices)s]. (default: %(default)s).""")

    parser.add_argument("-s", "--scratchpad", required=False,
                        metavar="SPADDRESS", help="""Address for the 64kB
                        scratchpad region needed on-target for 'checksum'
                        verification mode. Ignored unless -c/--check=checksum
                        is used. (default: %(default)s).""", type=constant)

    parser.add_argument("-b", "--blocksize", help="""Maximum blocksize to use
                        for write operations (default: %(default)s).""",
                        default="1M", type=constant)

    parser.add_argument("-q", "--quiet", action="store_true", help="""Suppress
                        progress reporting.""")

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

    if args.footer is None:
        args.footer = []

    if args.header is None:
        args.header = []

    if args.verbosity is None:
        args.verbosity = 0

    if (args.subcommand == 'run') and not args.command:
        if not os.path.exists(args.statement[0]):
            msg = f"PRACTICE script-file [{args.statement[0]}] doesn't exist."
            raise argparse.ArgumentError(None, msg)

    if (args.subcommand == 'write') and (args.check == 'checksum'):
        if args.scratchpad is None:
            msg = "SPADDRESS must be specified for 'checksum' validation mode."
            raise argparse.ArgumentError(None, msg)

        if (args.scratchpad % 16) != 0:
            msg = "SPADDRESS must be on a 16-byte boundary."
            raise argparse.ArgumentError(None, msg)

        if args.infile.seekable():
            length = args.infile.seek(0, io.SEEK_END)
            scratchpad_avoid(args.address, length, args.scratchpad)

    return args

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
        return _cli()

    except KeyboardInterrupt:
        print("Aborted.")
        sys.exit(1)

    except Exception as err:  # pylint: disable=broad-except
        dump_exception(err)
        sys.exit(1)


if __name__ == "__main__":
    exit_code = main()
    if not exit_code:
        sys.exit(0)
    else:
        sys.exit(int(exit_code))
