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

#include <stdint.h>   /* uint32_t */
#include <stdio.h>    /* printf   */
#include <string.h>   /* memcpy   */
#include <stdlib.h>   /* malloc   */

// Try to auto-detect T32HOST_* defines
#ifdef _WIN32
# ifndef T32HOST_WIN
#  define T32HOST_WIN
# endif
# ifndef T32HOST_LE
#  define T32HOST_LE
# endif
# if !defined(T32HOST_WIN_X86) && (defined(_M_IX86) || defined(__i386__))
#  define T32HOST_WIN_X86
# endif
# if !defined(T32HOST_WIN_X64) && (defined(_M_X64) || defined(__x86_64__))
#  define T32HOST_WIN_X64
# endif
#endif

#if defined(__linux__) || defined(__CYGWIN__)
# ifndef T32HOST_LINUX
#  define T32HOST_LINUX
# endif
# ifndef T32HOST_UNIX
#  define T32HOST_UNIX
# endif
# if !defined(T32HOST_LINUX_X86) && defined(__i386__)
#  define T32HOST_LINUX_X86
# endif
# if !defined(T32HOST_LINUX_X64) && defined(__x86_64__)
#  define T32HOST_LINUX_X64
# endif
# if !defined(T32HOST_LINUX_PPC) && defined(__ppc__)
#  define T32HOST_LINUX_PPC
# endif
# if !defined(T32HOST_LINUX_ARM) && defined(__SOFTFP__) && defined(__ARM_ARCH_4T__)
#  define T32HOST_LINUX_ARM
# endif
# if !defined(T32HOST_LINUX_ARMHF) && !defined(__SOFTFP__) && defined(__ARM_ARCH_7A__)
#  define T32HOST_LINUX_ARMHF
# endif
# if !defined(T32HOST_LINUX_ARM64) && defined(__aarch64__)
#  define T32HOST_LINUX_ARM64
# endif
# if !defined(T32HOST_LE) && (defined(T32HOST_LINUX_X86) || defined(T32HOST_LINUX_X64) || defined(T32HOST_LINUX_ARM) || defined(T32HOST_LINUX_ARMHF) || defined(T32HOST_LINUX_ARM64))
#  define T32HOST_LE
# endif
# if !defined(T32HOST_BE) && defined(T32HOST_LINUX_PPC)
#  define T32HOST_BE
# endif
#endif


#ifdef T32HOST_UNIX
# include <netdb.h>
# include <sys/time.h>
# include <sys/types.h>
# include <sys/socket.h>
# include <arpa/inet.h>
# include <netinet/tcp.h>
# include <unistd.h>
# include <errno.h>
# define INVALID_SOCKET -1
# ifdef DEBUG
#  define LOG_PRINT(_xx) fprintf(stderr,"Function %s, Line %d, Error: %s\n", __PRETTY_FUNCTION__ , __LINE__ , _xx);
# else
#  define LOG_PRINT(_xx)
# endif
#endif

#ifdef T32HOST_WIN
# pragma warning( push )
# pragma warning( disable : 4255 4005)
# include <winsock2.h>
# include <ws2tcpip.h>
# pragma warning( pop )

# include <winioctl.h>
# include <stdlib.h>
# include <fcntl.h>
# define ssize_t int
# ifdef DEBUG
#  define LOG_PRINT(_xx) fprintf(stderr,"Error: %s\n", _xx);
# else
#  define LOG_PRINT(_xx)
# endif
#endif

#include "tcpsimple2.h"

#define GET_WORD_LE(value,ptr)  do { \
	unsigned char *MV_v1_ = &(ptr); \
	uint32_t MV_v2_;\
	MV_v2_ = (((uint32_t)(MV_v1_[0]))<<0)|(((uint32_t)(MV_v1_[1]))<<8); \
	(value) = (uint16_t)MV_v2_; \
} while ((0))

#define GET_DWORD_LE(value,ptr)  do { \
	unsigned char *MV_v1_ = &(ptr); \
	uint32_t MV_v2_;\
	MV_v2_ = \
		(((uint32_t)(MV_v1_[0]))<< 0)|(((uint32_t)(MV_v1_[1]))<< 8)| \
		(((uint32_t)(MV_v1_[2]))<<16)|(((uint32_t)(MV_v1_[3]))<<24); \
	(value) = MV_v2_; \
} while ((0))

