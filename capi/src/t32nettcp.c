/*
 * TRACE32 Remote API
 *
 * Copyright (c) 1998-2020 Lauterbach GmbH
 * All rights reserved
 *
 * Link hlinknet.c and hremote.c
 * with your application to use the Remote API via UDP.
 *
 * Link tcpsimple2.c, t32nettcp.c and hremote.c
 * with your application to use the Remote API via TCP.
 *
 * Licensing restrictions apply to this code.
 * Please see documentation (api_remote_c.pdf) for
 * licensing terms and conditions.
 *
 * $LastChangedRevision: 128154 $
 */

/* including t32.h will set T32HOST... defines */
#define T32INTERNAL_MAGIC 0xfe8ac993
#include "t32.h"

#if defined(T32HOST_UNIX)
# ifndef T32HOST_SOL
#  define _XOPEN_SOURCE 500
# endif
# ifndef _POSIX_C_SOURCE
#  define _POSIX_C_SOURCE 200112L
# endif
# if defined(T32HOST_SOL)
#  define __EXTENSIONS__
# endif
#endif

#if defined(T32HOST_UNIX)
# include <sys/types.h>
# include <fcntl.h>
# include <unistd.h>
# include <sys/time.h>
# include <errno.h>
# include <sys/socket.h>
# include <netinet/in.h>
# include <netdb.h>
# include <sys/select.h>
#endif

#if defined(T32HOST_WIN)
# define _CRT_SECURE_NO_WARNINGS 1
# pragma warning( push )
# pragma warning( disable : 4255 )
# include <winsock2.h>
# include <ws2tcpip.h>
# pragma warning( pop )
# include <winioctl.h>
# include <stdlib.h>
# include <fcntl.h>
#endif

#include <stdint.h>
#include <string.h>  /* strcpy     */
#include <stdlib.h>  /* strtoul    */
#include "tcpsimple2.h"
#include "t32nettcp.h"

typedef struct {
	int sz;
	int wrIdx;
	int rdIdx;
	tcp2_msg_t *msgs;

	int szP;
	int wrIdxP;
	int rdIdxP;
	uint8_t *payload;
} notifyQueueT, *notifyQueueP;


typedef struct LineStruct_s {
	char         NodeName[80];  /* NODE=     */  /* node name of host running T32 SW */
	uint16_t     TcpServerPort; /* PORT=     */  /* TCP port to connect to */
	char         LineUp;        /* 1 if we are already connected */
	uint32_t     MessageId;

	tcp2_connection_t con;
	notifyQueueT notifyQueue;
} LineStruct;

static T32_THREADLOCAL struct {
	int isLineParamsInitialized;
	LineStruct lineParams;
	LineStruct *pLineParams;
} gThread;

static void SetToDefaultLineParams(LineStruct * params)
{
	if ((params == &gThread.lineParams) && gThread.isLineParamsInitialized!=0)
		return;

	memset(params,0,sizeof(LineStruct));
	strcpy(params->NodeName, "localhost");
	params->TcpServerPort = 20000;

	if (params == &gThread.lineParams)
		gThread.isLineParamsInitialized = 1;
}

static LineStruct *InitEmptyLineParams(void)
{
	if (gThread.pLineParams == NULL) {
		gThread.pLineParams = &gThread.lineParams;
		SetToDefaultLineParams(gThread.pLineParams);
	}
	return gThread.pLineParams;
}

static int  t32NetTcpConfig(char *input)
{
	LineStruct     *line;

	line = InitEmptyLineParams();

	if (!strncmp((char *) input, "NODE=", 5)) {
		strcpy(line->NodeName, input + 5);
		return 1;
	}
	if (!strncmp((char *) input, "PORT=", 5)) {
		line->TcpServerPort = (uint16_t)strtoul((input+5), NULL, 0);
		return 1;
	}
	// To be compatible to API via UDP.
	if (!strncmp((char *) input, "HOSTPORT=", 9)) {
		return 1;
	}
	if (!strncmp((char *) input, "PACKLEN=", 8)) {
		return 1;
	}
	if (!strncmp((char *) input, "TIMEOUT=", 8)) {
		// Currently (2020-07-15)
		// TCP transport does not check for keep-alive packets.
		return 1;
	}
	return -1;
}

