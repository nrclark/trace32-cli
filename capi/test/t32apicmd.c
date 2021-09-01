/* *********************************************************************************************
 * @Title: TRACE32 Remote API that use T32_Cmd() and T32_GetMessage()
 * @Description:
 *   TRACE32 Remote API sample program illustrating the use of T32_Cmd() and T32_GetMessage()
 *   This demo send a command to TRACE32 PowerView and request any AREA message.
 *   Syntax:   t32apicmd  [node=<name_or_IP>]  [port=<num>]  <cmd>
 *   Example:  t32apicmd   node=localhost       port=20000   PRINT VERSION.BUILD()
 *
 *  For remote access TRACE32's configuration file "config.t32" has to contain these lines:
 *
 *    RCL=NETASSIST
 *    PORT=20000
 *
 *  This default port value may be changed but has to match the specified command line value.
 *
 *  This sample program also shows how to establish and close a remote connection with TRACE32.
 *
 * $Id: t32apicmd.c 125610 2020-09-04 10:22:33Z kjmal $
 * $LastChangedRevision: 125610 $
 * $LastChangedBy: kjmal $
 *
 * @Copyright: (C) 1989-2020 Lauterbach GmbH, licensed for use with TRACE32(R) only
 * *********************************************************************************************
 * $Id: t32apicmd.c 125610 2020-09-04 10:22:33Z kjmal $
 */

#define WIN_MESSAGEMODENONE       0x00
#define WIN_MESSAGEMODEINFO       0x01
#define WIN_MESSAGEMODEERROR      0x02
#define WIN_MESSAGEMODESTATE      0x04
#define WIN_MESSAGEMODEWARNINFO   0x08
#define WIN_MESSAGEMODEERRORINFO  0x10
#define WIN_MESSAGEMODETEMP       0x20
#define WIN_MESSAGEMODETEMPINFO   0x40


