/* *********************************************************************************************
 * @Title: TRACE32 Remote API that run the communication test with FDX target sample program
 * @Description:
 * The program creates a connection to TRACE32 and run the communication test
 * with an FDX target sample program
 *
 * The port on which TRACE32 listens for API connections can optionally be
 * set with the --port <n> parameter. The port number must match with
 * the definition in config.t32. The default value is 20000.
 *
 * a binary of this sample can be found in t32/bin/<arch>/
 *
 * Syntax:  t32fdxhost <host> [port=<n>]
 *
 * Example: t32fdxhost localhost port=20002
 *
 *
 * $Id: t32fdxhost.c 125610 2020-09-04 10:22:33Z kjmal $
 * $LastChangedRevision: 125610 $
 * $LastChangedBy: kjmal $
 *
 * @Copyright: (C) 1989-2020 Lauterbach GmbH, licensed for use with TRACE32(R) only
 * *********************************************************************************************
 * $Id: t32fdxhost.c 125610 2020-09-04 10:22:33Z kjmal $
 */

#include "t32.h"

#if defined(_MSC_VER)
# pragma warning( push )
# pragma warning( disable : 4255 )
#endif

#include <stdlib.h>
#include <stdio.h>
#include <string.h>

#ifdef T32HOST_WIN
# include <windows.h>
#else
# include <time.h>
# include <sys/time.h>
# include <unistd.h>
#endif

#if defined(_MSC_VER)
# pragma warning( pop )
#endif


#ifdef WORD_ALIGNED_TARGET
typedef unsigned short fdxdatatype;
#else
typedef unsigned char fdxdatatype;
#endif


static int32_t GetMsecTimer(void)
{
#if defined(T32HOST_WIN)
	return GetTickCount();
#elif defined(T32HOST_LINUX) || defined(T32HOST_SOL)
	uint64_t        t;
	struct timespec clocktime;

	clock_gettime(CLOCK_REALTIME, &clocktime);
	/* microseconds since the epoch */
	t = (uint64_t) clocktime.tv_sec * 1000 * 1000 + clocktime.tv_nsec / 1000;
	return (t / 1000);
#elif defined(T32HOST_MACOSX)
	uint64_t         t;
	struct timeval  clocktime;

	gettimeofday(&clocktime, NULL);
	t = (uint64_t) clocktime.tv_sec * 1000 * 1000 + clocktime.tv_usec;
	return (t / 1000);
#else
# error Platform not supported
#endif
}

static void WaitMsecTimer(int32_t time_ms)
{
#ifdef T32HOST_WIN
	Sleep(time_ms);
#else
	struct timespec timeout;
	timeout.tv_sec = time_ms / 1000;
	timeout.tv_nsec = (uint64_t) (time_ms % 1000) * 1000 * 1000;
	nanosleep(&timeout, NULL);
#endif
}




