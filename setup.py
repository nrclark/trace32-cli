#!/usr/bin/env python3

import re
import ast
import textwrap
import os
import sys

from setuptools import setup
from setuptools import Extension

from setuptools.command.build_py import build_py
from setuptools.command.build_ext import build_ext

from subprocess import check_output

#------------------------------------------------------------------------------#


def calculate_version():
    """ Calculate the version-number based on VERSION and the repo's
    Git status."""

    version = open('VERSION').read().strip()
    release = os.environ.get('RELEASE', '0').strip() not in ("0", "")

    result = check_output(["git", "status", "--porcelain"])
    git_dirty = result.decode().strip() != ""

    if release and not git_dirty:
        return version

    result = check_output(["git", "rev-parse", "--short", "HEAD"])
    shorthash = result.decode().strip()

    version += f"+{shorthash}.{'dirty' if git_dirty else 'clean'}"
    return version


def generate_errfile(header_file="capi/src/t32.h",
                     output_file="trace32_cli/t32api_errors.py",
                     dry_run = False):

    """ Parses TRACE32's C-API header file (t32.h) for errcodes, and generates
    a Python enum that holds the errcodes. Creates a Python source file that
    holds the enum and a docstring. """

    with open(header_file) as infile:
        data = infile.read().strip()

    lines = [re.sub("//.*", "", x) for x in data.splitlines()]
    lines = [re.sub("/[*].*?[*]/", "", x) for x in lines]
    lines = [x.strip() for x in lines]

    regex = re.compile("[#][ \t]*define[ \t]*(T32_ERR[^ \t]*)[ \t]+(.*)")

    errors = []

    for x in lines:
        match = re.match(regex, x)
        if match:
            groups = match.groups()
            name = groups[0]
            value = ast.literal_eval(groups[1])
            errors.append((name, value))

    errors = sorted(errors, key=lambda x: x[1])
    assert len(errors) >= 1
    errors.insert(0, ("OK", 0))

    file_docstring = """Auto-generated errcode enum. The various values of
    Errcode are appended to this file by the build process, based on values
    pulled out from t32.h."""

    enum_docstring = """Error-codes returned by various functions. Parsed
    automatically from the CAPI's t32.h file."""

    file_docstring = re.sub("[ \t\n]+", " ", file_docstring)
    enum_docstring = re.sub("[ \t\n]+", " ", enum_docstring)
    file_docstring = '""" ' + file_docstring + ' """'
    enum_docstring = '""" ' + enum_docstring + ' """'

    file_docstring = textwrap.fill(file_docstring, width=79) + "\n"
    enum_docstring = textwrap.fill(enum_docstring, width=75,
                                   subsequent_indent='    ') + "\n"

    template = """
        #!/usr/bin/env python3
        @file_docstring@

        import enum


        class Errcode(enum.IntEnum):
            @enum_docstring@
            @enum_codes@
    """

    result = re.sub("^(    ){2}","", template.strip() + "\n", flags=re.M)
    result = result.replace("@file_docstring@", file_docstring)
    result = result.replace("@enum_docstring@", enum_docstring)

    enum_lines = [f"{x[0]} = {x[1]}" for x in errors]
    result = result.replace("@enum_codes@", "\n    ".join(enum_lines))

    exec(result)

    if not dry_run:
        with open(output_file, "w") as outfile:
            outfile.write(result)


#------------------------------------------------------------------------------#


class prebuild_files(build_py):
    """ Subclass of build_py that pre-generates VERSION and t32api_errors.py
    based on #defines from t32.h before running the actual builder."""

    def run(self):
        target_dir = os.path.join(self.build_lib, 'trace32_cli')
        version = calculate_version()

        if not self.dry_run:
            self.mkpath(target_dir)
            print("Generating VERSION.")
            with open(os.path.join(target_dir, 'VERSION'), 'w') as outfile:
                outfile.write(version + "\n")

        script_dir = os.path.abspath(os.path.dirname(__file__))
        input_file = os.path.join(script_dir, "capi", "src", "t32.h")
        output_file = os.path.join(target_dir, "t32api_errors.py")
        print("Generating t32api_errors.py from t32.h.")
        generate_errfile(input_file, output_file, self.dry_run)

        return super().run()


class update_libnames(build_ext):
    """ Subclass of build_ext that replaces reference shared-library
    filenames in Python sources with the actual names of the generated
    extension files. """

    def run(self):
        result = super().run()
        ext_map = {}

        for extension in self.extensions:
            # Author's note: at the time of this writing, setuptools' build_ext
            # puts a duplicate copy of each extension in the Python base
            # directory when generating an .tar.gz distribution (but not when
            # generating a wheel). This fix removes the duplicates without
            # perturbing the originals.

            extfile = self.get_ext_filename(extension.name)
            in_subdir = bool(os.path.dirname(extfile))

            if in_subdir:
                extfile = os.path.basename(extfile)
                root_file = os.path.join(self.build_lib, extfile)
                if os.path.exists(root_file):
                    os.unlink(root_file)

        for extension in self.extensions:
            reference = re.search('[^.]+$', extension.name).group(0)
            actual = os.path.basename(self.get_ext_filename(extension.name))

            ext_map[extension.name] = {
                "reference": f"{reference}.so",
                "actual": actual
            }

        python_files = []
        for root, _, files in os.walk(self.build_lib):
            for file in files:
                if file.lower().endswith(".py"):
                    python_files.append(os.path.join(root, file))

        for filename in python_files:
            with open(filename, 'r') as infile:
                data = infile.read()

            for key in ext_map:
                item = ext_map[key]
                data = data.replace(item['reference'], item['actual'])

            with open(filename, 'w') as outfile:
                outfile.write(data)

        return result


#------------------------------------------------------------------------------#


if __name__ == "__main__":
    if hasattr(sys, 'getwindowsversion'):
        extra_sources = [os.path.join('capi', 'dll', 't32api.c')]
    else:
        extra_sources = []

    setup(
        version=calculate_version(),
        cmdclass={'build_py': prebuild_files,
                  'build_ext': update_libnames},
        ext_modules = [
            Extension('trace32_cli._t32api',
                include_dirs = [os.path.join('capi', 'src')],
                sources = [
                    'rw_assist.c',
                    os.path.join('capi', 'src', 'hremote.c'),
                    os.path.join('capi', 'src', 't32nettcp.c'),
                    os.path.join('capi', 'src', 'tcpsimple2.c')
                ] + extra_sources
            )
        ],
    )
