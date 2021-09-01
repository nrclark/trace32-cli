; --------------------------------------------------------------------------------
; @Title: Information on the TRACE32 Remote API C Interface
; @Description: -
; @Author: DIE
; @Copyright: (C) 1989-2020 Lauterbach GmbH, licensed for use with TRACE32(R) only
; --------------------------------------------------------------------------------
; $Id: readme.txt 125610 2020-09-04 10:22:33Z kjmal $

/* $LastChangedRevision: 125610 $ */


 Table of contents:

  1) File listing of source and demo directories

  2) Prerequisites for using the TRACE32 Remote API

  3) Usage of the demo applications

 1) FILE LISTING OF SOURCE AND DEMO DIRECTORIES:

     /src
      t32.h             header file of the TRACE32 Remote API
      hremote.c         source file providing the interface functions
      hlinknet.c        source file realizing the UDP socket communication

      tcpsimple2.c      source and header files that contain and handle the TCP socket communication.
      tcpsimple2.h 
      t32nettcp.c 
      t32nettcp.h

     /dll
      makefile          NMAKE makefile for building Remote API DLL
      makefile.linux    makefile for building Remote API libraries for Linux
      makefile.macos    makefile for building Remote API library for MacOS
      t32api.c          source file for building Remote API dll/lib/exp-files

      t32api.dll        32bit TRACE32 Remote API dynamic link library (Windows)
      t32api.lib        32bit TRACE32 Remote API import library (Windows)
      t32api.exp        32bit TRACE32 Remote API export file (Windows)
      t32api64.dll      64bit TRACE32 Remote API dynamic link library (Windows)
      t32api64.lib      64bit TRACE32 Remote API import library (Windows)
      t32api64.exp      64bit TRACE32 Remote API export file (Windows)

      t32api.so         32bit TRACE32 Remote API shared object file (Linux)
      t32api64.so       64bit TRACE32 Remote API Linux shared object file (Linux)

      t32api.dylib      32bit TRACE32 Remote API shared library (MacOS)

     /test
      makefile          NMAKE makefile for building the various demos
      t32apicmd.c       demo source for sending a user specified command to TRACE32
      t32apicmd.exe     ready to use dos shell application
      t32apinotify.c    demo source for receiving notifications from TRACE32
      t32apinotify.exe  ready to use dos shell application
      t32apimenu.c      demo source offering various Remote API commands
      t32apimenu.exe    ready to use dos shell application
      t32bundle.c       demo source illustrating the Memory Bundle Transfer
      t32dllmenu.c      demo source offering various 32bit dll Remote API commands
      t32dllmenu.exe    ready to use dos shell application
      t32fdxhost.c      source of fast data exchange demo
      t32fdxhost.exe    ready to use dos shell application
      t32notification.c demo source for using notifications in CAPI
      t32rem.c          demo source to execute TRACE32 commands from a system shell
      t32remotedo.c     demo source to execute TRACE32 commands from a system shell with additional command line options
      t32remtest.c      demo source presenting a menu for sending various API command

     /dlltest
      hrtestdll.c 
      makedlltest.bat
      t32testdll.exe


 2) PREREQUISITES FOR USING THE TRACE32 REMOTE API

     All important information about the TRACE32 Remote API can be found in
     the TRACE32 Remote API manual "api_remote_c.pdf" which is located in the
     pdf-directory of the TRACE32 PowerView installation.

     In order to establish a remote connection TRACE32 PowerView has to be
     started with an enabled API port. If T32start is used for start up the
     "Advanced Settings > Interfaces > API Port" settings have to be adapted,
     otherwise the configuration file "config.t32" has to contain these lines:

       RCL=NETTCP
       PORT=20000

     In case this default port value is changed any custom C program has to
     call T32_Config() for specifying the modified value. A modified port
     value may be passed to the dos shell demos via command line argument.



 3) USAGE OF THE DEMO APPLICATIONS

     t32apicmd:          This demo sends a single, user specified command to PowerView and
                         displays any AREA message.

                         Syntax:  t32apicmd [node=<name_or_IP>] [port=<num>] <cmd>
                         Example: t32apicmd  node=localhost port=20000 PRINT VERSION.BUILD()

     t32apinotify:       This demo receives notifications from PowerView. PowerView is
                         configured accordingly via remote connection. Whether the user has
                         started PowerView for accessing real hardware or in simulator mode
                         is also detected.

                         Syntax:  t32apinotify [node=<name_or_IP>] [port=<num>]
                         Example: t32apinotify  node=localhost      port=20000

     t32apimenu:         This demo offers a menu for selection of various API commands.
                         PowerView is configured accordingly via remote connection. Whether
                         the user has started PowerView for accessing real hardware or in
                         simulator mode is also detected. For accessing real hardware the
                         location of the data memory can be specified by <hexaddr>.

                         Syntax:  t32apimenu [node=<name_or_IP>] [port=<num>] [<hexaddr>]
                         Example: t32apimenu  node=localhost      port=20000   0x400C000

     t32bundle:          This demo illustrates the usage of the Memory Bundle Transfer function.

     t32dllmenu:         Same as "t32apimenu" but uses 32bit dll for command execution.

     t32fdxhost:         Host of the FDX feature demonstration. See demo/<arch>/fdx for the
                         target implementation of FDX. The FDX demos can be executed in the
                         TRACE32 instruction set simulator. Usage:
                         1. start simulator with API enabled
                         2. run fdx.cmm
                         3. run fdxhost (fdxhost <host> [port=<n>])
                         4. run (Go) application in simulator

     t32notifications:   Sample program illustrating the use of notifications in the CAPI.

                         Syntax:  t32notifications  node=<name_or_IP>  [port=<num>]
                         Example: t32notifications  node=localhost      port=20010

     t32rem:             Sample program to execute TRACE32 commands from a system shell.

                         Syntax:  t32rem <hostname or ip-address> [port=<number>] [wait=<ms>] <command>
                         Example: t32rem  localhost  port=20000  wait=5000  DO ~~/demo/practice/pcmd.cmm

     t32remotedo:        Sample program to execute TRACE32 commands from a system shell with additional command line options.

                         Syntax:  t32remotedo [--help] [--node=<hostname>] [packlen=<number>] [--port=<number>] [--verbose] <command>
                         Example: t32remotedo --port=10000 --verbose Data.Set P:0x1000 0x22


     t32remtest:         Sample program presenting a menu for sending various API command.

                         Syntax:  t32remtest [<ip-address> | <hostname>] [port=<number>]
                         Example: t32remtest localhost port=10000


