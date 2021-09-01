/*
 * Copyright (c) 2020, embedded brains GmbH
 *
 *  embedded brains GmbH
 *  Dornierstr. 4
 *  82178 Puchheim
 *  Germany
 *  <info@embedded-brains.de>
 *
 * Permission to use, copy, modify, and/or distribute this software for any
 * purpose with or without fee is hereby granted, provided that the above
 * copyright notice and this permission notice appear in all copies.
 *
 * THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 * WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
 * SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 * WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION
 * OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
 * CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 */

#include <getopt.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include "t32.h"

static const struct option longopts[] = {
	{ "help", 0, NULL, 'h' },
	{ "node", 1, NULL, 'n' },
	{ "packlen", 1, NULL, 'l' },
	{ "port", 1, NULL, 'p' },
	{ "verbose", 0, NULL, 'v' },
	{ NULL, 0, NULL, 0 }
};

static void usage(char **argv)
{
	printf(
		"%s [OPTION]... [FILE]...\n"
		"\n"
		"Mandatory arguments to long options are mandatory for short options too.\n"
		"  -h, --help                 print this help text\n"
		"  -n, --node=NODE            the node name of the Trace32 instance\n"
		"  -l, --packlen=PACKLEN      the packet length to use\n"
		"  -p, --port=PORT            the port of the Trace32 instance\n"
		"  -v, --verbose              print commands sent to Trace32 instance\n",
		argv[0]
	);
}

static void atexit_handler(void)
{
	T32_Exit();
}

static void signal_handler(int sig)
{
	(void) sig;

	exit(EXIT_FAILURE);
}

static void send_commands(FILE *file, int verbose)
{
	char *line = NULL;
	size_t len = 0;
	ssize_t n;

	while ((n = getline(&line, &len, file)) >= 0) {
		int error;

		line[n - 1] = '\0';

		if (verbose) {
			puts(line);
		}

		error = T32_Cmd(line);
		if (error != 0) {
			fprintf(stderr, "command failed: \"%s\"\n", line);
			exit(EXIT_FAILURE);
		}
	}

	free(line);
}

int main(int argc, char **argv)
{
	int error;
	int retry = 0;
	const char *node = "localhost";
	const char *packlen = "1024";
	const char *port = "20000";
	int verbose = 0;
	int opt;
	int longindex;

	while ((opt = getopt_long(argc, argv, "hn:l:p:v", &longopts[0], &longindex)) != -1) {
		switch (opt) {
			case 'h':
				usage(argv);
				exit(EXIT_SUCCESS);
				break;
			case 'n':
				node = optarg;
				break;
			case 'l':
				packlen = optarg;
				break;
			case 'p':
				port = optarg;
				break;
			case 'v':
				verbose = 1;
				break;
			default:
				exit(EXIT_FAILURE);
				break;
		}
	}

	error = T32_Config("NODE=", node);
	if (error != 0) {
		fprintf(stderr, "invalid node: \"%s\"\n", node);
		exit(EXIT_FAILURE);
	}

	error = T32_Config("PACKLEN=", packlen);
	if (error != 0) {
		fprintf(stderr, "invalid packet length: \"%s\"\n", packlen);
		exit(EXIT_FAILURE);
	}

	error = T32_Config("PORT=", port);
	if (error != 0) {
		fprintf(stderr, "invalid port: \"%s\"\n", packlen);
		exit(EXIT_FAILURE);
	}

	error = T32_Init();
	if (error != 0) {
		fprintf(stderr, "cannot initialize Trace32 API\n");
		exit(EXIT_FAILURE);
	}

	do {
		error = T32_Attach(T32_DEV_ICE);
		if (error != 0) {
			sleep(3);
		}

		++retry;
	} while (error != 0 && retry <= 3);

	if (error == 0) {
		atexit(atexit_handler);
		signal(SIGINT, signal_handler);
	} else {
		fprintf(stderr, "cannot attach to Trace32 instance\n");
		exit(EXIT_FAILURE);
	}

	if (optind < argc) {
		while (optind < argc) {
			FILE *file = fopen(argv[optind], "r");

			if (file == NULL) {
				perror("cannot open file");
			}

			send_commands(file, verbose);
			fclose(file);

			++optind;
		}
	} else {
		send_commands(stdin, verbose);
	}

	exit(EXIT_SUCCESS);
}

