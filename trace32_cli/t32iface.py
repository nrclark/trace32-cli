#!/usr/bin/env python3
""" High-level wrapper module for interfacing with a Trace32 API. Provides a
class that uses the lower-level Trace32API to provide a set of useful functions
for interfacing with TRACE32. """

import ctypes
import os
import re
import time
import tempfile
import random
import multiprocessing as mp
import sys


from .t32api import Trace32API, PracticeState, MessageType, ResultType
from .t32api import EvalError, CommandFailure, CommunicationError
from .common import register_cleanup, make_tempdir

# --------------------------------------------------------------------------- #


class ScriptFailure(Exception):
    """ Exception class used to report that a PRACTICE script failed. Contains
    the failing script, and also some data about the error. """

    def __init__(self, script, error):
        super().__init__()
        self.script = script
        self.error = error

    def __str__(self):
        return repr(self.error)


def until_keyword(file_obj, keyword, maxblock=None, poll_rate=None):
    """ Calls $file_obj.read() repeatedly (with an adjustable polling rate).
    Retreives and yields as much data as possible, until $keyword is
    encountered. Intended to be used to fetch all of file_obj's data up until
    (but not including) $keyword. """

    buffer = type(file_obj.read(0))()
    assert isinstance(keyword, type(buffer))

    # the longest match is dropped because it's tested single-case.
    keychunks = [keyword[0:k] for k in range(1, len(keyword) + 1)]
    keychunks = keychunks[-2::-1]

    # the longest match is dropped because it's tested single-case.
    yield buffer[0:0]

    while True:
        block = file_obj.read(maxblock)
        buffer = buffer + block
        index = buffer.find(keyword)

        if index != -1:
            yield buffer[0:index]
            break

        for keychunk in keychunks:
            if buffer.endswith(keychunk):
                yield buffer[0:-len(keychunk)]
                buffer = keychunk
                break
        else:
            yield buffer
            buffer = buffer[0:0]

        if poll_rate is not None:
            time.sleep(poll_rate)

# --------------------------------------------------------------------------- #


