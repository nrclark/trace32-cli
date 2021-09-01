/*
 * TRACE32 Remote API
 *
 * Copyright (c) 1998-2020 Lauterbach GmbH
 * All rights reserved
 *
 * Licensing restrictions apply to this code.
 * Please see documentation (api_remote_c.pdf) for
 * licensing terms and conditions.
 *
 * $LastChangedRevision: 126221 $
 */

#ifndef TCPSIMPLE2_ajhdsf_H
#define TCPSIMPLE2_ajhdsf_H

#ifdef __cplusplus
extern "C" {
#endif

/* maximum size of message payload + header */
#define TCP2_MAX_BLOCK_SZ    0x4100
#define TCP2_BUF_SZ (TCP2_MAX_BLOCK_SZ*5)

#ifdef T32HOST_WIN
#define tcp2_socket_t SOCKET
#endif

#ifdef T32HOST_UNIX
#define tcp2_socket_t int
#define SOCKET_ERROR  (-1)
#endif

/*
	tcp2_open_listen_socket
		for a TCP server, open a listen socket

	Parameters:
		fd
			pointer to file descriptor (socket) which will be set,
			if socket is opened successfully.

		port
			TCP listen port number

		listenAddr
			Optional (might be NULL) IPv4 address to listen to.

	Return Value (error code):
		0
			No error, socket opened successfully
		<0
			Error
*/
extern int tcp2_open_listen_socket(tcp2_socket_t *fd, unsigned short port, uint32_t *listenAddr);

/*
	tcp2_accept_connection
		for a TCP server, accept an incoming connection

	Parameters:
		fd
			pointer to file descriptor (socket) which will be set,
			if connection to TCP listen socket is accepted successfully.

		listen_fd
			file descriptor (socket) for the TCP listen socket.

	Return Value (error code):
		0
			No error, successfully accepted connection.
		<0
			Error
*/
extern int tcp2_accept_connection(tcp2_socket_t *fd,tcp2_socket_t listen_fd);

/*
	tcp2_open_connection
		for a TCP client, open a connection to a server

	Parameters:
		fd
			pointer to file descriptor (socket) which will be set,
			if connection is successfully established.

		hostname
			Name of host to connect to.
			Note: IPv4 addresses are also allowed here (like "127.0.0.1")

		port
			Port number of server TCP listening port.

	Return Value (error code):
		0
			No error, successfully established connection.
		<0
			Error
*/
extern int tcp2_open_connection(tcp2_socket_t *fd, const char *hostname, unsigned short port);

/*
	tcp2_close_socket
		Close an open socket.

	Parameters
		fd
			file descriptor of socket which should be closed.

	Return Value (error code):
		0
			No error, successfully closed socket.
		<0
			Error
*/
extern int tcp2_close_socket(tcp2_socket_t fd);

/* Set NoDelay option for socket (Disable TCP Nagle Algorithm */
extern void tcp2_set_nodelay(tcp2_socket_t fd, int enable);


/*
	Structure to handle an established connection
*/
typedef struct tcp2_connection {
	tcp2_socket_t fd;
	struct {
		int wrIdx;
		int rdIdx;
		unsigned char *buf;
	} recv;
	struct {
		int wrIdx;
		int rdIdx;
		unsigned char *buf;
	} send;
} tcp2_connection_t, *tcp2_connection_p;

/*
	tcp2_reinit_connection
		Initialize members of "struct tcp2_connection".
		Use this function if "tcp2_init_connection" has been called before.

	Parameters
		fd
			file descriptor (socket) of established TCP connection.
		con
			pointer to "struct tcp2_connection", which will be initialized.
*/
extern void tcp2_reinit_connection(tcp2_connection_p con, tcp2_socket_t fd);

/*
	tcp2_init_connection
		First calls "tcp2_reinit_connection" and ADDITIONALLY
		reserves space (via malloc) for the send and receive buffers.

	Parameters
		fd
			file descriptor (socket) of established TCP connection.
		con
			pointer to "struct tcp2_connection", which will be initialized.
*/
extern void tcp2_init_connection(tcp2_connection_p con, tcp2_socket_t fd);

/* message structure which is used to send and receive messages */
typedef struct tcp2_msg
{
	int valid;               /* !=0 if message is valid */

	int msg_len;             /* length of payload */
	int msg_type;            /* message type */
	unsigned char *msg_data; /* payload */
} tcp2_msg_t,*tcp2_msg_p;

/*
	tcp2_send_prep
	tcp2_send_do

		to send a message:

		tcp2_msg_t tcpMsg;
		tcp2_send_prep(connection, &tcpMsg);
		// set     tcpMsg.msg_type
		// set     tcpMsg.msg_len
		// fill in tcpMsg.msg_data (with tcpMsg.msg_len bytes)
		tcp2_send_do(connection, &tcpMsg);
*/
extern int tcp2_send_prep(tcp2_connection_p con, tcp2_msg_p msg);
extern int tcp2_send_do(tcp2_connection_p con, tcp2_msg_p msg);

/*
	tcp2_poll_msg
		to check/receive a message:

		tcp2_msg_t tcpMsg;
		int err;
		tcpMsg.valid = 0;
		err = tcp2_poll_msg(connection, &tcpMsg, timeoutInMicroSeconds);
		if (err!=0) {
			// error (for example connection was closed)
		}
		if (tcpMsg.valid == 0) {
			// timeout (no message arrived in the specified time)
		}
		// We have a valid message in tcpMsg
		// tcpMsg.msg_type => type of message
		// tcpMsg.msg_len  => number of received bytes
		// tcpMsg.msg_data => pointer to data of received bytes

	Parameters
		con
			pointer to "struct tcp2_connection" for
			an established connection.
		msg
			pointer to "struct tcp2_msg" to receive data.

		waitUsec
			0                             => don't wait (just check if there is a message).
			1..TCP2_POLL_WAIT_INFINITE-1  => timeout at the specified amount of micro seconds.
			TCP2_POLL_WAIT_INFINITE..     => wait indefinitely for message.
*/
#define TCP2_POLL_WAIT_INFINITE 0x01000000
extern int tcp2_poll_msg(tcp2_connection_p con, tcp2_msg_p msg, int waitUsec);

#ifdef __cplusplus
}
#endif

#endif   /* #ifndef TCPSIMPLE2_ajhdsf_H */
