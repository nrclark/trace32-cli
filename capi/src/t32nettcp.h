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

/*
	For NETTCP we use semantic versioning:
	BitNr
	31..24     MAJOR      Incremented if there is a completely incompatible procotol change
	23..12     MINOR      Incremented if an extension is implemented
	11..0      PATCH      Incremented for bug fixes
*/
#define T32_NETTCP_VER_MAJOR(MP_v_) ((((uint32_t)(MP_v_))>>24)&0xFF)
#define T32_NETTCP_VER_MINOR(MP_v_) ((((uint32_t)(MP_v_))>>12)&0xFFF)
#define T32_NETTCP_VER_PATCH(MP_v_) ((((uint32_t)(MP_v_))>> 0)&0xFFF)

#define T32_NETTCP_VERSION     0x01000000
enum {
	T32_NETTCP_INTFTYPE_RCL   = 0x01,
	T32_NETTCP_INTFTYPE_RCL2  = 0x02
};

#define T32_NETTCP_RCL_VERSION 0x01000000
enum {
	T32_NETTCP_CLIENT_INFO   = 0x0001,
	T32_NETTCP_SERVER_INFO   = 0x0002,

	T32_NETTCP_RCL_REQ       = 0x0010,
	T32_NETTCP_RCL_RESP      = 0x0011,
	T32_NETTCP_RCL_NOTIFY    = 0x0012
};