#define GET_WORD_BE(value,ptr)  do { \
	unsigned char *MV_v1_ = &(ptr); \
	uint32_t MV_v2_;\
	MV_v2_ = (((uint32_t)(MV_v1_[0]))<<8)|(((uint32_t)(MV_v1_[1]))<<0); \
	(value) = (uint16_t)MV_v2_; \
} while ((0))

#define GET_DWORD_BE(value,ptr)  do { \
	unsigned char *MV_v1_ = &(ptr); \
	uint32_t MV_v2_;\
	MV_v2_ = \
		(((uint32_t)(MV_v1_[0]))<<24)|(((uint32_t)(MV_v1_[1]))<<16)| \
		(((uint32_t)(MV_v1_[2]))<< 8)|(((uint32_t)(MV_v1_[3]))<< 0); \
	(value) = MV_v2_; \
} while ((0))


#define SET_WORD_LE(ptr,value)  do { \
	unsigned char *MV_v1_ = &(ptr); \
	uint32_t MV_v2_ = (value); \
	MV_v1_[0] = (unsigned char)(MV_v2_>>0); \
	MV_v1_[1] = (unsigned char)(MV_v2_>>8); \
} while ((0))

#define SET_DWORD_LE(ptr,value) do { \
	unsigned char *MV_v1_ = &(ptr); \
	uint32_t MV_v2_ = (value); \
	MV_v1_[0] = (unsigned char)(MV_v2_>> 0); \
	MV_v1_[1] = (unsigned char)(MV_v2_>> 8); \
	MV_v1_[2] = (unsigned char)(MV_v2_>>16); \
	MV_v1_[3] = (unsigned char)(MV_v2_>>24); \
} while ((0))

#define SET_WORD_BE(ptr,value)  do { \
	unsigned char *MV_v1_ = &(ptr); \
	uint32_t MV_v2_ = (value); \
	MV_v1_[0]= (unsigned char)(MV_v2_>>8); \
	MV_v1_[1]= (unsigned char)(MV_v2_>>0); \
} while ((0))

#define SET_DWORD_BE(ptr,value) do { \
	unsigned char *MV_v1_ = &(ptr); \
	uint32_t MV_v2_ = (value); \
	MV_v1_[0] = (unsigned char)(MV_v2_>>24); \
	MV_v1_[1] = (unsigned char)(MV_v2_>>16); \
	MV_v1_[2] = (unsigned char)(MV_v2_>> 8); \
	MV_v1_[3] = (unsigned char)(MV_v2_>> 0); \
} while ((0))


static void printNetworkErrorDetails(int errType, int errValue)
{
	(void)errType;  // warning fix
	(void)errValue; // warning fix

#if defined(DEBUG)

#if defined(T32HOST_WIN)
	char msg[512];
	int wsaErr;

	(void)errType;
	(void)errValue;
	wsaErr = WSAGetLastError();
	if (
		FormatMessage(
			FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
			NULL,  // lpSource (ignored with FORMAT_MESSAGE_FROM_SYSTEM)
			wsaErr,
			LANG_SYSTEM_DEFAULT,
			(LPTSTR)msg,
			sizeof(msg),
			NULL   // Arguments (ignored wih FORMAT_MESSAGE_IGNORE_INSERTS)
		)
	) {
		fprintf(stderr, "    details: %s\n",msg);
	}
#endif
#if defined(T32HOST_UNIX)
	switch(errType) {
	case 1:
		// errno
		fprintf(stderr, "    details: %s\n", strerror(errno));
		break;
	case 2:
		// getaddrinfo
		fprintf(stderr, "    details: %s\n" ,gai_strerror(errValue));
		break;
	default:
		;
	}
#endif

#endif // #if defined(DEBUG)
}

int tcp2_close_socket(tcp2_socket_t fd)
{
#ifdef T32HOST_WIN
	shutdown(fd,SD_BOTH);
	closesocket(fd);
#endif
#ifdef T32HOST_LINUX
	close(fd);
#endif
	return 0;
}