#include "t32.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
int indexOf_shift (char* base, char* str, unsigned int startIndex) {
	int result;
	unsigned int baselen = strlen(base);
		char* pos=NULL;
	// str should not longer than base
	if (strlen(str) > baselen || startIndex > baselen) {
		result = -1;
	} else {
		if (startIndex < 0 ) {
			startIndex = 0;
		}
		pos = strstr(base+startIndex, str);
		if (pos == NULL) {
			result = -1;
		} else {
			result = pos - base;
		}
	}
	return result;
}
int lastIndexOf (char* base, char* str) {
	int result;
	// str should not longer than base
	if (strlen(str) > strlen(base)) {
		result = -1;
	} else {
		unsigned int start = 0;
		unsigned int endinit = strlen(base) - strlen(str);
		unsigned int end = endinit;
		int endtmp = endinit;
		while(start != end) {
			start = indexOf_shift(base, str, start);
			end = indexOf_shift(base, str, end);

			// not found from start
			if (start == -1) {
				end = -1; // then break;
			} else if (end == -1) {
				// found from start
				// but not found from end
				// move end to middle
				if (endtmp == (start+1)) {
					end = start; // then break;
				} else {
					end = endtmp - (endtmp - start) / 2;
					if (end <= start) {
						end = start+1;
					}
					endtmp = end;
				}
			} else {
				// found from both start and end
				// move start to end and
				// move end to base - strlen(str)
				start = end;
				end = endinit;
			}
		}
		result = start;
	}
	return result;
}
int main(int argc, char **argv)
{
	int       i, j = 0, argn = 1, retval = EXIT_SUCCESS;
	char      cmdstring[2041],msgstring[4095];
	uint16_t  msgtype;
	int index = lastIndexOf(__FILE__,".");
	char  filename [100];
	if      (index == -1 ){
		strcpy(filename,__FILE__);
		}
		else {
		strncpy(filename, __FILE__, index);
		}

	/*** get command line parameters and establish connection ************************************/

	if ((argc > argn) && (!strncmp(argv[argn], "node=", 5) || !strncmp(argv[argn], "NODE=", 5))) {
		T32_Config("NODE=", argv[argn] + 5);
		argn++;
	}

	if ((argc > argn) && (!strncmp(argv[argn], "port=", 5) || !strncmp(argv[argn], "PORT=", 5))) {
		if (T32_Config("PORT=", argv[argn] + 5) != T32_OK) {
			printf("\n\n Invalid port number '%s' specified.\n", argv[argn] + 5);
			retval = EXIT_FAILURE;
		}
		argn++;
	}

	if ((argc <= argn) || (retval == EXIT_FAILURE)) {
		printf("\n\n Syntax:  %s.exe [node=<name_or_IP>] [port=<num>] <cmd>", filename);
		printf(  "\n Example: %s.exe  node=localhost      port=20000  PRINT VERSION.BUILD()\n\n\n", filename);

		printf(" Messages printed to TRACE32 AREA window are also printed to this\n");
		printf(" shell. Most PRACTICE commands like Go only generate a message in\n");
		printf(" case of an error.  Escaping is important if the PRINT command is\n");
		printf(" used (try  PRINT \042\042\042hi\042\042\042  and  PRINT \042\042\042"
							  "\042\042\042\042hi\042\042\042\042\042\042\042).\n\n");
		return EXIT_FAILURE;
	}
		/* PRINT """hi""" and PRINT """""""hi""""""" work this way:                                       */
		/* If a command line argument/string is enclosed by quotes, it loses one opening and one closing  */
		/* quote when the string is stored in argv, so ""hi"" and """"""hi"""""" will be left. For the    */
		/* input-data of T32_Cmd() the C-language's standard quote-sign-escaping is applied, so "hi" and  */
		/* """hi""" are transfered to TRACE32 PowerView. TRACE32 expects strings to be enclosed by quotes */
		/* and standard quote-sign-escaping is expected for further quotes, so hi and "hi" are printed.   */

	printf("\n\n Connecting...");

	for (i = 0; i < 2; i++) {  /* try twice */
		if (T32_Init() == T32_OK) {
			if (T32_Attach(T32_DEV_ICD) == T32_OK)
				break;
			else
				printf("%s to establish a remote connection with TRACE32 PowerView.%s\n",
					   i==0?"\n\n Failed once":"\n Failed twice", i==0?"\n":" Terminating ...\n");
		}
		else
			printf("%s to initialize the remote connection.%s\n",
				   i==0?"\n\n Failed once":"\n Failed twice", i==0?" ":" Terminating ...\n");

		T32_Exit(); /* reset/close a potentially existing connection */
		if (i == 1)
			return EXIT_FAILURE;
	}

	if (i == 1)
		printf("\r Successfully established a remote connection with TRACE32 PowerView.");
	else
		printf("\r              \n"); /* just clear */


	/*** send input command to TRACE32 PowerView for execution and return any message ************/

	for (i = argn; i < argc; i++)
		j += strlen(argv[i]); /* see T32_Cmd(),MaxPacketSize in hremote.c */
	if ((j + argc - argn - 1 > 2048 - 8) || (sizeof(cmdstring) != 2041)) {
		printf(" Failed to send remote command, command exceeds 2040 characters.\n");
		return EXIT_FAILURE;
	}

	strcpy(cmdstring, argv[argn]);
	while (++argn < argc) {
		strcat(cmdstring, " ");
		strcat(cmdstring, argv[argn]);
	}

	retval = EXIT_FAILURE;            /* bugfix: calling T32_Cmd("PRINT") first ensures   */
	if (T32_Cmd("PRINT") == T32_OK) { /* that T32_GetMessage() will return no old message */
		if (T32_Cmd(cmdstring) == T32_OK) {
			if (T32_GetMessage(msgstring, &msgtype) == T32_OK) {
				if (msgtype < (WIN_MESSAGEMODETEMPINFO << 1)) {
					retval = EXIT_SUCCESS;
					if ( ( msgtype != WIN_MESSAGEMODENONE                                                 )&&
						!((msgstring[0] == 0) && (msgtype & (WIN_MESSAGEMODETEMPINFO|WIN_MESSAGEMODETEMP)))  ) {
						 /* bugfix: for empty message the message type may be temp => DO NOT DISPLAY */

						if (msgtype & WIN_MESSAGEMODEINFO)
							printf(" info ");
						if (msgtype & WIN_MESSAGEMODESTATE)
							printf(" status ");
						if (msgtype & WIN_MESSAGEMODEWARNINFO)
							printf(" warning ");
						if ((msgtype & WIN_MESSAGEMODEERRORINFO) || (msgtype & WIN_MESSAGEMODEERROR))
							printf(" error ");
						if ((msgtype & WIN_MESSAGEMODETEMPINFO)  || (msgtype & WIN_MESSAGEMODETEMP))
							printf(" miscellaneous ");
						printf("message: %s\n\n", msgstring);
					}
					else
						printf(" successfully executed user command '%s'\n\n", cmdstring);
				}
				else
					printf(" Failed to determine the type of the return message.\n\n");
			}
			else
				printf(" Failed to query return message.\n\n");
		}
		else
			printf(" Failed to execute erroneous user command '%s'\n\n", cmdstring);
	}
	else
		printf(" Failed to execute 'T32_Cmd(""PRINT"")'\n\n" );

	if (T32_Exit() != T32_OK) {
		printf(" Failed to close the remote connection port on the dos shell application's side.\n\n");
		return EXIT_FAILURE;
	}
	else
		return retval;
}