static int t32NetTcpInit(char *message)
{
	LineStruct     *line;
	tcp2_socket_t  fd;
	tcp2_msg_t tcpMsg;
	int err;
	int intfType;
	uint32_t srvTcpVersion;
	uint32_t srvRclVersion;

	line = InitEmptyLineParams();

	if (line->LineUp) {
		return 0;
	}

#ifdef T32HOST_WIN
	{
		WSADATA wsa;
		if (WSAStartup(0x0202, &wsa)) {
			strcpy(message, "WSAStartup returned error.");
			return -1;
		}
	}
#endif

	err = tcp2_open_connection(&fd, line->NodeName, line->TcpServerPort);
	if (err) {
		strcpy(message, "Can't connect");
		return -1;
	}
	if (line->con.recv.buf == NULL)
		tcp2_init_connection(&line->con, fd);
	else
		tcp2_reinit_connection(&line->con, fd);

	// send packet to t32 to tell it which client RCL version is used
	tcp2_send_prep(&line->con, &tcpMsg);

	tcpMsg.msg_type = T32_NETTCP_CLIENT_INFO;
	tcpMsg.msg_len  = 32;
	memset(tcpMsg.msg_data, 0, 32);

	tcpMsg.msg_data[ 0] = (uint8_t)(T32_NETTCP_VERSION>>0);
	tcpMsg.msg_data[ 1] = (uint8_t)(T32_NETTCP_VERSION>>8);
	tcpMsg.msg_data[ 2] = (uint8_t)(T32_NETTCP_VERSION>>16);
	tcpMsg.msg_data[ 3] = (uint8_t)(T32_NETTCP_VERSION>>24);

	tcpMsg.msg_data[ 4] = (uint8_t)(T32_NETTCP_INTFTYPE_RCL>>0);
	tcpMsg.msg_data[ 5] = (uint8_t)(T32_NETTCP_INTFTYPE_RCL>>8);

	tcpMsg.msg_data[ 8] = (uint8_t)(T32_NETTCP_RCL_VERSION>>0);
	tcpMsg.msg_data[ 9] = (uint8_t)(T32_NETTCP_RCL_VERSION>>8);
	tcpMsg.msg_data[10] = (uint8_t)(T32_NETTCP_RCL_VERSION>>16);
	tcpMsg.msg_data[11] = (uint8_t)(T32_NETTCP_RCL_VERSION>>24);
	// 2020-07-24: Bytes 12..31 unused
	tcp2_send_do(&line->con, &tcpMsg);

	// wait for packet from t32 to find out what kind of server it is
	tcpMsg.valid=0;
	err = tcp2_poll_msg(&line->con, &tcpMsg, TCP2_POLL_WAIT_INFINITE);
	if (err!=0 || tcpMsg.valid==0 || tcpMsg.msg_type != T32_NETTCP_SERVER_INFO)
		goto errExit;

	if (tcpMsg.msg_len < 12)
		goto errExit;

	srvTcpVersion = 0;
	srvTcpVersion |= ((uint32_t)tcpMsg.msg_data[0])<<0;
	srvTcpVersion |= ((uint32_t)tcpMsg.msg_data[1])<<8;
	srvTcpVersion |= ((uint32_t)tcpMsg.msg_data[2])<<16;
	srvTcpVersion |= ((uint32_t)tcpMsg.msg_data[3])<<24;

	intfType = 0;
	intfType |= ((int)tcpMsg.msg_data[4])<<0;
	intfType |= ((int)tcpMsg.msg_data[5])<<8;

	srvRclVersion = 0;
	srvRclVersion |= ((uint32_t)tcpMsg.msg_data[8])<<0;
	srvRclVersion |= ((uint32_t)tcpMsg.msg_data[9])<<8;
	srvRclVersion |= ((uint32_t)tcpMsg.msg_data[10])<<16;
	srvRclVersion |= ((uint32_t)tcpMsg.msg_data[11])<<24;

	// If we have an incompatible MAJOR version, exit
	if (T32_NETTCP_VER_MAJOR(srvTcpVersion) != T32_NETTCP_VER_MAJOR(T32_NETTCP_VERSION))
		goto errExit;

	// If server does not support at least our minor version exit
	if (T32_NETTCP_VER_MINOR(srvTcpVersion) < T32_NETTCP_VER_MINOR(T32_NETTCP_VERSION))
		goto errExit;

	if (intfType != T32_NETTCP_INTFTYPE_RCL)
		goto errExit;

	// If we have an incompatible MAJOR version, exit
	if (T32_NETTCP_VER_MAJOR(srvRclVersion) != T32_NETTCP_VER_MAJOR(T32_NETTCP_RCL_VERSION))
		goto errExit;

	// If server does not support at least our minor version exit
	if (T32_NETTCP_VER_MAJOR(srvRclVersion) < T32_NETTCP_VER_MAJOR(T32_NETTCP_RCL_VERSION))
		goto errExit;

	line->LineUp = 1;
	return 1;

errExit:
	tcp2_close_socket(line->con.fd);
	line->con.fd = SOCKET_ERROR;
	return -1;
}