int tcp2_open_connection(tcp2_socket_t *fd, const char *hostname, unsigned short port)
{
	tcp2_socket_t fd_int;
	struct sockaddr_in addr;
	int ret;
	struct addrinfo hints, *ai_result;
	int ai_status;
	uint32_t nbo_ipaddr;

	memset(&hints, 0, sizeof hints);
	hints.ai_family = AF_INET;
	hints.ai_socktype = SOCK_STREAM;

	ai_status = getaddrinfo(hostname, NULL, &hints, &ai_result);
	if (ai_status != 0) {
		LOG_PRINT("getaddrinfo() failed");
		printNetworkErrorDetails(2,ai_status);
		return -1;
	}

	nbo_ipaddr = ((struct sockaddr_in *) ai_result->ai_addr)->sin_addr.s_addr;
	freeaddrinfo(ai_result);

	fd_int = socket(AF_INET, SOCK_STREAM, 0);
	if (fd_int == INVALID_SOCKET) {
		LOG_PRINT("socket() failed");
		printNetworkErrorDetails(1,0);
		return -1;
	}

	memset(&addr, 0, sizeof(addr));
	addr.sin_family = AF_INET;
	addr.sin_port = htons((unsigned short)port);
	addr.sin_addr.s_addr = nbo_ipaddr;

	// connect to remote TCP socket
	ret = connect(fd_int, (struct sockaddr *) &addr, sizeof(addr));
	if (ret == SOCKET_ERROR) {
		LOG_PRINT("connect() failed");
		printNetworkErrorDetails(1,0);
		tcp2_close_socket(fd_int);
		return -1;
	}
	*fd=fd_int;
	return 0;
}


int tcp2_open_listen_socket(tcp2_socket_t *fd, unsigned short port, uint32_t *listenAddr)
{
	tcp2_socket_t listen_fd;
	int ret;
	struct sockaddr_in addrBind;

	listen_fd = socket(AF_INET, SOCK_STREAM, 0);
	if (listen_fd == INVALID_SOCKET)
		return -1;

#if defined(T32HOST_UNIX)
	/* Avoid "Error Address already in use" on UNIX systems, when socket is in "TIME_WAIT" state */
	/* Note: Windows behaves differently for "SO_REUSEADDR", so only do this for UNIX */
	{
		int yes;

		yes = 1;
		ret = setsockopt(listen_fd, SOL_SOCKET, SO_REUSEADDR, (char *)(&yes), sizeof(yes));
		if (ret == SOCKET_ERROR) {
			LOG_PRINT("setsockopt() failed");
			printNetworkErrorDetails(1,0);
			tcp2_close_socket(listen_fd);
			return -1;
		}
	}
#endif

	memset(&addrBind, 0, sizeof(addrBind));
	addrBind.sin_family = AF_INET;
	if (listenAddr == NULL) {
		addrBind.sin_addr.s_addr = htonl(INADDR_ANY);
	}
	else {
		addrBind.sin_addr.s_addr = htonl(*listenAddr);
	}
	addrBind.sin_port = htons(port);

	/* bind socket to port */
	ret = bind(listen_fd, (struct sockaddr *) &addrBind, sizeof(addrBind));
	if (ret == SOCKET_ERROR) {
		LOG_PRINT("bind() failed");
		printNetworkErrorDetails(1,0);
		tcp2_close_socket(listen_fd);
		return -1;
	}

	ret = listen(listen_fd, 5);
	if (ret == SOCKET_ERROR) {
		LOG_PRINT("listen() failed");
		printNetworkErrorDetails(1,0);
		tcp2_close_socket(listen_fd);
		return -1;
	}
	*fd=listen_fd;
	return 0;
}

int tcp2_accept_connection(tcp2_socket_t *fd,tcp2_socket_t listen_fd)
{
	tcp2_socket_t fd_l;

	fd_l = accept(listen_fd,NULL,NULL);
	if (fd_l == INVALID_SOCKET) {
		LOG_PRINT("accept() failed");
		printNetworkErrorDetails(1,0);
		return -1;
	}
	*fd=fd_l;

	return 0;
}

