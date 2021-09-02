# Introduction #

Standalone CLI tool for using Lauterbach TRACE32 in an automation-friendly
way. Can be used to launch PRACTICE scripts from the command-line, to run
single TRACE32 commands, or to read/write from a device's memory. Other
functionality might be added in future releases.

This tool is the spiritual successor to `t32-ctl`, which was bundled with
early versions of the
[Dune HAPS Firmware](https://github.com/cruise-automation/dune-haps-firmware)
repo.

## Use Case ##

TRACE32 is very powerful program, and a great GUI tool to use. But it's very
hard to control from a shell script, Makefile, CI tool, etc. This limits its
usefulness for tasks like "load a bootloader onto every Dune board" or "put an
initramfs on every HAPS system".

`Trace32-cli` solves this problem by providing an easy way to run PRACTICE
scripts from the command-line, and to directly read/write from a device's
memory. It deals with all aspects of the task, including configuring/launching
TRACE32.

## How It Works ##

`Trace32-cli` launches a headless instance of TRACE32 (your choice of target),
and then uses Lauterbach's C-API to interact with it over a local TCP/IP port.
Command and control is done mostly through the API, and text output is
retrieved through a pipe.

After launching TRACE32, `trace32-cli` does whatever you've requested and then
shuts down the TRACE32 instance automatically.

# Usage #

`Trace32-cli` currently supports three subcommands, with several others planned
for future implementation.

The currently implemented commands are:
 - `run`: Run a PRACTICE script or a single TRACE32 command.
 - `read`: Read from a block of memory on the target device.
 - `write`: Write to a block of memory on the target device.

## Common Options ##

These options can be found on all subcommands:
 - `-H`/`--header <somefile.cmm>`: Run `<somefile.cmm>` before running the
   subcommand. Intended for tasks like initializing/configuring a JTAG link.
   Can be specified multiple times.
 - `-F`/`--footer <somefile.cmm>`: Run `<somefile.cmm>` after running the
   subcommand. Intended for tasks like bringing the CPU out of reset. Can be
   specified multiple times.
 - `-u`/`--usb-reset`: Use `t32usbchecker` to reset a USB-connected debug probe.
   Can be used to recover the USB probe if TRACE32 was terminated unexpectedly.
 - `-p`/`--protocol` <protocol>: Choose the connection mode between TRACE32 and
   the debugger. Currently supports `usb` and `sim`. Other modes might be
   added later.
 - `-t`/`--t32bin` <trace32bin>: Choose the TRACE32 executable that gets
    launched. This is used to select the target architecture, because TRACE32
    ships different binaries for each target architecture.
 - `-v`/`--verbose`: Be verbose. Specify multiple times for more verbosity.

## `Read` Options ##
 - `-b`/`--blocksize <blocksize>`: Maximum size (in bytes) to use for each
   internal read operation. Defaults to 1MB.
 - `-o`/`--outfile <outfile>`: Output file to write. If unspecified, data will
   be written to stdout.
 - `-c`/`--count <size>`: Read <size> number of bytes from the target. This
   is required unless `-r`/`--reference` is used.
 - `-r`/`--reference <filename>`: Get the size of `<filename>` and read that
   many bytes from the target. This is required unless `-c`/`--count` is used.

## `Write` Options ##
 - `-b`/`--blocksize <blocksize>`: Maximum size (in bytes) to use for each
   internal write operation. Defaults to 1MB.
 - `-s`/`--spaddress <address>`: Address to use for 64kB scratchpad region, if
   using `checksum`-based write verification (see below).
 - `-c`/`--check <mode>`: Mode to use for checking that data was written to
   target correctly. Possible values are:
    - `full`: Read back each block, and confirm that it has the correct value.
      Best (and slowest) option.
    - `checksum`: Use TRACE32's `Data.LOAD /CHECKLOAD` mode to write and
      verify each block.  Checksum is calculated on-target using a temporary
      program that TRACE32 creates. Requires 64kB of scratchpad memory
      (specified with `-s`/`--scratchpad`) to hold the checksum program. Faster
      than `full`, but not as safe.
    - `sparse`: Use TRACE32's `Data.LOAD /PVerify` mode to write each block and
      verify 1/16th of the writes. Faster than `checksum` but provides minimal
      protection against corrupted writes.
    - `none`: Don't verify data after writing. Fastest and least-safe option.

## `Run` Options ##
 - `-c`/`--command`: Run a standalone PRACTICE command instead of a `.cmm`
   script.

# Examples #

## `Run` Examples

 - Run `somefile.cmm` after connecting to the target device:
   ```
   $ trace32-cli run somefile.cmm
   ```

 - Same as above, but run `header.cmm` first:
   ```
   $ trace32-cli -H header.cmm run somefile.cmm
   ```

 - Same as above, but reset the USB debugger before launching TRACE32:
   ```
   $ trace32-cli -u -H header.cmm run somefile.cmm
   ```

 - Same as above, but be very verbose:
   ```
   $ trace32-cli -uvvv -H header.cmm run somefile.cmm
   ```

## `Read` Examples

 - Read an 4MB block of memory from the address `0x78000000` on the target.
   Reset the USB debugger before launching TRACE32, and run `header.cmm` before
   the `read` operation. Store the result as `readback.bin`:
   ```
   $ trace32-cli -u -H header.cmm read 0x78000000 -c4M -o readback.bin
   ```
   or:
   ```
   $ trace32-cli -u -H header.cmm read 0x78000000 -c4M  >readback.bin
   ```

 - Read back a file from memory, and check to see if it's the same as a local
   copy:
   ```
   $ trace32-cli -u -H header.cmm read 0x78000000 -r reference.bin -o readback.bin
   $ diff reference.bin readback.bin
   ```

## `Write` Examples

 - Write `bootloader.bin` to address `0x78000000` on the target with
   checksum-based verification, using a scratchpad placed at `0x7300000`:

   ```
   $ trace32-cli -u -H header.cmm write --check=checksum --scratchpad=0x73000000 0x78000000 bootloader.bin
   ```
   or:
   ```
   $ cat bootloader.bin | trace32-cli -u -H header.cmm write --check=checksum --scratchpad=0x73000000 0x78000000
   ```
# Build Instructions #

`Trace32-cli` is packaged as a standard Python package with binary extensions
for the C API. To compile, you need `python3-setuptools` and `python3-wheel`
installed on your system. To compile it into a Python wheel, clone the repo and
run:

```
python3 setup.py bdist_wheel
```

and the resulting wheel will be placed in `dist/`. Standard cross-compilation
techniques should also work, although this hasn't been tested.

By default, the wheel's version number is set by the contents of the `VERSION`
file. The current Git commit-hash and `dirty` or `clean` will be appended to
the version number.

To make a releasable build, set `RELEASE` environment variable is set to `1`
before compiling the wheel. If the Git repo is clean (no uncommitted changes or
untracked files), the version number won't include any Git metadata.

## Maintainer Instructions ##

There's a `maintainer.mk` Makefile that has some extra targets that might be
useful for a maintainer. These include:
 - `hotwire`: Configure the package for direct use, without compiling to
   a wheel or installing it anywhere. After running this target, you can use
   `trace32-cli.py` in-place with no further effort.

  - `download`: Download a C API zip-file from Lauterbach's website.
  - `unpack`: Unpack the C API into `capi/`, replacing whatever version
    was already there. Prune anything that isn't source-code, and unixify
    all extracted files.


# Current Status #

At the time of this writing, `trace32-cli`'s initial design is complete. Some
bugs will probably get found as the tool starts to get more widely used.

The following features are currently planned for a future release:
 - `gdb` mode, which will launch TRACE32 and start a `gdb` front-end.
 - `serve` mode, which will act like the RCL back-end for other TRACE32 tools.
 - An Ethernet-based debugger `protocol` mode (right now, `trace32-cli` only
   supports USB-connected debuggers).
