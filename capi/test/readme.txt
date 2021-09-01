; --------------------------------------------------------------------------------
; @Title: TRACE32 Remote API - README
; @Description: Readme file for TRACE32 Remote API
; @Author: MOB
; @Copyright: (C) 1989-2020 Lauterbach GmbH, licensed for use with TRACE32(R) only
; --------------------------------------------------------------------------------
; $Id: readme.txt 125719 2020-09-08 14:29:16Z irohloff $

TRACE32 Remote-API



t32apicmd:     This demo sends a single, user specified command to PowerView and
               displays any AREA message.
               Usage:  t32apicmd [node=<name_or_IP>] [port=<num>] <cmd>

t32apimenu:    This demo offers a menu for selection of various API commands.
               PowerView is configured accordingly via remote connection. Whether
               the user has started PowerView for accessing real hardware or in
               simulator mode is also detected. For accessing real hardware the
               location of the data memory can be specified by <hexaddr>.
               Usage:  t32apimenu [node=<name_or_IP>] [port=<num>] [<hexaddr>]

t32apinotify:  This demo receives notifications from PowerView. PowerView is
               configured accordingly via remote connection. Whether the user has
               started PowerView for accessing real hardware or in simulator mode
               is also detected.
               Syntax:  t32apinotify [node=<name_or_IP>] [port=<num>]

t32fdxhost:    Host of the FDX feature demontration. See demo/<arch>/fdx for
               the target implementation of FDX. The FDX demos can be executed
               in the TRACE32 instruction set simulator.
               Usage (example with PowerPC Simulator):
               1. Start TRACE32 PowerPC simulator with API enabled
               2. In TRACE32, execute
                     CD.RUN demo/powerpc/fdx/fdx.cmm
               3. from command shell, run t32fdxhost (t32fdxhost <host> [port=<n>])
               4. In TRACE32, execute "GO" (start application in simulator).


If you compile the applications with support for Remote-API via TCP, 
the executables are prefixed with "tcp_"; so:
  tcp_t32apicmd
  tcp_t32apimenu
  tcp_t32apinotify
  tcp_t32fdxhost



Build instructions
------------------

Windows, Visual Studio
^^^^^^^^^^^^^^^^^^^^^^
Start a "Native Tools Command Prompt" from the Windows "Start" menu.
Change directory to ...\demo\api\capi\test
Then execute
   nmake
to compile the applications.

To compile and link the applications with Remote-API via TCP, execute
   nmake NETTCP=1

To compile a version with debug information, add a DEBUG=1 to the command line. E.g.:
   nmake DEBUG=1
   nmake DEBUG=1 NETTCP=1

Linux, GCC
^^^^^^^^^^
Start a command shell.
Change directory to .../demo/api/capi/test
Execute
  make
to compile the applications

To compile and link the applications with Remote-API via TCP, execute
   make NETTCP=1

To compile a version with debug information, add a DEBUG=1 to the command line. E.g.:
   nmake DEBUG=1
   nmake DEBUG=1 NETTCP=1