static void t32NetTcpExit(void)
{
	LineStruct     *line;

	line = gThread.pLineParams;
	if (!line)
		return;
	if (!line->LineUp)
		return;
	tcp2_close_socket(line->con.fd);
	line->con.fd = SOCKET_ERROR;
	line->LineUp = 0;
}

static int t32NetTcpGetSocket(void)
{
	// not useful for TCP ? So for now not implemented.
	return -1;
}

static int t32NetTcpTransmit(unsigned char *in, int size)
{
	LineStruct *line;
	tcp2_msg_t tcpMsg;

	line = gThread.pLineParams;
	if (!line)
		return -1;
	if (!line->LineUp)
		return -1;
	if (size<5)
		return -1;

	// seems hremote.c assumes a 5 byte empty header...
	// get rid of it.
	tcp2_send_prep(&line->con, &tcpMsg);
	tcpMsg.msg_type = T32_NETTCP_RCL_REQ;
	tcpMsg.msg_len  = size-5;
	memcpy(tcpMsg.msg_data, in+5, size-5);
	tcp2_send_do(&line->con, &tcpMsg);
	return 1;
}

static void notifyGrowPayload(notifyQueueP notifyQueue)
{
	int wrIdx, rdIdx, sz, szP, wrIdxP, msgLen;
	uint8_t *newPayloadBuf;

	sz    = notifyQueue->sz;
	wrIdx = notifyQueue->wrIdx;
	rdIdx = notifyQueue->rdIdx;

	wrIdxP = 0;
	szP    = notifyQueue->szP*2;
	newPayloadBuf = (uint8_t *)malloc(szP);
	// copy payload of already existing messages into
	// new space for payload.
	while (rdIdx != wrIdx) {
		msgLen = notifyQueue->msgs[rdIdx].msg_len;
		if (msgLen>0) {
			memcpy(
				newPayloadBuf + wrIdxP,
				notifyQueue->msgs[rdIdx].msg_data,
				msgLen
			);
		}
		notifyQueue->msgs[rdIdx].msg_data = newPayloadBuf + wrIdxP;
		wrIdxP += msgLen;
		// if (wrIdxP > szP) => fatal error
		rdIdx++;
		if (rdIdx>=sz)
			rdIdx = 0;
	}
	free(notifyQueue->payload);
	notifyQueue->szP     = szP;
	// border case handling:
	//    only empty messages enqueued
	// OR no messages enqueued
	notifyQueue->rdIdxP = szP;
	if (wrIdxP>0) {
		// queue has some payload data.
		notifyQueue->rdIdxP = 0;
	}
	notifyQueue->wrIdxP  = wrIdxP;
	notifyQueue->payload = newPayloadBuf;
}

static void notifyCopyPayload(notifyQueueP notifyQueue, tcp2_msg_t *tcpDestMsg, tcp2_msg_t *tcpSrcMsg)
{
	int szP,wrIdxP,rdIdxP;

	szP = notifyQueue->szP;
	wrIdxP = notifyQueue->wrIdxP;
	rdIdxP = notifyQueue->rdIdxP;
	// Note: The reason this condition works is,
	// because   rdIdxP:=szP wrIdxP:=0  if payload buffer is empty.
	if (wrIdxP <= rdIdxP && wrIdxP + tcpSrcMsg->msg_len > rdIdxP) {
		// we would overtake rdIdxP => grow payload buffer
		notifyGrowPayload(notifyQueue);
		szP = notifyQueue->szP;
		wrIdxP = notifyQueue->wrIdxP;
		rdIdxP = notifyQueue->rdIdxP;
	}
	else if (wrIdxP + tcpSrcMsg->msg_len > notifyQueue->szP) {
		// we would write over the end of the payload buffer
		// => go to start of payload buffer
		wrIdxP = 0;
		if (tcpSrcMsg->msg_len > rdIdxP) {
			// we would overtake rdIdxP => grow payload buffer
			notifyGrowPayload(notifyQueue);
			szP = notifyQueue->szP;
			wrIdxP = notifyQueue->wrIdxP;
			rdIdxP = notifyQueue->rdIdxP;
		}
	}
	tcpDestMsg->msg_data = notifyQueue->payload + wrIdxP;
	wrIdxP += tcpSrcMsg->msg_len;
	// if (wrIdxP > szP) => fatal error

	if (rdIdxP >= szP && wrIdxP>0) {
		// payload buffer was empty and now has some data.
		// => set read index to start of payload buffer
		notifyQueue->rdIdxP = 0;
	}
	// we allow a message payload a perfect fit
	// at the end of the payload buffer.
	// So here it might be that wrIdxP == szP.
	// In this case set wrIdxP to 0.
	if (wrIdxP >= szP)
		wrIdxP = 0;
	notifyQueue->wrIdxP = wrIdxP;

	if (tcpSrcMsg->msg_len>0)
		memcpy(tcpDestMsg->msg_data, tcpSrcMsg->msg_data, tcpSrcMsg->msg_len);
}

