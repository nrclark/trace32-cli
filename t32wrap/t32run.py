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

from .common import make_tempdir

# --------------------------------------------------------------------------- #


class Podbus(enum.Enum):
    """ Enumeration of all supported Podbus interfaces. This could grow to
    include TCP or other more exotic alternatives in the future. """

    SIM = enum.auto()
    USB = enum.auto()


class Trace32Subprocess:
    """ Class for running Trace32 in a subprocess, and communicating with its
    stdin/stdout/stderr via queues. """
    # pylint: disable=too-many-instance-attributes

    def __init__(self, trace32_bin, podbus: Podbus = Podbus.SIM, gui=False):
        self.port, self.dummy_socket = self._get_port()
        self.t32dir = self._find_trace32_dir(trace32_bin)
        self.t32bin = self._find_program(trace32_bin, self.t32dir)

        self.buftype = str
        self._tempdir_obj = make_tempdir()
        self.tempdir = self._tempdir_obj.name

        self.config_file = os.path.join(self.tempdir, "trace32.cfg")
        with open(self.config_file, "w") as outfile:
            outfile.write(self._genconfig(gui, podbus))

        self._queues = {
            'ctrl': queue.Queue(),
            'stdin': queue.Queue(),
            'stdout': queue.Queue(),
            'stderr': queue.Queue()
        }

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

    @staticmethod
    def _find_trace32_dir(trace32_bin=None):
        """ Finds the install directory for Trace32. Checks to see if
        'trace32_bin' is in the system PATH, and derives the install directory
        from that if possible. Otherwise, $HOME/t32 and /opt/t32 are checked
        in that order. """

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

    @staticmethod
    def _find_program(target, install_dir):
        """ Finds the right trace32 executable for your target bin. If pointed
        at a multi-OS install, the right OS is chosen based on the Python
        interpeter being used. Tries an exact match, but can also pick up
        -qt variants if an exact match isn't found. """

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

    def stop(self):
        """ Shuts down trace32 by sending SIGTERM to the subprocess, followed
        by SIGKILL if it didn't respond to SIGTERM. """

        self._queues['ctrl'].put("stop")

    def run(self, program, args=(), pollrate=0.025):
        """ Runs {program} as a subprocess, with pipe-connected stdin, stdout,
        and stderr. Supplies data from a queue into stdin. Reads stdout/stderr
        to queues. Can be signalled to terminate by stop(). This function is
        suitable for running in a background thread to support cross-platform
        nonblocking I/O. """

        cmd = [program] + args
        timeout = 0

        if 'CREATE_NEW_PROCESS_GROUP' in dir(sp):
            flag = sp.__dict__['CREATE_NEW_PROCESS_GROUP']
            extra_arg = {'creationflags': flag}
        else:
            extra_arg = {"start_new_session": True}

        self.dummy_socket.close()
        popen = sp.Popen(cmd, bufsize=0, stdin=sp.PIPE, stdout=sp.PIPE,
                         stderr=sp.PIPE, encoding="latin-1", *extra_arg)

        self.buftype = type(popen.stdout.read(0))

        while True:
            if self._queues['ctrl'].empty() is False:
                ctrl = self._queues['ctrl'].get()
                if ctrl not in ['stop']:
                    raise ValueError(f"Unknown control command [{ctrl}]")

                popen.terminate()
                timeout = time.time() + 2

            if timeout and (time.time() > timeout):
                timeout = 0
                popen.kill()
                progname = os.path.dirname(program)
                sys.stderr.write(f"Issued SIGKILL to {progname}.\n")

            buffer = popen.stdout.read(2**16)
            if buffer:
                self._queues['stdout'].put(buffer)

            buffer = popen.stderr.read(2**16)
            if buffer:
                self._queues['stderr'].put(buffer)

            if self._queues['stdin'].empty() is False:
                buffer = self._queues['stdin'].get()
                popen.stdin.write(buffer)

            if popen.poll() is not None:
                return popen.returncode

            time.sleep(pollrate)

    def stdin(self, data):
        """ Writes a block of data to the Trace32 subprocess. Can be called
        prior to launching run() if desired. """

        self._queues['stdin'].put(data)

    def stdout(self):
        """ Gets all data waiting in the Trace32 subprocess's stdout queue,
        and returns it as a single string. """
        blocks = []
        try:
            while True:
                if self._queues['stdout'].empty():
                    break

                blocks.append(self._queues['stdout'].get_nowait())
        except queue.Empty:
            pass

        return self.buftype().join(blocks)

    def stderr(self):
        """ Gets all data waiting in the Trace32 subprocess's stderr queue,
        and returns it as a single string. """
        blocks = []
        try:
            while True:
                if self._queues['stderr'].empty():
                    break

                blocks.append(self._queues['stderr'].get_nowait())
        except queue.Empty:
            pass

        return self.buftype().join(blocks)