class Trace32Interface:
    """ High-level Trace32 interface that provides better-integrated functions
    for running commands and/or scripts, and evaluating literals. The interface
    uses a FIFO on the filesystem to pipe data out from a newly-created AREA.

    The routines in this class wrap a lot of the oddness/non-standard error
    handling that's necessary to automate error detection. Trace32 reports
    errors in a few different ways, all generally quite obnoxious.

    This class can be used as a 'with' context-manager for auto-disconnect."""

    # pylint: disable=too-many-instance-attributes

    def __init__(self, libfile=None, tempdir=None, port=None, node=None):

        self.api = Trace32API(libfile)

        self.area = None
        self.connected = False

        if tempdir is None:
            self._tempdir_obj = make_tempdir()
            self.tempdir = self._tempdir_obj.name
        else:
            self.tempdir = tempdir

        fifo_name = os.path.join(self.tempdir, "area.fifo")
        os.mkfifo(fifo_name)
        fileno = os.open(fifo_name, os.O_RDONLY | os.O_NONBLOCK)
        self.fifo = os.fdopen(fileno, 'r')
        self.fifo.read(4096)
        self.fifo_name = fifo_name
        self.node = node
        self.port = port
        self.packlen = None
        self.libfile = libfile

    def __enter__(self):
        kwargs = {}
        if self.node:
            kwargs['node'] = self.node

        if self.port:
            kwargs['port'] = self.port

        self.connect(**kwargs)
        return self

    def __exit__(self, exception_type, exception_val, trace):
        if exception_type is None:
            self.disconnect()
        else:
            self.api.T32_Exit()

    @staticmethod
    def _try_attach(libfile, node, port, packlen):
        """ Utility function that initializes a Trace32 API session and then
        closes it. Intended to be used as a background task to validate
        connectivity with Trace32. """
        try:
            api = Trace32API(libfile)
            api.T32_Config("NODE=", node)
            api.T32_Config("PORT=", port)

            if packlen:
                api.T32_Config("PACKLEN=", packlen)

            api.T32_Init()
            api.T32_Attach()
            api.T32_Exit()
        except (KeyboardInterrupt, CommunicationError):
            sys.exit(1)

    def connect(self, node="localhost", port=20000, packlen=None, timeout=10):
        """ Connect to a Trace32 instance. """

        self.node = node
        self.port = port
        self.packlen = packlen

        self._connect_lowlevel(timeout)

        name = [chr(random.randint(ord('A'), ord('Z'))) for _ in range(8)]
        self.area = ''.join(name)

        # The geometry of this window was experimentally determined by hunting
        # around. Trace32 doesn't let you make an infinite-sized window, but
        # also doesn't clearly state where the limits are. Experimentally,
        # the limit is a 4095x32767-sized window. We don't need to buffer that
        # many lines though, since we're configuring the AREA to pipe directly
        # out to a FIFO.

        cmds = [
            f"AREA.Create {self.area} 4095. 1024.",
            f"AREA.OPEN {self.area} {self.fifo_name} /Append /NoFileCache",
            f"AREA.Select {self.area}"
        ]

        while self.fifo.read(4096):
            pass

        for cmd in cmds:
            self.api.T32_Cmd(cmd)

    def _connect_lowlevel(self, timeout=10):
        """ Connect to a Trace32 instance. """

        timeout_time = time.time() + timeout

        while True:
            if time.time() > timeout_time:
                raise CommunicationError("init/attach timeout", 1)

            args = (self.libfile, self.node, self.port, self.packlen)
            proc = mp.Process(target=self._try_attach, args=args, daemon=True)
            proc.start()
            attach_timeout = time.time() + 0.5
            while True:
                if (time.time() > attach_timeout) or not proc.is_alive():
                    break

                if time.time() > timeout_time:
                    raise CommunicationError("init/attach timeout", 1)

                time.sleep(0.01)

            if proc.is_alive():
                proc.terminate()

            elif proc.exitcode == 0:
                break

        self.api.T32_Config("NODE=", self.node)
        self.api.T32_Config("PORT=", self.port)

        if self.packlen:
            self.api.T32_Config("PACKLEN=", self.packlen)

        init_ok = False

        while True:
            if time.time() > timeout_time:
                raise CommunicationError("init/attach timeout", 1)

            try:
                self.api.T32_Init()
                init_ok = True
                break
            except CommunicationError as err:
                last_exception = err
                time.sleep(0.01)

        if not init_ok:
            raise last_exception

        register_cleanup(self.api.T32_Exit)

        self.api.T32_Attach()
        self.api.T32_Ping()
        self.connected = True

    def _reconnect(self):
        """ Reconnect to a preconfigured to a Trace32 instance. """

        self.api.T32_Config("NODE=", self.node)
        self.api.T32_Config("PORT=", self.port)

        if self.packlen:
            self.api.T32_Config("PACKLEN=", self.packlen)

        self.api.T32_Init()
        self.api.T32_Attach()
        self.api.T32_Ping()

        self.connected = True

    def disconnect(self, shutdown=False, exit_code=None):
        """ Disconnect from a Trace32 instance. """

        if not self.connected:
            return

        if shutdown:
            if exit_code is None:
                exit_code = 0

            self.api.T32_Terminate(exit_code)

        else:
            cmds = [
                f"AREA.CLOSE {self.area}",
                f"AREA.Delete {self.area}",
            ]

            for cmd in cmds:
                self.api.T32_Cmd(cmd)

        self.api.T32_Exit()
        self.connected = False

    def ping(self):
        """ Checks to make sure that the API is connected and active. """
        self.api.T32_Ping()

    def read_memory(self, address, length, address_width=None):
        """ Reads a block of data from the target's memory-space and
        returns it. Set address_width to 32 or 64 for an explicit value,
        or else it'll be auto-determined. """

        if address_width is None:
            if address >= 2**32:
                address_width = 64
            else:
                address_width = 32

        buffer = ctypes.create_string_buffer(length)
        self.api.dll.read_memory(address, address_width, buffer, length)
        return buffer.raw

    def write_memory(self, address, data, address_width=None):
        """ Writes a block of data to the target's memory-space. Set
        address_width to 32 or 64 for an explicit value, or else it'll be
        auto-determined. """

        if address_width is None:
            if address >= 2**32:
                address_width = 64
            else:
                address_width = 32

        assert isinstance(data, bytes)
        self.api.dll.write_memory(address, address_width, data, len(data))

    def clear_area(self):
        """ Clears the current AREA, and drops any data pending in the input
        FIFO (which is connected to that AREA). Set the message-string to
        a detectable flag-value, and return that value. """

        self.api.T32_Cmd(f"AREA.CLEAR {self.area}")
        self.api.T32_Cmd(f"AREA.Select {self.area}")
        while self.fifo.read(4096):
            pass

        chars = [chr(random.randint(ord('A'), ord('Z'))) for _ in range(16)]
        flag_message = f"Semaphore {''.join(chars)}"
        self.api.T32_Cmd(f'Print %AREA A000 "{flag_message}"')
        message_string = self.api.T32_GetMessageString()
        assert message_string['msg'] == flag_message
        return flag_message

    @staticmethod
    def _wait_idle(libfile, node, port, packlen):
        """ Creates a new API instance and uses it to poll the
        T32_GetPracticeState function.  Blocks until T32_GetPracticeState()
        returns Idle. This function is intended to be used in a background
        thread/process, while the main API is disconnected. """

        api = Trace32API(libfile)
        api.T32_Config("NODE=", node)
        api.T32_Config("PORT=", port)
        if packlen:
            api.T32_Config("PACKLEN=", packlen)

        api.T32_Init()

        try:
            while True:
                practice_state = api.T32_GetPracticeState()
                if practice_state == PracticeState.Idle:
                    break

                time.sleep(0.01)
        except KeyboardInterrupt:
            pass

        api.T32_Exit()

    @staticmethod
    def _validate_script(scriptfile):
        """ Sanity-check a PRACTICE script before running it. """
        script = open(scriptfile).read().strip()
        lines = re.sub("^[ \t]*;.*?$", "", script, flags=re.M).splitlines()
        lines = [x.strip() for x in lines]
        lines = [x for x in lines if x]

        if not lines[-1].startswith("ENDDO"):
            err_msg = "Error: %s is missing final ENDDO statement."
            raise ValueError(err_msg % scriptfile)

    def run_file(self, scriptfile, args=(), logfile=None):
        """ Run a PRACTICE script that exists on the filesystem. """

        buffer = ""
        self._validate_script(scriptfile)
        msgline_flag = self.clear_area()

        cmd = f"DO {os.path.abspath(scriptfile)}"
        if args:
            cmd += " " + " ".join(args)

        self.api.T32_ExecuteCommand(cmd)

        # A background task is used to poll Trace32 and wait until the script
        # exits. This allows us to continue retrieving FIFO data while the
        # script runs, and is necessary because some Trace32 operations can
        # block its ability to respond to API calls.

        # To accomplish this, the main API is shut down with T32_Exit() so that
        # it's available to the background task. Then, it's re-initialized
        # after the background task is completed.

        self.api.T32_Exit()
        self.connected = False
        caught_exception = None

        args = (self.libfile, self.node, self.port, self.packlen)
        proc = mp.Process(target=self._wait_idle, args=args, daemon=True)
        proc.start()

        try:
            while True:
                output = self.fifo.read(4096)
                if logfile:
                    logfile.write(output)
                buffer += output

                if not proc.is_alive():
                    break

                time.sleep(0.025)

        # pylint: disable=broad-except
        except Exception as err:
            caught_exception = err

        # At the conclusion of proc.is_alive(), Trace32 has reported that the
        # script is finished (or there was an abnormal exit of some kind).
        # The proc is expliticly terminated as a just-in-case, and then the API
        # is re-initialized.

        proc.terminate()
        self._reconnect()

        if caught_exception:
            raise caught_exception

        # After running the script, a random string is generated and printed
        # to the Trace32 AREA. This flag is then detected using until_keyword()
        # as a reliable means to make sure that we've captured all of the
        # script's output data.

        flag = [chr(random.randint(ord('A'), ord('Z'))) for _ in range(16)]
        flag = "".join(flag)
        self.api.T32_Cmd(f'PRINT %AREA {self.area} "{flag}"')

        for chunk in until_keyword(self.fifo, flag, maxblock=4096,
                                   poll_rate=0.05):
            if logfile:
                logfile.write(chunk)

            buffer += chunk

        while self.fifo.read(4096):
            pass

        message_string = self.api.T32_GetMessageString()
        if message_string['msg'] != msgline_flag:
            buffer += "\n" + message_string['msg']
            err_types = [MessageType.Error, MessageType.Error_Info]
            if [x for x in message_string['types'] if x in err_types]:
                raise ScriptFailure(scriptfile, message_string)

        return buffer

    def run_script(self, script, args=(), logfile=None):
        """ Run a PRACTICE script supplied as a string. """

        lines = re.sub("^;.*?$", "", script.strip(), flags=re.M).splitlines()
        lines = [x.strip() for x in lines]

        if not lines[-1].startswith("ENDDO"):
            script = script + "\nENDDO"

        script = script.strip() + "\n"
        with tempfile.NamedTemporaryFile(dir=self.tempdir, suffix=".cmm",
                                         mode="w+") as outfile:
            outfile.write(script)
            outfile.flush()
            try:
                return self.run_file(outfile.name, args=args, logfile=logfile)
            except ScriptFailure as err:
                err.script = script
                raise err

    def run_command(self, cmd, logfile=None):
        """ Run a single command and return the result. Optionally, also write
        the result to a logfile as its received. """

        msgline_flag = self.clear_area()
        while self.fifo.read(4096):
            pass

        self.api.T32_ExecuteCommand(cmd)

        flag = [chr(random.randint(ord('A'), ord('Z'))) for _ in range(16)]
        flag = "".join(flag)
        self.api.T32_Cmd(f'PRINT %AREA {self.area} "{flag}"')

        fetcher = until_keyword(self.fifo, flag, maxblock=4096,
                                poll_rate=0.05)
        buffer = ""
        for chunk in fetcher:
            if logfile:
                logfile.write(chunk)

            buffer += chunk

        while self.fifo.read(4096):
            pass

        if logfile:
            if len(buffer) > 1 and buffer[-1] != '\n':
                logfile.write('\n')

        message_string = self.api.T32_GetMessageString()

        if message_string['msg'] != msgline_flag:
            err_types = [MessageType.Error, MessageType.Error_Info]
            if [x for x in message_string['types'] if x in err_types]:
                raise CommandFailure(cmd, message_string['msg'].strip())

            if logfile:
                msg = message_string['msg'].strip()
                if msg:
                    logfile.write(msg + '\n')

        return buffer

    @staticmethod
    def _decode_eval_result(result):
        """ Decode the result from a call to T32_ExecuteFunction() into a
        Python literal. """

        if result['type'] == ResultType.Boolean:
            if result['msg'].lower() in ["true", "true()", "1"]:
                return True

            if result['msg'].lower() in ["false", "false()", "0"]:
                return False

            err_msg = f"Unknown mapping from [{result['msg']}] to bool."
            raise ValueError(err_msg)

        if result['type'] == ResultType.Hexadecimal:
            result = int(result['msg'], 16)

        elif result['type'] == ResultType.Binary:
            msg = re.sub("[!]$", "", result['msg'])
            msg = re.sub("^(0y){0,1}", "0b", msg)
            result = int(msg, 2)

        elif result['type'] == (ResultType.Decimal):
            msg = re.sub("[.]$", "", result['msg'])
            result = int(msg, 10)

        elif result['type'] == (ResultType.Float):
            result = float(result['msg'])

        else:
            result = result['msg']

        return result

    def eval_expression(self, expression, decode=True, logfile=None):
        """ Run a single command and return the result. Optionally, also write
        the result to a logfile as its received. """

        msgline_flag = self.clear_area()
        result = self.api.T32_ExecuteFunction(expression)

        message_string = self.api.T32_GetMessageString()
        if message_string['msg'] != msgline_flag:
            err_types = [MessageType.Error, MessageType.Error_Info]
            if [x for x in message_string['types'] if x in err_types]:
                raise EvalError(message_string['msg'], expression)

        if logfile:
            logfile.write(result['msg'])

            if len(result['msg']) > 1 and result['msg'][-1] != '\n':
                logfile.write('\n')

        if not decode:
            return result

        return self._decode_eval_result(result)
