@echo off
:TRY1
if not exist C:\VS6\nul goto TRY2
set L_MSDEV=C:\VS6\MSDev98\Bin
set L_VC=C:\MVS6\VC98
goto COMPILE

:TRY2
set L_MSDEV=C:\DevTools\Microsoft Visual Studio\Common\MSDev98\Bin
set L_VC=C:\DevTools\Microsoft Visual Studio\VC98
goto COMPILE

:COMPILE
set MAKEFLAGS=
set PATH=.;%L_MSDEV%
set MSDIR=%L_VC%
set INCDIR="%MSDIR%\Include"
set LIBDIR="%MSDIR%\Lib"
set MCC="%MSDIR%\bin\cl"
set MLINK="%MSDIR%\bin\link" /LIBPATH:$(LIBDIR) /OUT:$@

%MCC% /D "T32HOST_WIN" /I %INCDIR% /I "..\src" /c hrtestdll.c
%MLINK% /LIBPATH:%LIBDIR% /OUT:"t32testdll.exe" hrtestdll.obj ..\dll\t32api.lib