int main(int argc, char **argp)
{
	int             argn;
	int             i, len;
	int             fdxin, fdxout;
	int32_t            starttime, stoptime, stoptime2;
	fdxdatatype     buffer[4096];

	if ( argc < 2 ) {
		printf( "usage: t32fdxhost <host> [port=<n>]\n" );
		exit(2);
	}
	if ( T32_Config( "NODE=", argp[1] ) == -1 ) {
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

	printf("connecting...\n");

	if (T32_Init() == -1) {
		printf("error initializing TRACE32\n");
		T32_Exit();
		return 2;
	}
	if (T32_Attach(1) != 0) {
		printf("error no device\n");
		T32_Exit();
		return 2;
	}
	if ((fdxin = T32_Fdx_Open("FdxTestSendBuffer","r")) == -1) {
		printf("error no FDX buffer\n");
		T32_Exit();
		return 2;
	}
	if ((fdxout = T32_Fdx_Open("FdxTestReceiveBuffer","w")) == -1) {
		printf("error no FDX buffer\n");
		T32_Exit();
		return 2;
	}
	printf("  connection o.k.\n");

	printf("receiving test data...\n");

	for (i = 0; i < 50; i++) {
		len = T32_Fdx_Receive(fdxin, buffer, sizeof(buffer[0]), sizeof(buffer) / sizeof(buffer[0]));
		if (len <= 0) {
			printf("FDX receive error\n");
			T32_Exit();
			return 2;
		}
		if (len != i + 2 || buffer[0] != '0' + i || buffer[len - 1] != '1' + i)
			goto wrongpacket;
	}

	len = T32_Fdx_Receive(fdxin, buffer, sizeof(buffer[0]), sizeof(buffer) / sizeof(buffer[0]));
	if (len != 1)
		goto wrongpacket;

	printf("  short packets o.k.\n");

	for (i = 0; i < 10; i++) {
		len = T32_Fdx_Receive(fdxin, buffer, sizeof(buffer[0]), sizeof(buffer) / sizeof(buffer[0]));
		if (len != 1000) {
			printf("FDX receive error\n");
			T32_Exit();
			return 2;
		}
		if (buffer[0] != 'a' || buffer[1] != 'b' || buffer[2] != 'c' || buffer[3] != i || buffer[999] != i)
			goto wrongpacket;
	}

	len = T32_Fdx_Receive(fdxin, buffer, sizeof(buffer[0]), sizeof(buffer) / sizeof(buffer[0]));
	if (len != 1)
		goto wrongpacket;

	printf("  long packets o.k.\n");

	printf("sending test data...\n");

	for (i = 0; i < 50; i++) {
		len = i + 2;
		buffer[0] = '0' + i;
		buffer[len - 1] = '1' + i;
		if (T32_Fdx_Send(fdxout, buffer, sizeof(buffer[0]), len) == -1) {
			printf("FDX send error\n");
			T32_Exit();
			return 2;
		}
	}

	buffer[0] = 0;
	if (T32_Fdx_Send(fdxout, buffer, sizeof(buffer[0]), 1) == -1) {
		printf("FDX send error\n");
		T32_Exit();
		return 2;
	}
	printf("  short packets o.k.\n");

	for (i = 0; i < 10; i++) {
		buffer[0] = 'x';
		buffer[1] = 'y';
		buffer[2] = 'z';
		buffer[3] = i;
		if (T32_Fdx_Send(fdxout, buffer, sizeof(buffer[0]), 1000) == -1) {
			printf("FDX send error\n");
			T32_Exit();
			return 2;
		}
	}

	buffer[0] = 0;
	if (T32_Fdx_Send(fdxout, buffer, sizeof(buffer[0]), 1) == -1) {
		printf("FDX send error\n");
		T32_Exit();
		return 2;
	}
	printf("  long packets o.k.\n");

	WaitMsecTimer(1000);    /* give target time to send data to buffer */

	printf("receive latency test...\n");

	starttime = GetMsecTimer();

	for (i = 0; i < 1000; i++) {
		len = T32_Fdx_Receive(fdxin, buffer, sizeof(buffer[0]), sizeof(buffer) / sizeof(buffer[0]));
		if (len != 1 || buffer[0] != 0)
			goto wrongpacket;
	}

	stoptime = GetMsecTimer();

	printf("  host latency: %d usec\n", stoptime - starttime);

	buffer[0] = 0;
	if (T32_Fdx_Send(fdxout, buffer, sizeof(buffer[0]), 1) == -1) {
		printf("FDX send error\n");
		T32_Exit();
		return 2;
	}
	starttime = GetMsecTimer();

	for (i = 0; i < 1000; i++) {
		len = T32_Fdx_Receive(fdxin, buffer, sizeof(buffer[0]), sizeof(buffer) / sizeof(buffer[0]));
		if (len != 1 || buffer[0] != 0)
			goto wrongpacket;
	}

	stoptime = GetMsecTimer();

	printf("  total latency: %d usec\n", stoptime - starttime);

	buffer[0] = 0;
	if (T32_Fdx_Send(fdxout, buffer, sizeof(buffer[0]), 1) == -1) {
		printf("FDX send error\n");
		T32_Exit();
		return 2;
	}
	printf("send latency test...\n");

	starttime = GetMsecTimer();

	for (i = 0; i < 1000; i++) {
		buffer[0] = 0;
		if (T32_Fdx_Send(fdxout, buffer, sizeof(buffer[0]), 1) == -1) {
			printf("FDX send error\n");
			T32_Exit();
			return 2;
		}
	}

	stoptime = GetMsecTimer();

	len = T32_Fdx_Receive(fdxin, buffer, sizeof(buffer[0]), sizeof(buffer) / sizeof(buffer[0]));
	if (len != 1)
		goto wrongpacket;

	stoptime2 = GetMsecTimer();

	printf("  host latency: %d usec\n", stoptime - starttime);
	printf("  total latency: %d usec\n", stoptime2 - starttime);

	printf("send/receive latency test...\n");

	starttime = GetMsecTimer();

	for (i = 0; i < 1000; i++) {
		buffer[0] = 0;
		if (T32_Fdx_Send(fdxout, buffer, sizeof(buffer[0]), 1) == -1) {
			printf("FDX send error\n");
			T32_Exit();
			return 2;
		}
		len = T32_Fdx_Receive(fdxin, buffer, sizeof(buffer[0]), sizeof(buffer) / sizeof(buffer[0]));
		if (len != 1 || buffer[0] != 0)
			goto wrongpacket;
	}

	stoptime = GetMsecTimer();

	printf("  total latency: %d usec\n", stoptime - starttime);

	printf("receive data thruput test...\n");

	starttime = GetMsecTimer();

	for (i = 0; i < 100; i++) {
		len = T32_Fdx_Receive(fdxin, buffer, sizeof(buffer[0]), sizeof(buffer) / sizeof(buffer[0]));
		if (len != 1024)
			goto wrongpacket;
	}

	stoptime = GetMsecTimer();

	printf("  thruput: %d KB/sec\n", 100000 / (stoptime - starttime));

	printf("send data thruput test...\n");

	starttime = GetMsecTimer();

	for (i = 0; i < 100; i++) {
		buffer[0] = 0;
		if (T32_Fdx_Send(fdxout, buffer, sizeof(buffer[0]), 1024) == -1) {
			printf("FDX send error\n");
			T32_Exit();
			return 2;
		}
	}

	len = T32_Fdx_Receive(fdxin, buffer, sizeof(buffer[0]), sizeof(buffer) / sizeof(buffer[0]));
	if (len != 1)
		goto wrongpacket;

	stoptime = GetMsecTimer();

	printf("  thruput: %d KB/sec\n", 100000 / (stoptime - starttime));

	printf("done.\n");

	T32_Fdx_Close(fdxin);
	T32_Fdx_Close(fdxout);

	T32_Exit();

	return 0;

wrongpacket:
	printf("wrong FDX packet received:\n");
	for (i = 0; i < len; i++) {
		printf("%x ", buffer[i]);
	}
	printf("\n");
	T32_Exit();
	return 2;
}
