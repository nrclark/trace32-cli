#!/usr/bin/env python3
""" CTypes wrapper module for interfacing with a Trace32 API. Wraps most of the
interesting functions documented in api_remote_c.pdf. Intended to be a
better-quality replacement for Lauterbach's `python-legacy` module, and also
their `python-rcl` module (which is missing a lot of functionality at the
time of this writing). """

import ctypes
import enum
import os
import re
import time
import tempfile
import random
import multiprocessing as mp

from .t32api_errors import Errcode
from .common import register_cleanup, make_tempdir

# Errcode is auto-generated by parsing t32.h from the Trace32 CAPI. This assert
# is intended to verify that t32api_errors.py was created correctly.
assert len(Errcode) > 1

# --------------------------------------------------------------------------- #


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


class ApiError(Exception):
    """ Base exception class used to report failed Trace32 API calls. """

    def __init__(self, funcname, errcode):
        super().__init__()
        self.funcname = funcname

        if isinstance(errcode, Errcode):
            self.errcode = errcode
        else:
            matches = [x for x in Errcode if x == int(errcode)]

            if matches:
                self.errcode = matches[0]
            else:
                self.errcode = int(errcode)

    def __str__(self):
        err_msg = f"Function '{self.funcname}' returned nonzero status of "

        if isinstance(self.errcode, Errcode):
            err_msg += f"{self.errcode.value} ({self.errcode.name})."
        else:
            err_msg += str(self.errcode) + "."

        return err_msg


class CommunicationError(ApiError):
    """ Exception class used to report Trace32 API calls that failed
    because of communication errors between this library and the remote
    Trace32 instance. """


class CallFailure(ApiError):
    """ Exception class used to report Trace32 API calls that were sent
    successfully, but returned an error from the remote Trace32 instance. """


class CommandFailure(Exception):
    """ Exception class used to report that a PRACTICE command failed. Contains
    the failing command, and also some data about the error. """

    def __init__(self, command, error):
        super().__init__()
        self.command = command
        self.error = error

    def __str__(self):
        return self.error


class ScriptFailure(Exception):
    """ Exception class used to report that a PRACTICE script failed. Contains
    the failing script, and also some data about the error. """

    def __init__(self, script, error):
        super().__init__()
        self.script = script
        self.error = error

    def __str__(self):
        return repr(self.error)


class EvalError(Exception):
    """ Base exception class used to report failed Trace32 API calls. """

    def __init__(self, reason=None, expression=None):
        super().__init__()
        self.expression = expression
        self.reason = reason
        self.name = re.search("'.*'", str(self.__class__)).group(0)[1:-1]

    @staticmethod
    def _shorten(phrase):
        if phrase is None:
            return "None"
        clip = phrase[:32]
        if clip != phrase:
            clip += "..."
        return clip

    def __str__(self):
        expression = self._shorten(self.expression)

        if self.reason and self.expression:
            return f"[{expression}] ({self.reason})"

        if self.reason:
            return f"{self.reason}"

        if self.expression:
            return f"{expression}"

        return self.name

    def __repr__(self):
        result = self._shorten(self.reason)
        expression = self._shorten(self.expression)
        return f"{self.name}({result}, {expression})"


class AttachType(enum.IntEnum):
    """ Device-types understood by T32_Attach. Note that ICE is an alias for
    ICD. """
    OS = 0
    ICD = 1
    ICE = ICD


class MessageType(enum.IntEnum):
    """ Message types returned by T32_GetMessageString. """
    # pylint: disable = invalid-name
    Ignore = 0
    General_Info = 1
    Error = 2
    Status_Info = 8
    Error_Info = 16
    Temp_Display = 32
    Temp_Info = 64


class PracticeState(enum.IntEnum):
    """ Possible states for the remote's PRACTICE interpeter. """
    # pylint: disable = invalid-name
    Idle = 0
    Running = 1
    Dialog = 2


class ResultType(enum.IntEnum):
    """ Possible types of the result data from T32_ExecuteFunction. """
    # pylint: disable = invalid-name
    Boolean = 0x1
    Binary = 0x2
    Hexadecimal = 0x4
    Decimal = 0x8
    Float = 0x10
    ASCII = 0x20
    String = 0x40
    NumRange = 0x80
    Address = 0x100
    AddrRange = 0x200
    Time = 0x400
    TimeRange = 0x800
    BitMask = 0x4000
    Empty = 0x8000