void tcp2_set_nodelay(tcp2_socket_t fd,int enable)
{
	int tcpNoDelay;
	tcpNoDelay=0;
	if (enable)
		tcpNoDelay=1;
	setsockopt(fd,IPPROTO_TCP,TCP_NODELAY,(char *)(&tcpNoDelay),sizeof(tcpNoDelay));
}

/*
	Transmission is optimized to a multiple of 64-bit words.
	This seems to fit to what the world is using nowadays.
*/
#define TCP2_MSG_HDR_LENGTH 8
#define TCP2_MSGLEN_ALIGN(MP_v_) (((MP_v_)+7)&(~0x7))

void tcp2_reinit_connection(tcp2_connection_p con, tcp2_socket_t fd)
{
	con->fd = fd;
	con->recv.wrIdx = 0;
	con->recv.rdIdx = 0;
	con->send.wrIdx = 0;
	con->send.rdIdx = 0;
}

void tcp2_init_connection(tcp2_connection_p con, tcp2_socket_t fd)
{
	tcp2_reinit_connection(con, fd);
	con->recv.buf = (unsigned char *)malloc(TCP2_BUF_SZ);
	con->send.buf = (unsigned char *)malloc(TCP2_BUF_SZ);
}


#define TCP2_SEND_NEXT_IDX(MP_v_) do { \
	MP_v_ += TCP2_MAX_BLOCK_SZ; \
	if (MP_v_ > TCP2_BUF_SZ - TCP2_MAX_BLOCK_SZ) \
		MP_v_ = 0; \
} while ((0))

int tcp2_send_prep(tcp2_connection_p con, tcp2_msg_p msg)
{
	int wrIdx;

	wrIdx = con->send.wrIdx;

	msg->valid=0;
	msg->msg_type=-1;
	msg->msg_len=0;
	msg->msg_data = con->send.buf + (wrIdx + TCP2_MSG_HDR_LENGTH);

	TCP2_SEND_NEXT_IDX(wrIdx);
	con->send.wrIdx = wrIdx;
	return 0;
}

int tcp2_send_do(tcp2_connection_p con, tcp2_msg_p msg)
{
	ssize_t ret;
	int bufLen;
	unsigned char *buf;
	int rdIdx;

	rdIdx = con->send.rdIdx;
	TCP2_SEND_NEXT_IDX(rdIdx);
	con->send.rdIdx = rdIdx;

	if (msg->msg_type<1 || msg->msg_len<0 || msg->msg_len>(TCP2_MAX_BLOCK_SZ - TCP2_MSG_HDR_LENGTH)) {
		msg->valid=0;
		return -1;
	}

	msg->valid=1;
	bufLen = msg->msg_len + TCP2_MSG_HDR_LENGTH;
	bufLen = TCP2_MSGLEN_ALIGN(bufLen);

	buf = msg->msg_data - TCP2_MSG_HDR_LENGTH;
	SET_DWORD_LE(buf[0],(uint32_t)msg->msg_len);
	SET_DWORD_LE(buf[4],(uint32_t)msg->msg_type);
	ret = send(con->fd,(char *)buf,bufLen,0);
	if (ret != (ssize_t)bufLen) {
		if (ret<0) {
			LOG_PRINT("send() failed");
			printNetworkErrorDetails(1,0);
		}
		return -1;
	}

	return 0;
}

// check if we are able to extract a full message from connection receive buffer
static int tcp2_extract_message(tcp2_connection_p con, tcp2_msg_p msg)
{
	int rdIdx;
	int wrIdx;
	rdIdx = con->recv.rdIdx;
	wrIdx = con->recv.wrIdx;
	if (wrIdx >= rdIdx + 4) {
		// we can read out the message length
		int msgLen;
		int bufLen;
		GET_DWORD_LE(msgLen, con->recv.buf[rdIdx]);
		if (msgLen<0 || msgLen > TCP2_MAX_BLOCK_SZ - TCP2_MSG_HDR_LENGTH)
			return -5;
		bufLen = msgLen + TCP2_MSG_HDR_LENGTH;
		bufLen = TCP2_MSGLEN_ALIGN(bufLen);
		if (wrIdx >= rdIdx + bufLen) {
			// we got a full message in the receive buffer
			// save necessary data in msg
			int msgType;
			GET_DWORD_LE(msgType, con->recv.buf[rdIdx+4]);
			msg->msg_type = msgType;
			msg->msg_len  = msgLen;
			if (msgType<1)
				return -6;
			msg->msg_data = con->recv.buf + (rdIdx + TCP2_MSG_HDR_LENGTH);
			msg->valid    = 1;
			rdIdx += bufLen;
			con->recv.rdIdx = rdIdx;
		}
	}
	return 0;
}

