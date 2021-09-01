/* **********************************************************************************************
 * @Title: TRACE32 Remote API sample program illustrating the use of the Memory Bundle Transfer function.
 * @Description:
 *   TRACE32 Remote API sample program illustrating the use of the Memory Bundle Transfer function.
 *   A number of memory read/write buffers are inititalized for being read/written back-to-back
 *   using the T32_TransferMemoryBundleObj function.
 *
 *  For remote access TRACE32's configuration file "config.t32" has to contain these lines:
 *
 *    RCL=NETASSIST
 *    PORT=20000
 *
 *  This default port value may be changed but must match the settings in the example.
 *
 *
 *  $Id: t32bundle.c 76425 2016-08-25 15:01:51Z mzens $
 *  $LastChangedRevision: 76425 $
 *  $LastChangedBy: mzens $
 *
 * @Copyright: (C) 1989-2020 Lauterbach GmbH, licensed for use with TRACE32(R) only
 * *********************************************************************************************
 * $Id: t32bundle.c 76425 2016-08-25 15:01:51Z mzens $
 */

#include "t32.h"

#if defined(_MSC_VER)
# pragma warning( push )
# pragma warning( disable : 4255 )
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_MSC_VER)
# pragma warning( pop )
#endif

int main(int argc, char **argp)
{
	// T32_Config( "NODE=", "localhost" ); // default
	// T32_Config( "PORT=", "20000" ); // default

	if (T32_Init())
		goto error;

	if (T32_Attach(T32_DEV_ICD)) {
		// retry if attach error because previous UDP connection was (still) open
		T32_Exit();
		if (T32_Init())
			goto error;
		if (T32_Attach(T32_DEV_ICD))
			goto error;
	}

	printf("Initial Ping\n");
	if (T32_Ping() == -1)
		goto error;

	{
		T32_MemoryBundleHandle bundleHandle;
		T32_Size bundleSize;
		T32_Index idx;
		T32_AddressHandle ah;
		unsigned i;

		T32_RequestMemoryBundleObj(&bundleHandle, 0);

		for (i=0; i<6; i++) {
			T32_RequestAddressObjA32(&ah, i*0x10 + 0x10000);
			T32_AddToBundleObjAddrLength(bundleHandle, ah, 8+i);
			T32_ReleaseAddressObj(&ah);
		}

		for (i=6; i<10; i++) {
			uint8_t *buf;
			switch(i-6) {
			case 0: buf = "abcdefgh"; break;
			case 1: buf = "ijklmnop"; break;
			case 2: buf = "qrstuvwx"; break;
			case 3: buf = "12345678"; break;
			}
			T32_RequestAddressObjA32(&ah, i*0x10 + 0x10000);
			T32_AddToBundleObjAddrLengthByteArray(bundleHandle, ah, 8-(i-6), buf);
			T32_ReleaseAddressObj(&ah);
		}

		T32_TransferMemoryBundleObj(bundleHandle);

		T32_GetBundleObjSize(bundleHandle, &bundleSize);
		for (idx = 0; idx < bundleSize; idx++) {
			T32_BufferSynchStatus syncStatus;
			T32_GetBundleObjSyncStatusByIndex(bundleHandle, &syncStatus, idx);
			if (syncStatus == T32_BUFFER_READ) {
				uint8_t buf[14];
				printf("Bundle buffer %d was read successfully: ",idx);
				T32_CopyDataFromBundleObjByIndex(buf,8+idx,bundleHandle,idx);
				for (i=0; i<8+idx; i++)
					printf("%02x ",buf[i]);
				printf("\n");
			}
			else if (syncStatus == T32_BUFFER_WRITTEN) {
				printf("Bundle buffer %d was written successfully\n",idx);
			}
			else {
				printf("ERROR: Bundle buffer %d read/write error\n",idx);
			}
		}
		T32_ReleaseMemoryBundleObj(&bundleHandle);
	}

	printf("Final Ping\n");
	if ( T32_Ping() == -1 )
		goto error;

	T32_Exit();
	return 0;

error:
	printf("error accessing TRACE32\n");
	T32_Exit();
	return 1;
}