# --------------------------------------------------------------------------- #


class StringConverter:
    """ Utility class intended to be used as a ctypes argtype. Stringifies
    anything that isn't a str, bytes, or bytearray instance. Converts the
    output to always be a 'bytes' instance, regardless of input. """
    # pylint: disable=too-few-public-methods

    @staticmethod
    def from_param(data):
        """ Converts 'data' to a bytes instance. Stringifies it first, if
        necessary. """

        if isinstance(data, bytearray):
            data = bytes(data)

        if not isinstance(data, bytes):
            data = str(data)

        if isinstance(data, str):
            data = data.encode('ascii')

        return ctypes.c_char_p(data)


def confirm_success(result, func, args=None):
    """ Confirms that the value of result is 0, and then returns it. Raises
    an error otherwise. Intended to commonize error-detection across all
    wrapped functions. """

    if int(result) == Errcode.OK:
        return Errcode(int(result))

    # Note on this: From api_remote_c.pdf, Lauterbach states that negative
    # values are reserved for communication/library errors, and positive
    # values are reserved for failed commands and the like.

    if int(result) in list(Errcode):
        errcode = Errcode(int(result))

        if errcode.value < 0:
            raise CommunicationError(func.__name__, errcode)
    else:
        errcode = int(result)

    arg_strings = []

    for arg in args:
        arg = repr(arg)
        if len(arg) > 64:
            arg = arg[0:64] + "..."

        arg_strings.append(arg)

    arg_str = "(%s)" % ", ".join(arg_strings)
    raise CallFailure(func.__name__ + arg_str, errcode)


# --------------------------------------------------------------------------- #


def _dll_init_generic(dll):
    """ Configure the basic ctypes wrappers of the "Generic API functions"
    imported from the Trace32 CAPI. Note only a subset is wrapped. """

    function_list = [
        'T32_Config', 'T32_Init', 'T32_Exit', 'T32_Attach',
        'T32_Nop', 'T32_Ping', 'T32_Cmd', 'T32_ExecuteCommand',
        'T32_ExecuteFunction', 'T32_Stop', 'T32_EvalGet', 'T32_EvalGetString',
        'T32_GetMessageString', 'T32_Terminate', 'T32_GetPracticeState',
        'T32_ResetCPU', 'T32_Break'
    ]

    for name in function_list:
        function = dll.__getattr__(name)
        function.argtypes = ()
        function.restype = ctypes.c_int
        function.errcheck = confirm_success

    dll.T32_Config.argtypes = (StringConverter, StringConverter)
    dll.T32_Attach.argtypes = (ctypes.c_int,)
    dll.T32_Cmd.argtypes = (StringConverter,)

    dll.T32_ExecuteCommand.argtypes = (
        StringConverter,
        ctypes.POINTER(ctypes.c_char),
        ctypes.c_uint32
    )

    dll.T32_ExecuteFunction.argtypes = (
        StringConverter,
        ctypes.POINTER(ctypes.c_char),
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32)
    )

    dll.T32_EvalGet.argtypes = (ctypes.POINTER(ctypes.c_uint32),)
    dll.T32_EvalGetString.argtypes = (ctypes.POINTER(ctypes.c_char),)

    dll.T32_GetMessageString.argtypes = (
        ctypes.POINTER(ctypes.c_char),
        ctypes.c_uint16,
        ctypes.POINTER(ctypes.c_uint16),
        ctypes.POINTER(ctypes.c_uint16)
    )

    dll.T32_Terminate.argtypes = (ctypes.c_int,)
    dll.T32_GetPracticeState.argtypes = (ctypes.POINTER(ctypes.c_int),)

    return dll