static void notifyInitQueue(notifyQueueP notifyQueue)
{
	// allocate buffers for tcp2_msg_t structures and payload.
	notifyQueue->sz      = 8;
	notifyQueue->szP     = TCP2_MAX_BLOCK_SZ*2;
	notifyQueue->wrIdx   = 0;
	notifyQueue->rdIdx   = 0;
	notifyQueue->wrIdxP  = 0;
	notifyQueue->rdIdxP  = notifyQueue->szP;

	notifyQueue->msgs    = (tcp2_msg_t *)malloc(sizeof(tcp2_msg_t)*notifyQueue->sz);
	notifyQueue->payload = (uint8_t *)malloc(notifyQueue->szP);
}

static void notifyGrowQueue(notifyQueueP notifyQueue)
{
	int rdIdx,sz;
	tcp2_msg_t *newMsgBuf;

	// Note queue is full:
	//  sz entries used
	//  wrIdx == rdIdx
	rdIdx = notifyQueue->rdIdx;
	sz    = notifyQueue->sz;
	newMsgBuf = (tcp2_msg_t *)malloc(sizeof(tcp2_msg_t)*sz*2);

	// copy rdIdx..(sz-1) to start of new queue space
	memcpy(newMsgBuf, &(notifyQueue->msgs[rdIdx]), sizeof(tcp2_msg_t)*(sz-rdIdx));
	if (rdIdx>0) {
		// copy 0..(rdIdx-1) at next part of new queue space
		memcpy(newMsgBuf+(sz-rdIdx), notifyQueue->msgs, sizeof(tcp2_msg_t)*rdIdx);
	}
	free(notifyQueue->msgs);
	notifyQueue->msgs  = newMsgBuf;
	notifyQueue->rdIdx = 0;
	notifyQueue->wrIdx = sz;
	notifyQueue->sz    = sz*2;
}

static void notifyEnqueueMsg(notifyQueueP notifyQueue, tcp2_msg_t *tcpMsg)
{
	int wrIdx;
	tcp2_msg_t *tcpDstMsg;

	if (notifyQueue->sz == 0)
		notifyInitQueue(notifyQueue);

	wrIdx = notifyQueue->wrIdx;
	tcpDstMsg = &(notifyQueue->msgs[wrIdx]);

	*tcpDstMsg = *tcpMsg;
	notifyCopyPayload(notifyQueue, tcpDstMsg, tcpMsg);

	wrIdx++;
	if (wrIdx == notifyQueue->sz)
		wrIdx = 0;
	notifyQueue->wrIdx = wrIdx;
	if (wrIdx == notifyQueue->rdIdx) {
		// queue now full => grow queue
		notifyGrowQueue(notifyQueue);
	}
}

static tcp2_msg_t *notifyDequeueMsg(notifyQueueP notifyQueue)
{
	int wrIdx, rdIdx;
	tcp2_msg_t *msg;

	// note: this also works if queue has
	// not been initialized yet,
	// because then wrIdx == rdIdx == 0
	wrIdx = notifyQueue->wrIdx;
	rdIdx = notifyQueue->rdIdx;
	if (wrIdx == rdIdx)
		return NULL;

	msg = &(notifyQueue->msgs[rdIdx]);
	rdIdx++;
	if (rdIdx >= notifyQueue->sz)
		rdIdx = 0;
	notifyQueue->rdIdx = rdIdx;

	if (rdIdx == wrIdx) {
		// queue is now empty
		// allocate next payload from payload buffer idx 0
		// mark that payload buffer is empty by setting rdIdxP to szP
		notifyQueue->wrIdxP = 0;
		notifyQueue->rdIdxP = notifyQueue->szP;
	}
	else {
		// set read index for payload buffer to start of next message
		notifyQueue->rdIdxP = (int)(notifyQueue->msgs[rdIdx].msg_data - notifyQueue->payload);
	}
	return msg;
}

static int t32NetNotificationPending(void)
{
	LineStruct     *line;

	line = gThread.pLineParams;
	if (line->notifyQueue.wrIdx != line->notifyQueue.rdIdx)
		return 1;
	return 0;
}

