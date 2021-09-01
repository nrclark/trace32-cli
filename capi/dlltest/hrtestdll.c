
#include "t32.h"
#include "stdio.h"

extern int T32_Errno;

extern char * getenv();

uint8_t         buffer[12000];
uint16_t        wbuffer[12000];

int main(argc, argp)
int argc;
char * * argp;
{
	int             ch;
	int             i, j;
	int             statinfo;
	uint32_t        cpu_registers[64];
	int             retries = 0;

retryit:
	retries++;

#if 0
	{
		char           *ptr;
		if ((ptr = getenv("T32NODE")) != 0) {
			T32_Config("NODE=", ptr);
		}
		if ((ptr = getenv("T32PORT")) != 0) {
			T32_Config("PORT=", ptr);
		}
	}
#endif

	if (T32_Init() == -1) {
		printf("error initializing T32\n");
		T32_Exit();
		if (retries < 2)
			goto retryit;
		return 2;
	}
	if (T32_Attach(1) != 0) {
		printf("error no device\n");
	}
	while (1) {
		printf("\n     Q    Quit Program\n");
		printf("\n     s    STOP Cmd");
		printf("\n     D    DO Test\n");
		printf("\n     n    NOP Test");
		printf("\n     N    1000*NOP Test");
		printf("\n     P    PING Test\n");
		printf("\n     m    Read Memory");
		printf("\n     M    Write Memory");
		printf("\n     W    Write Memory Pipelined 1MB\n");
		printf("\n     r    Read Registers");
		printf("\n     R    Write Registers\n");
		printf("\n     b    Read Breakpoints");
		printf("\n     B    Write Breakpoints\n");
		printf("\n     C    CPU Reset");
		printf("\n     c    CPU State\n");
		printf("\n     S    Single Step");
		printf("\n     G    Go");
		printf("\n     g    Break\n");
		printf("\nCMD> ");

		do {
			ch = getchar();
		}
		while (ch == '\n');

		if (ch == 'Q' || ch == 'q')
			break;

		switch (ch) {
		case 'n':               /* NOP */
			if (T32_Nop() == -1)
				goto error;
			break;
		case 'p':               /* NOP */
			if (T32_NopFail() == -1)
				goto error;
			break;
		case 'N':               /* 1000*NOP */
			for (i = 0; i < 1000; i++) {
				if (T32_Nop() == -1)
					goto error;
			}
			break;
		case 's':               /* STOP */
			if (T32_Stop() == -1)
				goto error;
			break;
		case 'P':               /* PING */
			if (T32_Ping() == -1)
				goto error;
			break;
		case 'D':               /* DO */
			if (T32_Cmd("do test") == -1)
				goto error;
			break;
		case 'M':               /* Memory Write */
			if ((T32_WriteMemory(0x1234l, 0x40, (unsigned char *) "hello world", 12)))
				goto error;
			break;
		case 'W':               /* DOWNLOAD */
			for (i = 0; i < 256; i++) {
				if ((T32_WriteMemoryPipe(0x1234l, 0x40, (unsigned char *) "hello world", 4096)))
					goto error;
			}
			if (T32_WriteMemoryPipe(0l, 0, (unsigned char *) 0, 0))
				goto error;
			break;
		case 'm':               /* Memory Read */
			if ((T32_ReadMemory(0x1234l, 0, buffer, 200)))
				goto error;
			printf("\n");
			for (i = 0; i < 16; i++)
				printf(" %02x", buffer[i]);
			printf("\n");
			break;
		case 'i':               /* read ICEbreaker COMM status & data (ARM) */
			if ((T32_ReadMemory(4 * 4, 0x43, buffer, 2 * 4)))
				goto error;
			printf("\n");
			for (i = 0; i < 8; i++)
				printf(" %02x", buffer[i]);
			printf("\n");
			break;
		case 'I':               /* write ICEbreaker data */
			buffer[0] = 'x';
			buffer[1] = 'x';
			buffer[2] = 'x';
			buffer[3] = 'x';
			if ((T32_WriteMemory(5 * 4, 0x43, buffer, 1 * 4)))
				goto error;
			break;
		case 'r':               /* Register Read */
			if ((T32_ReadRegister(0xffffffffl, 0l, cpu_registers)))
				goto error;
			printf("\n");
			for (i = 0; i < 32; i++)
				printf(" %08lx", cpu_registers[i]);
			printf("\n");
			break;
		case 'R':               /* Register Write */
			for (i = 0; i < 8; i++)
				cpu_registers[i]++;
			if ((T32_WriteRegister(0xffl, 0l, cpu_registers)))
				goto error;
			break;
		case 'b':               /* Breakpoint Read */
			if ((T32_ReadBreakpoint(0x1234l, 0, wbuffer, 8)))
				goto error;
			printf("\n");
			for (i = 0; i < 8; i++)
				printf(" %04x", wbuffer[i]);
			printf("\n");
			break;
		case 'B':               /* Breakpoint Write */
			if ((T32_WriteBreakpoint(0x1234l, 0x80, 0x18, 4)))      /* Set */
				goto error;
			if ((T32_WriteBreakpoint(0x1238l, 0x80, 0x118, 4)))     /* Clear */
				goto error;
			if ((T32_WriteBreakpoint(0x123cl, 0x80, 0x01, 1)))      /* Set */
				goto error;
			if ((T32_WriteBreakpoint(0x1240l, 0x80, 0x101, 1)))     /* Clear */
				goto error;
			if ((T32_WriteBreakpoint(0x1250l, 0x80, 0x01, 1)))      /* Set */
				goto error;
			if ((T32_WriteBreakpoint(0x1250l, 0x80, 0x101, 1)))     /* Clear */
				goto error;
			break;
		case 'c':               /* STATE */
			if ((i = T32_GetState(&statinfo)))
				goto error;
			switch (statinfo) {
			case 0:
				printf("\ndown\n");
				break;
			case 1:
				printf("\nhalted\n");
				break;
			case 2:
				printf("\nstopped\n");
				break;
			case 3:
				printf("\nrunning\n");
				break;
			}
			break;
		case 'C':               /* CPU Reset/Prepare */
			if (T32_ResetCPU())
				goto error;
			break;
		case 'S':               /* Single Step */
			if (T32_Step())
				goto error;
			break;
		case 'G':               /* Start Realtime */
			if (T32_Go())
				goto error;
			break;
		case 'g':               /* Stop Realtime */
			if (T32_Break())
				goto error;
			break;
		case 'j':               /* JTAG tap access */
			buffer[0] = 'a';
			buffer[1] = 'b';
			buffer[2] = 'c';
			buffer[3] = 'd';
			if (T32_TAPAccessShiftIR(0, 32, buffer, buffer))
				goto error;
			printf("\n");
			for (i = 0; i < 4; i++)
				printf(" %02x", buffer[i]);
			printf("\n");
			break;
		case 'x':               /* test */
			for (i = 0; i < 10; i++) {
				int             state;
				uint32_t        pcvalue;
				T32_GetState(&state);
				printf("T32_GetState %d\n", state);
				T32_Step();
				printf("T32_Step\n");
				T32_GetState(&state);
				printf("T32_GetState %d\n", state);
				T32_ReadPP(&pcvalue);
				printf("T32_ReadPP %d\n", pcvalue);
				T32_GetState(&state);
				printf("T32_GetState %d\n", state);
				T32_GetState(&state);
				printf("T32_GetState %d\n", state);
				T32_GetState(&state);
				printf("T32_GetState %d\n", state);
			}
			break;
		case 'a':               /* Analyzer readout */
			{
				int width;
				int             state;
				int32_t         records, min, max;

				if (T32_GetTraceState(0, &state, &records, &min, &max))
					goto error;

				printf("T32_GetTraceState state: %d, records: %ld, min: %ld, max: %ld \n", state, records, min, max);

				width = 17*4;
				if (T32_ReadTrace(0, min, 100, 0x1ffff, buffer))
					goto error;

				for (i = 0; i < 100; i++) {
					printf("frame %10d: ", min+i);
					for (j = 0; j < width; j += 4) {
						printf("%02x%02x%02x%02x ", buffer[i * width + j + 3], buffer[i * width + j + 2], buffer[i * width + j + 1], buffer[i * width + j + 0]);
					}
					printf("\n");
				}
			}
			break;
		case 'J':               /* Integrator readout */
			{
				int width;
				int             state;
				int32_t         records, min, max;

				if (T32_GetTraceState(1, &state, &records, &min, &max))
					goto error;

				printf("T32_GetTraceState state: %d, records: %ld, min: %ld, max: %ld \n", state, records, min, max);

				width = 3*4;
				if (T32_ReadTrace(1, min, 100, 0x1000c, buffer))
					goto error;

				for (i = 0; i < 100; i++) {
					printf("frame %10d: ", min+i);
					for (j = 0; j < width; j += 4) {
						printf("%02x%02x%02x%02x ", buffer[i * width + j + 3], buffer[i * width + j + 2], buffer[i * width + j + 1], buffer[i * width + j + 0]);
					}
					printf("\n");
				}
			}
			break;

		default:
			printf("no such command\n");
		}
		continue;
error:
		printf("error %d accessing T32\n", T32_Errno);
	}

	T32_Exit();

	return 0;
}



