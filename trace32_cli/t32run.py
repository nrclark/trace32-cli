#!/usr/bin/env python3
""" Provides a Trace32 class that runs the actual Trace32 binary in a polled
loop and provides Queue-based stdin/stdout/stderr/ctrl communication with the
loop. """

import queue
import enum
import subprocess as sp
import shutil
import os
import sys
import socket
import typing
import platform
import glob
import time
import threading
import multiprocessing as mp
import re

from .common import make_tempdir, register_cleanup
from .t32api import Trace32API, CommunicationError

# --------------------------------------------------------------------------- #


def _add_doc(value):
    """ Decorator that adds a docstring to a function. """
    def _doc(func):
        func.__doc__ = value
        return func
    return _doc


def find_trace32_dir(trace32_bin=None):
    """ Finds the install directory for Trace32. Checks to see if 'trace32_bin'
    is in the system PATH, and derives the install directory from that if
    possible. Otherwise, $HOME/t32 and /opt/t32 are checked in that order. """

    if trace32_bin:
        trace32_executable = shutil.which(trace32_bin)

        if trace32_executable is not None:
            dirname = os.path.abspath(os.path.dirname(trace32_executable))

            while dirname != "/":
                if os.path.exists(os.path.join(dirname, "version.t32")):
                    if os.path.exists(os.path.join(dirname, "bin")):
                        return os.path.abspath(dirname)

                dirname = os.path.abspath(os.path.join(dirname, ".."))

    sysdir_choices = [os.path.join(os.path.expanduser("~"), "t32")]

    if "windows" in platform.system().lower():
        sysdir_choices.append("C:\\T32")
        sysdir_choices.append("C:\\t32")
    else:
        sysdir_choices.append("/opt/t32")
        sysdir_choices.append("/usr/local/t32")

    for dirname in sysdir_choices:
        if os.path.exists(os.path.join(dirname, "version.t32")):
            return os.path.abspath(dirname)

    raise ValueError("Couldn't find Trace32 install directory.")


def find_trace32_bin(target, install_dir):
    """ Finds the right trace32 executable for your target bin. If pointed
    at a multi-OS install, the right OS is chosen based on the Python
    interpeter being used. Tries an exact match, but can also pick up -qt
    variants if an exact match isn't found. """

    platname = platform.system().lower()
    if "windows" in platname and target.endswith(".exe"):
        target = target[:-4]

    glob_frag = f"bin/*/{target}*".replace("/", os.sep)
    glob_pattern = os.path.join(os.path.abspath(install_dir), glob_frag)
    matches = glob.glob(glob_pattern)
    match_dirs = [os.path.basename(os.path.dirname(x)) for x in matches]
    bin_platforms = sorted(set(match_dirs))

    if "darwin" in platname:
        bin_platforms = [x for x in bin_platforms if "mac" in x]
    elif "windows" in platname:
        bin_platforms = [x for x in bin_platforms if "windows" in x]
    elif "linux" in platname:
        bin_platforms = [x for x in bin_platforms if "linux" in x]
    elif "solaris" in platname:
        bin_platforms = [x for x in bin_platforms if "suns" in x]

    if "64" in str(platform.architecture()[0]):
        bin_platforms = [x for x in bin_platforms if "64" in x]
    else:
        bin_platforms = [x for x in bin_platforms if "64" not in x]

    if len(bin_platforms) != 1:
        msg = f"Couldn't find a compatible installation in {install_dir}."
        raise OSError(msg)

    bindir = os.path.join(install_dir, "bin", bin_platforms[0])
    glob_pattern = os.path.join(bindir, f"{target}*")

    if "windows" in platname:
        glob_pattern += ".exe"

    matches = glob.glob(glob_pattern)
    matches = sorted([x for x in matches if shutil.which(x)])
    if not matches:
        msg = f"Couldn't find executable with name {target} in {bindir}."
        raise OSError(msg)

    for match in matches:
        if os.path.splitext(os.path.basename(match))[0] == target:
            return match

    return matches[0]