#ifdef T32HOST_WIN
# pragma warning( push )
# pragma warning( disable : 4548 )
#endif
// Use select to implement waiting with timeout
// use a timeout of "0" to just immideately check for read data
static int tcp2_has_read_data(tcp2_socket_t fd, int waitUsec)
{
	struct timeval timeoutVal;
	struct timeval *timeoutPtr;
	fd_set readfds;
	int err;

	timeoutPtr = NULL;
	if (waitUsec < TCP2_POLL_WAIT_INFINITE) {
		timeoutPtr = &timeoutVal;
		timeoutVal.tv_sec  = 0;
		timeoutVal.tv_usec = waitUsec;
	}

	FD_ZERO(&readfds);
	FD_SET(fd, &readfds);
	err = select((int)(fd+1), &readfds, (fd_set *) NULL, (fd_set *) NULL, timeoutPtr);
	return err;
}
#ifdef T32HOST_WIN
# pragma warning( pop )
#endif

int tcp2_poll_msg(tcp2_connection_p con, tcp2_msg_p msg, int waitUsec)
{
	ssize_t ll;
	int err;
	int rdIdx;
	int wrIdx;
	int recvFlags;

	if (msg->valid)
		return 0;

	rdIdx = con->recv.rdIdx;
	wrIdx = con->recv.wrIdx;
	if (rdIdx > TCP2_BUF_SZ - TCP2_MAX_BLOCK_SZ) {
		// we start to get close to the end of receive buffer
		// to make more space, move already received data to start of buffer
		wrIdx -= rdIdx;
		if (wrIdx>0) {
			// move already received data to start of buffer
			// memcpy should be OK, because there should be NO overlap
			memcpy(con->recv.buf, con->recv.buf + rdIdx, wrIdx);
		}
		rdIdx  = 0;
		con->recv.rdIdx = rdIdx;
		con->recv.wrIdx = wrIdx;
	}

	err = tcp2_extract_message(con,msg);
	if (err)
		return err;
	if (msg->valid)
		return 0;

	recvFlags = 0;
#ifdef T32HOST_LINUX
	if (waitUsec == 0)
		recvFlags = MSG_DONTWAIT;
#endif
	for(;;) {

		if (recvFlags==0) {
			// we are not using "MSG_DONTWAIT"
			// => check via select if data is available
			err = tcp2_has_read_data(con->fd, waitUsec);
			if (err<0)
				return -1;
			if (err==0) {
				// we do not have any bytes to read.
				// if we want to wait indefinitely, just repeat select call
				if (waitUsec >= TCP2_POLL_WAIT_INFINITE)
					continue;
				// We don't want to wait indefinitely => stop function
				break;
			}
		}

		/* read as much as possible from TCP socket */
		ll = recv(con->fd, (char *)(con->recv.buf + wrIdx), TCP2_BUF_SZ - wrIdx, recvFlags);

		if (ll<0) {

#ifdef T32HOST_LINUX
			err = errno;
			if ((err==EAGAIN || err==EINTR) && recvFlags==MSG_DONTWAIT) {
				// Linux MSG_DONTWAIT extension:
				// we did not have any bytes to read.
				// => do nothing
				break;
			}
#endif
			// we had a weird error (fatal)
			LOG_PRINT("recv() failed");
			printNetworkErrorDetails(1,0);
			return -2;
		}

		if (ll==0) {
			// socket was closed
			return -1;
		}

		wrIdx += (int)ll;
		con->recv.wrIdx = wrIdx;

		// we got some more bytes, try to extract message again
		err = tcp2_extract_message(con,msg);
		if (err)
			return err;

		if (waitUsec<TCP2_POLL_WAIT_INFINITE || msg->valid)
			break;
	}
	return 0;
}