static int t32NetTcpReceiveNotifyMessage(unsigned char *package)
{
	LineStruct *line;
	tcp2_msg_t *notifyMsg;
	int err;
	tcp2_msg_t tcpMsg;

	line = gThread.pLineParams;
	if (!line)
		return -1;
	if (!line->LineUp)
		return -1;

	notifyMsg = NULL;
	for(;;) {
		notifyMsg = notifyDequeueMsg(&(line->notifyQueue));
		if (notifyMsg != NULL)
			break;

		tcpMsg.valid=0;
		err = tcp2_poll_msg(&line->con, &tcpMsg, 0);
		if (err)
			return -1;
		if (tcpMsg.valid==0)
			return -1;
		if (tcpMsg.msg_type == T32_NETTCP_RCL_NOTIFY) {
			notifyMsg = &tcpMsg;
			break;
		}
		// this is actually a fatal error.
		return -1;
	}
	memcpy(package, notifyMsg->msg_data, notifyMsg->msg_len);

	/*
		package[1] == type of notification:
			T32_E_BREAK,
			T32_E_EDIT,
			T32_E_BREAKPOINTCONFIG,
			...
	*/
	return package[1];
}

static int t32NetTcpReceive(unsigned char *out)
{
	LineStruct *line;
	tcp2_msg_t tcpMsg;
	int err;

	line = gThread.pLineParams;
	if (!line)
		return -1;
	if (!line->LineUp)
		return -1;
	do {
		tcpMsg.valid=0;
		err = tcp2_poll_msg(&line->con, &tcpMsg, TCP2_POLL_WAIT_INFINITE);
		if (err)
			return -1;
		if (tcpMsg.valid==0)
			return -1;
		if (tcpMsg.msg_type == T32_NETTCP_RCL_NOTIFY) {
			notifyEnqueueMsg(&(line->notifyQueue),&tcpMsg);
		}
	} while (tcpMsg.msg_type != T32_NETTCP_RCL_RESP);

	out[0] = 0x0;
	out[1] = 0x0;                            // == T32_INBUFFER[0]
	out[2] = 0x0;                            // == T32_INBUFFER[1]
	// out[3]                                // == T32_INBUFFER[2]  == T32_Errno
	// out[4]                                // == T32_INBUFFER[3]  MessageId
	memcpy(out+3, tcpMsg.msg_data, tcpMsg.msg_len);
	return tcpMsg.msg_len+3;
}

static int t32NetTcpSync(void)
{
	return 1;
}

static int t32NetTcpGetParamsSize(void)
{
	return (int)sizeof(LineStruct);
}

static void t32NetTcpDefaultParams(LineStruct * ParametersOut)
{
	SetToDefaultLineParams(ParametersOut);
}

static void t32NetTcpSetParams(LineStruct * params)
{
	gThread.pLineParams = params;
}

static void t32NetTcpSetReceiveToggleBit(int value)
{
	(void)value; // warning fix
}

static int t32NetTcpGetReceiveToggleBit(void)
{
	return 1;
}

static unsigned char t32NetTcpGetNextMessageId(void)
{
	LineStruct *line;

	line = gThread.pLineParams;
	if (!line)
		return 0;
	line->MessageId++;
	return (unsigned char)line->MessageId;
}

static unsigned char t32NetTcpGetMessageId(void)
{
	LineStruct *line;

	line = gThread.pLineParams;
	if (!line)
		return 0;
	return (unsigned char)line->MessageId;
}

static struct T32InternalLineDriver gT32NetTcpDrv = {
	t32NetTcpConfig,                // Config
	t32NetTcpInit,                  // Init
	t32NetTcpExit,                  // Exit
	t32NetTcpGetSocket,             // GetSocket
	t32NetTcpTransmit,              // Transmit
	t32NetTcpReceive,               // Receive
	t32NetTcpReceiveNotifyMessage,  // ReceiveNotifyMessage
	t32NetTcpSync,                  // Sync
	t32NetTcpGetParamsSize,         // GetParamsSize
	t32NetTcpDefaultParams,         // DefaultParams
	t32NetTcpSetParams,             // SetParams
	t32NetTcpSetReceiveToggleBit,   // SetReceiveToggleBit
	t32NetTcpGetReceiveToggleBit,   // GetReceiveToggleBit
	t32NetTcpGetNextMessageId,      // GetNextMessageId
	t32NetTcpGetMessageId,          // GetMessageId
	t32NetNotificationPending       // NotificationPending
};
struct T32InternalLineDriver *gT32InternalLineDriver = &gT32NetTcpDrv;