class Trace32API:
    """ Ctypes-based wrapper around useful Trace32 CAPI functions. Adds some
    argument management, standardized error-checking, etc. """
    # pylint: disable=invalid-name

    def __init__(self, libfile=None):
        if libfile is None:
            script_dir = os.path.abspath(os.path.dirname(__file__))
            libfile = os.path.join(script_dir, "_t32api.so")

        libfile = os.path.abspath(libfile)
        self.dll = ctypes.cdll.LoadLibrary(libfile)
        self.dll = _dll_init_generic(self.dll)

        self.dll.read_memory.restype = ctypes.c_int
        self.dll.read_memory.errcheck = confirm_success
        self.dll.read_memory.argtypes = (
            ctypes.c_size_t,
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_char),
            ctypes.c_int
        )

        self.dll.write_memory.argtypes = ()
        self.dll.write_memory.restype = ctypes.c_int
        self.dll.write_memory.errcheck = confirm_success
        self.dll.write_memory.argtypes = (
            ctypes.c_size_t,
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_char),
            ctypes.c_int
        )

    def T32_Config(self, key, value):
        """ Sets $key to $value in the trace32 DLL. Used for setting up
        communication parameters before calling T32_Start(). Known parameters
        include: NODE, PACKLEN, PORT, TIMEOUT, HOSTPORT. """

        key = key.upper()

        if key.endswith("="):
            key = key[:-1]

        if key not in ('NODE', 'PACKLEN', 'PORT', 'TIMEOUT', 'HOSTPORT'):
            raise ValueError(f"Invalid key '{key}' for T32_Config")

        self.dll.T32_Config(key + '=', value)

    def T32_Init(self):
        """ Initializes the driver and connects to Trace32. Should be
        done before calling T32_Attach (which in-turn is necessary before
        doing anything useful). """

        self.dll.T32_Init()

    def T32_Attach(self, device=AttachType.ICD):
        """ Attaches to an initialized T32 session. Should be called
        immediately after T32_Init(). """

        if device not in (x.value for x in AttachType):
            raise ValueError(f"Invalid device '{device}' for T32_Attach")

        self.dll.T32_Attach(int(device))

    def T32_Exit(self):
        """ Terminates the connection to Trace32 instance. Doesn't actually
        exit any programs, despite the name. """

        self.dll.T32_Exit()

    def T32_Cmd(self, command):
        """ Runs a TRACE32 command on the connected instance. DO commands will
        return immediately, and all other kinds of commands will block until
        they're completed. """

        self.dll.T32_Cmd(command)

    def T32_Nop(self):
        """ Runs a NOP command that checks communication with the Trace32
        instance. See also: T32_Ping. """

        self.dll.T32_Nop()
        return True

    def T32_Ping(self):
        """ Runs a PING command that checks communication with the Trace32
        instance. See also: T32_Nop. """

        self.dll.T32_Ping()
        return True

    def T32_GetMessageString(self):
        """ Retrieves a message-string created by a PRACTICE command. Returns
        the string, as well as any type-hints associated with it."""

        msg_type = ctypes.c_uint16(0)
        msg_len = ctypes.c_uint16(0)
        buffer = ctypes.create_string_buffer(2**16)
        self.dll.T32_GetMessageString(buffer, 2**16 - 1, msg_type, msg_len)

        msg_type = msg_type.value
        msg_len = msg_len.value

        if msg_type == 0:
            return {"msg": "", "types": (MessageType(0),)}

        if buffer[msg_len - 1:msg_len] == b'\x00':
            msg_len -= 1

        # pylint: disable=consider-using-generator
        types = tuple([x for x in MessageType if int(x.value) & msg_type])
        msg = buffer.value.decode("ascii")
        return {"msg": msg, "types": types}

    def T32_EvalGet(self):
        """ Retrieves a exit-code from an EVAL or a few other specific PRACTICE
        commands. """

        result = ctypes.c_uint32(-1)
        self.dll.T32_EvalGet(result)
        return result.value

    def T32_EvalGetString(self):
        """ Retrieves a pending message from the global buffer used by a few
        specific PRACTICE commands such as EVAL. There is potentially some
        overlap with messages reported on T32_GetMessageString. """

        buffer = ctypes.create_string_buffer(2**16)
        self.dll.T32_EvalGetString(buffer)
        return buffer.value.decode("ascii")

    def T32_GetPracticeState(self):
        """ Checks to see whether a PRACTICE script is currently running. """

        pstate = ctypes.c_int(-1)
        self.dll.T32_GetPracticeState(pstate)

        if pstate.value == -1:
            raise CallFailure("T32_GetPracticeState.pstate", pstate)

        return PracticeState(pstate.value)

    def T32_Terminate(self, exit_code=0):
        """ Shuts down the remote Trace32 instance. Used for asking the remote
        trace32 to exit. """

        self.dll.T32_Terminate(exit_code)

    def T32_ExecuteCommand(self, cmd):
        """ Executes a TRACE32 command. Returns a buffer containing the
        response message (if any). DO commands will return immediately, and all
        other kinds of commands will block until they're completed. """

        buffer = ctypes.create_string_buffer(2**16)
        call_failure = None

        try:
            self.dll.T32_ExecuteCommand(cmd, buffer, 2**16 - 1)
        except CallFailure as err:
            call_failure = err

        if call_failure:
            if call_failure.errcode != Errcode.T32_ERR_EXECUTECOMMAND_FAIL:
                raise call_failure

            raise CommandFailure(cmd, buffer.value.decode("ascii"))

        return buffer.value.decode("ascii")

    def T32_ExecuteFunction(self, expression):
        """ Evaluate a TRACE32 expression/command. Return the resulting
        buffer, as well as its reported result-type. """

        buff = ctypes.create_string_buffer(2**16)
        restype = ctypes.c_uint32(0)
        error = False
        try:
            self.dll.T32_ExecuteFunction(expression, buff, 2**16 - 1, restype)
        except CallFailure:
            error = True

        if error:
            result = buff.value.decode('latin-1')
            raise EvalError(result, expression)

        if restype.value not in (x.value for x in ResultType):
            err_msg = f"result-type [{restype}] from T32_ExecuteFunction"
            err_msg += " is unknown."
            raise ValueError(err_msg)

        buff = buff.value.decode("ascii")
        return {"msg": buff, "type": ResultType(restype.value)}

    def T32_Stop(self):
        """ Stop a currently-running PRACTICE script. """

        self.dll.T32_Stop()

    def T32_ResetCPU(self):
        """ Reset the connected CPU. Effectively equivalent to running
        SYStem.UP and Register.RESet. """

        self.dll.T32_ResetCPU()

    def T32_Break(self):
        """ Break/halt the connected CPU.  """

        self.dll.T32_Break()


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

    def connect(self, node="localhost", port=20000, packlen=None, timeout=10):
        """ Connect to a Trace32 instance. """

        self.node = node
        self.port = port
        self.packlen = packlen
        self.api.T32_Config("NODE=", node)
        self.api.T32_Config("PORT=", port)

        if packlen:
            self.api.T32_Config("PACKLEN=", packlen)

        init_ok = False
        maxtime = time.time() + timeout

        while time.time() < maxtime:
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

    def run_scriptfile(self, scriptfile, logfile=None):
        """ Run a PRACTICE script that exists on the filesystem. """
        # pylint: disable=too-many-locals

        buffer = ""
        script = open(scriptfile).read().strip()
        lines = re.sub("^[ \t]*;.*?$", "", script, flags=re.M).splitlines()
        lines = [x.strip() for x in lines]
        lines = [x for x in lines if x]

        if not lines[-1].startswith("ENDDO"):
            err_msg = "Error: %s is missing final ENDDO statement."
            raise ValueError(err_msg % scriptfile)

        msgline_flag = self.clear_area()
        self.api.T32_ExecuteCommand(f"DO {os.path.abspath(scriptfile)}")

        # A background task is used to poll Trace32 and wait until the script
        # exits. This allows us to continue retrieving FIFO data while the
        # script runs, and is necessary because some Trace32 operations can
        # block its ability to respond to API calls.

        # To accomplish this, the main API is shut down with T32_Exit() so that
        # it's available to the background task. Then, it's re-initialized
        # after the background task is completed.

        self.api.T32_Exit()
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
        self.api.T32_Config("NODE=", self.node)
        self.api.T32_Config("PORT=", self.port)

        if self.packlen:
            self.api.T32_Config("PACKLEN=", self.packlen)

        self.api.T32_Init()
        self.api.T32_Ping()

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
                raise ScriptFailure(script, message_string)

        return buffer

    def run_script(self, script, logfile=None):
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
            result = self.run_scriptfile(outfile.name, logfile)

        return result

    def run_command(self, cmd, logfile=None):
        """ Run a single command and return the result. Optionally, also write
        the result to a logfile as its received. """

        self.clear_area()
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


def _main():
    iface = Trace32Interface()
    iface.connect(port=30000)
    iface.ping()
    iface.disconnect()
    print("Connection test OK.")


if __name__ == "__main__":
    _main()