class ThreadedPopen(sp.Popen):
    """ Subclass of subprocess.Popen that connects stdin, stdout, and sterr
    to thread-serviced pipes. Stdin can be sent with write_stdin(). Stdout
    and Stderr can be received with read_stdout() and read_stderr(). Threads
    are transparently created and terminated. """

    def __init__(self, *args, **kwargs):
        self._shutdown = False
        self._threads = []
        self._queues = {
            'ctrl': queue.Queue(),
            'stdin': queue.Queue(),
            'stdout': queue.Queue(),
            'stderr': queue.Queue()
        }

        kwargs['stdin'] = sp.PIPE
        kwargs['stdout'] = sp.PIPE
        kwargs['stderr'] = sp.PIPE
        kwargs['bufsize'] = 0

        super().__init__(*args, **kwargs)
        self._buftype = type(self.stdout.read(0))

        args = (self.stdout, self._queues['stdout'], "read")
        thread = threading.Thread(target=self._service_pipe, args=args)
        self._threads.append(thread)

        args = (self.stderr, self._queues['stderr'], "read")
        thread = threading.Thread(target=self._service_pipe, args=args)
        self._threads.append(thread)

        args = (self.stdin, self._queues['stdin'], "write")
        thread = threading.Thread(target=self._service_pipe, args=args)
        self._threads.append(thread)

        for thread in self._threads:
            thread.start()

    def _shutdown_pipes(self):
        if self._shutdown is False:
            self._queues['stdin'].put(self._buftype())
            for pipe in [self.stdin, self.stdout, self.stderr]:
                pipe.close()
            self._shutdown = True

    @_add_doc(sp.Popen.terminate.__doc__)
    def terminate(self, *args, **kwargs):
        super().terminate(*args, **kwargs)
        self._shutdown_pipes()

    @_add_doc(sp.Popen.kill.__doc__)
    def kill(self, *args, **kwargs):
        super().kill(*args, **kwargs)
        self._shutdown_pipes()

    @_add_doc(sp.Popen.wait.__doc__)
    def wait(self, timeout=None):
        result = super().wait(timeout=timeout)
        self._shutdown_pipes()
        return result

    @_add_doc(sp.Popen.communicate.__doc__)
    def communicate(self, input=None, timeout=None):
        # pylint: disable=redefined-builtin
        if input:
            self.write_stdin(input)
        result = super().communicate(input=None, timeout=timeout)
        self._shutdown_pipes()
        return result

    @_add_doc(sp.Popen.poll.__doc__)
    def poll(self):
        result = super().poll()
        if result is not None:
            self._shutdown_pipes()
        return result

    @staticmethod
    def _service_pipe(iopipe, ioqueue, direction):
        if direction == "read":
            while True:
                try:
                    data = iopipe.read(2**16)
                    ioqueue.put(data)
                # pylint: disable=broad-except
                except Exception:
                    break

        elif direction == "write":
            while True:
                try:
                    data = ioqueue.get()
                    ioqueue.task_done()
                    iopipe.write(data)
                # pylint: disable=broad-except
                except Exception:
                    break

    def _read_queue(self, ioqueue):
        """ Reads all blocks of data from one of the internal ioqueues, joins
        them together, and returns the result. """

        blocks = []
        try:
            while True:
                if ioqueue.empty():
                    break

                blocks.append(ioqueue.get_nowait())
                ioqueue.task_done()
        except queue.Empty:
            pass

        return self._buftype().join(blocks)

    def write_stdin(self, data):
        """ Writes a block of data to the Trace32 subprocess. Can be called
        prior to launching run() if desired. """

        self._queues['stdin'].put(data)

    def read_stdout(self):
        """ Gets all data waiting in the Trace32 subprocess's stdout queue,
        and returns it as a single string. """

        return self._read_queue(self._queues['stdout'])

    def read_stderr(self):
        """ Gets all data waiting in the Trace32 subprocess's stderr queue,
        and returns it as a single string. """

        return self._read_queue(self._queues['stderr'])


class Podbus(enum.Enum):
    """ Enumeration of all supported Podbus interfaces. This could grow to
    include TCP or other more exotic alternatives in the future. """

    SIM = enum.auto()
    USB = enum.auto()


