/* *********************************************************************************************
 * @Title: Sample program to execute TRACE32 commands from a system shell.
 * @Description:
 * This application creates a connection to a TRACE32 PowerView instance and sends a
 * TRACE32 command to that PowerView instance for execution.
 *
 * By default the port on which TRACE32 PowerView listens for API connections is 20000.
 * Optionally the port can be send with the port=<n> parameter.
 * The port number must match with the definition in config.t32 of the PowerView instance you
 * want to receive the command
 *.
 * The optional parameter wait=<ms> will cause t32rem to wait (after sending its command) until
 * no more PRACTICE scripts are running in TRACE32 - or the given timeout elapses. Without the
 * parameter wait=<ms>, t32rem will not wait until all PRACTICE	scripts stop running.
 *
 * A binary of this sample can be found in <t32>/bin/<os>/t32rem[.exe]
 *
 * Syntax:  t32rem <hostname or ip-address> [port=<number>] [wait=<ms>] <command>
 *
 * Example1: Set a breakpoint on main():
 *           t32rem  localhost  port=20000  Break.Set main
 *
 * Example2: Open the Break.List window:
 *           t32rem  localhost  port=20000  Break.List
 *
 * Example3: Start a PRACTICE script and waits up to 5000.ms until it stops:
 *           t32rem  localhost  port=20000  wait=5000  DO ~~/demo/practice/pcmd.cmm
 *
 * Return values:
 *   0  OK
 *   1  Error accessing TRACE32.
 *   2  Failed to connect to TRACE32. (No TRACE32 with an open API port at that socket)
 *   3  Invalid input. (Invalid ip-address/hostname/port or too long command)
 *   4  Timeout while waiting for PRACTICE scripts to stop running.
 *
 * $Id: t32rem.c 125610 2020-09-04 10:22:33Z kjmal $
 * $LastChangedRevision: 125610 $
 * $LastChangedBy: kjmal $
 *
 * @Copyright: (C) 1989-2020 Lauterbach GmbH, licensed for use with TRACE32(R) only
 * *********************************************************************************************
 * $Id: t32rem.c 125610 2020-09-04 10:22:33Z kjmal $
 */


#if defined(_MSC_VER)
# pragma warning( push )
# pragma warning( disable : 4255 4005)
# include <stdio.h>
# include <stdlib.h>
# include <string.h>
# include <Windows.h>
# pragma warning( pop )
# define strncasecmp(S1,S2,N)  _strnicmp((S1), (S2), (N))
#else
# ifdef __linux__
/* for usleep() declaration */
#  define _BSD_SOURCE
# endif
# include <stdio.h>
# include <stdlib.h>
# include <string.h>
# include <strings.h>
# include <unistd.h>
# include <sys/time.h>
# define Sleep(t)  usleep((t)*1000)
#endif
#include "t32.h"


#if !defined(_MSC_VER)
static uint32_t GetTickCount(void)
{
	struct timeval now;
	if ( gettimeofday( &now, NULL ) == -1 )
		return 0;
	return (now.tv_sec*1000 + now.tv_usec/1000);
}
#endif


int main(int argc, char **argp)
{
	typedef enum { RESULT_OK = 0, RESULT_NOACCESS, RESULT_NOCONNECTION, RESULT_INVALIDINPUT, RESULT_TIMEOUT} result_t;

	int                argn = 2;
	char               cmd[2048];
	uint16_t           msgMode, msgLen;
	unsigned long int  wait = 0;
	result_t           result = RESULT_OK;

	if ( argc < 2 ) {
		printf( "Usage: t32rem <host> [port=<n>] [wait=<ms>] <cmd>\n" );
		printf( "Send a TRACE32 command to a running TRACE32 PowerView instance.\n");
		printf( "The receiving TRACE32 instance needs to have an enabled API port.\n\n");
		printf( "  <host>    IP address or hostname of the machine running the receiving TRACE32.\n");
		printf( "  port=<n>  API port opened on the receiving TRACE32 (Default ist 20000)\n");
		printf( "  wait=<ms> Wait up to the given milliseconds until all PRACTICE scripts on the\n"
		        "            receiving TRACE32 stop, after sending  the command. This is useful in\n"
		        "            combination with a command starting a PRACTICE script like \"run\" or\n"
		        "            \"do\". Without this option t32rem will not wait for scripts to end.\n");
		exit(RESULT_INVALIDINPUT);
	}

	if ( T32_Config( "NODE=", argp[1] ) == -1 ) {
		printf( "hostname %s not accepted\n", argp[1] );
		exit(RESULT_INVALIDINPUT);
	}

	if ( argc >= 3  &&  !strncasecmp(argp[2],"port=", 5)) {
		if ( T32_Config( "PORT=", argp[2]+5 ) == -1 ) {
			printf( "port number %s not accepted\n", argp[2] );
			exit(RESULT_INVALIDINPUT);
		}
		argn++;
	}

	if ( argc >= argn + 1  &&  !strncasecmp(argp[argn],"wait=", 5)) {
		wait = strtoul(argp[argn] + 5, NULL, 10);
		argn++;
	}

	strcpy( cmd, "" );
	while ( argn < argc ) {
		if ( (strlen(cmd)+strlen(argp[argn])+1) > (sizeof(cmd)-1) ) {
			printf( "actual command line exceeds maximum internal bufferlength of %d\n", (int)sizeof(cmd)-1 );
			exit(RESULT_INVALIDINPUT);
		}
		strcat( cmd, argp[argn] );
		strcat( cmd, " " );
		argn++;
	}

	if ( T32_Init() != T32_OK ) {
		printf( "error initializing TRACE32\n" );
		exit(RESULT_NOCONNECTION);
	}

	if (T32_Attach(1) != T32_OK) {
		printf("error no device\n");
		exit(RESULT_NOCONNECTION);
	}

	if ( T32_Nop() != T32_OK )
		goto error;

	T32_Stop();
	if (T32_Errno != T32_OK  &&  T32_Errno != 1)
		goto error;

	if ( T32_Cmd( cmd ) != T32_OK )
		goto error;

	if (wait){
		uint32_t  start, end, now;
		int       pstate;

		start = GetTickCount();
		end = start + wait;
		while (T32_GetPracticeState(&pstate) == T32_OK  &&  pstate != 0){
			now = GetTickCount();
			if (now >= end  &&  (end >= start  ||  now <= start)){
				result = RESULT_TIMEOUT;
				break;
			}
			Sleep(1);
		}
	}

	if ( T32_GetMessageString( cmd, (uint16_t)sizeof(cmd), &msgMode, &msgLen) != T32_OK )
		goto error;

	printf( "command returned ");
	if (msgMode & 1)
		printf ("General Information, ");
	if (msgMode & 2)
		printf ("Error, ");
	if (msgMode & 8)
		printf ("Status Information, ");
	if (msgMode & 16)
		printf ("Error Information, ");
	if (msgMode & 32)
		printf ("Temporary Display, ");
	if (msgMode & 64)
		printf ("Temporary Information, ");
	if (msgMode & 128)
		printf ("Empty, ");

	printf ("message: %s\n", cmd);

	T32_Exit();
	return result;


error:
	printf( "error accessing TRACE32\n" );
	T32_Exit();
	return RESULT_NOACCESS;
}


