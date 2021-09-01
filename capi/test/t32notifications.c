/* *********************************************************************************************
 * @Title: Sample program illustrating the use of notifications in the CAPI.
 * @Description:
 * Sample program illustrating the use of notifications in the CAPI.
 *
 * used -DENABLE_NOTIFICATION option to compile _all_ source files
 *
 * $Id: t32notifications.c 125610 2020-09-04 10:22:33Z kjmal $
 * $LastChangedRevision: 125610 $
 * $LastChangedBy: kjmal $
 *
 *
 * @Copyright: (C) 1989-2020 Lauterbach GmbH, licensed for use with TRACE32(R) only
 * *********************************************************************************************
 * $Id: t32notifications.c 125610 2020-09-04 10:22:33Z kjmal $
 */

#if defined(_MSC_VER)
# pragma warning( push )
# pragma warning( disable : 4255 )
# include "t32.h"
# pragma warning( pop )
#else
# include "t32.h"
#endif

#include "stdio.h"
#include "conio.h"
#include <time.h>
#include "stdlib.h"
#include <string.h>


static void T32_callbackEditExtern(int dummy, int lineNr, char *fileName);
static void T32_callbackBreakpointConfig(int dummy);
static void T32_callbackBreak(int dummy);

int main(int argc, char ** argp)
{
	int retries = 0;
	int argn;

retryit:
		retries++;

	if ( argc < 2 ) {
		printf( "usage: t32notifications <host> [port=<n>]\n" );
		exit(2);
	}
	if ( T32_Config( "NODE=", argp[1] ) == -1 )     {
		printf( "hostname %s not accepted\n", argp[1] );
		exit(2);
	}
	argn = 2;
	if ( argc >= 3 && ((!strncmp(argp[2],"port=", 5)) || (!strncmp(argp[2],"PORT=", 5)))) {
		if ( T32_Config( "PORT=", argp[2]+5 ) == -1 ) {
			printf( "port number %s not accepted\n", argp[2] );
			exit(2);
		}
		argn++;
	}

	if (T32_Init() == -1) {
		printf("Error initializing API.\n");
		T32_Exit();
		if (retries < 2)
			goto retryit;
		return 2;
	}

	/* When attach fails, we close a (potentially) existing connection and retry */
	if (T32_Attach(T32_DEV_ICD) != 0) {

		T32_Exit();
		T32_Init();

			if (T32_Attach(T32_DEV_ICD) != 0) {
				printf("Failure to connecting to TRACE32. Terminating.\n");
			return 1;
		}
	}

	/* Tell TRACE32 to report user request for editing source via edit.external command. */
	T32_NotifyStateEnable( T32_E_EDIT, (void (__cdecl *)(void)) T32_callbackEditExtern);

	/* Tell TRACE32 to report changes in breakpoint configuration. */
	T32_NotifyStateEnable( T32_E_BREAKPOINTCONFIG, (void (__cdecl *)(void)) T32_callbackBreakpointConfig);

	/* Tell TRACE32 to report when target program stops execution. */
	T32_NotifyStateEnable( T32_E_BREAK, (void (__cdecl *)(void)) T32_callbackBreak);


	while (1) {

		uint32_t pc;
		T32_ReadPP( &pc); /* creates some traffic and shows that API connection is alive */
		printf("PC=%d\n", (int)pc);

		/* Poll for notifications; If needed invokes previously registered callback handler */
		T32_CheckStateNotify (0x0 /* dummy parameter */);

		/* press <Q><return> to exit the application */
		if (_kbhit()) {
			int ch;
			do {ch = getchar(); } while (ch == '\n');
			if (ch == 'Q' || ch == 'q')
				break;

		} else {
			_sleep( 200 );  /* Windows-specific; adapt for your platform */
		}

	}

	T32_Exit();

	return 0;
}



/* Callback handler invoked when TRACE32 reports edit.external commands.
 * @param dummy: unused in this sample, is taken from T32_Check StateNotify() call.
 * @param lineNr to place the cursor
 * @param fileName of file to edit
 */
static void T32_callbackEditExtern(int dummy, int lineNr, char *fileName) {

		/* Application may open editor window */
	printf("TRACE32: edit.extern request with lineNr=%d, fileName=%s\n\n", lineNr, fileName);

}



/* Callback handler invoked when the breakpoint configuration changes
 * e.g. after break.set, break.delete commands
 * execution, e.g. after break command.
 * @param dummy: unused in this sample, is taken from T32_Check StateNotify() call.
 */
static void T32_callbackBreakpointConfig(int dummy) {

	/* Application may request latest breakpoint information here.*/
	printf("TRACE32: Breakpoint configuration changed. \n\n");

}


/* Callback handler invoked when the target program stops execution,
 * e.g. after break command.
 * @param dummy: unused in this sample, is taken from T32_Check StateNotify() call.
 */
static void T32_callbackBreak(int dummy) {

	/* Application may trigger further actions */
	printf("TRACE32: Target program stopped execution. \n\n");

}