class Trace32Subprocess:
    """ Class for running Trace32 in a subprocess, and communicating with its
    stdin/stdout/stderr via queues. This class can be used as a 'with'
    context-manager if you want it to attempt an API-based request for Trace32
    to quite gracefully. """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, trace32_bin, podbus: Podbus = Podbus.SIM, gui=False,
                 libfile=None):
        self.port, self._dummy_socket = self._get_port()
        self.t32dir = find_trace32_dir(trace32_bin)
        self.t32bin = find_trace32_bin(trace32_bin, self.t32dir)

        self._tempdir_obj = make_tempdir()
        self.tempdir = self._tempdir_obj.name

        self.config_file = os.path.join(self.tempdir, "trace32.cfg")
        self.popen = None
        self.podbus = podbus
        self.libfile = libfile

        with open(self.config_file, "w") as outfile:
            outfile.write(self._genconfig(gui, podbus))

    @staticmethod
    def _api_quit(libfile, port):
        api = Trace32API(libfile)
        api.T32_Config("NODE=", "localhost")
        api.T32_Config("PORT=", port)
        api.T32_Init()
        api.T32_Terminate(1)
        api.T32_Exit()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exception_type, exception_val, trace):
        graceful_exit = 0

        if self.popen is None:
            return

        if self.popen.poll() is not None:
            return

        if exception_type in (None, KeyboardInterrupt):
            graceful_exit = 1

        elif exception_type not in (CommunicationError,):
            graceful_exit = 1

        if graceful_exit:
            args = (self.libfile, self.port)
            proc = mp.Process(target=self._api_quit, args=args, daemon=True)
            proc.start()
            timeout = time.time() + 1

            while proc.is_alive():
                time.sleep(0.01)
                if time.time() > timeout:
                    break

            if proc.exitcode == 0:
                timeout = 10

            elif proc.exitcode is None:
                proc.terminate()
                timeout = 0.25

            timeout = time.time() + timeout
            while True:
                if self.popen.poll() is not None:
                    return

                time.sleep(0.01)
                if time.time() > timeout:
                    break

        self.stop(0.25)

    @staticmethod
    def _get_port(port: typing.Optional[int] = None):
        """ Finds an available port. Can be either for TCP or UDP. Returns the
        port number, and a dummy socket that should be held open until the port
        is going to be used. """

        port = 0 if (port is None) else port

        socktype = socket.SOCK_STREAM
        temp_socket = socket.socket(socket.AF_INET, socktype)

        try:
            temp_socket.bind(('', port))
        except (OSError, PermissionError):
            err_msg = f"couldn't bind to port [{port}] in TCP mode."
            if port == 0:
                err_msg = "couldn't find available port for TCP."

            sys.stderr.write(f"Error: {err_msg}\n")
            sys.exit(1)

        temp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        port = int(temp_socket.getsockname()[1])
        return (port, temp_socket)

    def _genconfig(self, gui: bool, podbus: Podbus):
        config = """
        OS=
        SYS=@T32DIR@
        TMP=@TMPDIR@

        RCL=NETTCP
        PORT=@PORT@
        """
        if not gui:
            config += """
            SCREEN=OFF
            MOUSE=OFF
            KEY=OFF
            SOUND=OFF
            """

        if podbus == Podbus.USB:
            config += """
            PBI=
            USB
            CONNECTIONMODE=AUTOCONNECT
            """
        else:
            config += """
            PBI=SIM
            """

        config = "\n".join([x.strip() for x in config.strip().splitlines()])
        config = config.strip() + "\n"

        replacements = {
            "T32DIR": self.t32dir,
            "TMPDIR": self.tempdir,
            "PORT": self.port,
        }

        for key in replacements:
            config = config.replace(f"@{key}@", str(replacements[key]))

        return config

    def stop(self, wait_kill=5):
        """ Shuts down trace32 by sending SIGTERM to the subprocess, followed
        by SIGKILL if it didn't respond to SIGTERM within 2 seconds. """

        progname = os.path.basename(self.t32bin)

        if self.popen is None:
            return -1

        if self.popen.returncode is not None:
            return self.popen.returncode

        sys.stderr.write(f"Aborting {progname}.\n")
        if self.podbus == Podbus.USB:
            msg = "Please reset the Trace32 USB debugger afterwards.\n"
            sys.stderr.write(msg)

        self.popen.terminate()
        timeout = time.time() + wait_kill

        while time.time() < timeout:
            self.popen.poll()
            if self.popen.returncode is not None:
                return self.popen.returncode
            time.sleep(0.01)

        self.popen.kill()

        sys.stderr.write(f"Issued SIGKILL to {progname}.\n")

        timeout = time.time() + wait_kill
        while time.time() < timeout:
            self.popen.poll()
            if self.popen.returncode is not None:
                return self.popen.returncode
            time.sleep(0.01)

        sys.stderr.write(f"Fatal: failed to halt {progname}.\n")
        return -1

    def start(self):
        """ Runs {self.t32bin} as a subprocess with pipe-connected stdin,
        stdout, and stderr attached to thread-serviced queues, and returns the
        active popen instance. I/O can be accessed with popen.write_stdin(),
        popen.read_stdout(), and popen.read_stderr() respectively."""

        cmd = [self.t32bin, "-c", self.config_file]

        if 'CREATE_NEW_PROCESS_GROUP' in dir(sp):
            flag = sp.__dict__['CREATE_NEW_PROCESS_GROUP']
            extra_arg = {'creationflags': flag}
        else:
            extra_arg = {"start_new_session": True}

        self._dummy_socket.close()
        self.popen = ThreadedPopen(cmd, **extra_arg)
        register_cleanup(self.popen.kill)


def usb_reset():
    """ Run a Trace32 USB reset using t32usbchecker, which is a utility
    included in the Trace32 installation. It verifies USB communication
    with the debug probe, and also resets the probe's internal state.

    This function can be used to recover after force-quitting a Trace32
    instance and leaving the probe in an unstable state. """

    t32dir = find_trace32_dir()
    t32bin = find_trace32_bin("t32usbchecker", t32dir)
    result = sp.run([t32bin], stdout=sp.PIPE, encoding='latin-1', check=True)
    stdout = re.sub("[ \t\n\r]+", " ", result.stdout.lower())
    if "USB communication OK".lower() not in stdout:
        raise IOError("Can't enable USB communication with Trace32")
