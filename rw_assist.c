#include <stdint.h>
#include <stddef.h>

#include "t32.h"

int read_memory(size_t address, uint8_t awidth, char *outbuf, int len)
{
    int result = -1;
    T32_BufferHandle buffer_handle = {0};
    T32_AddressHandle address_handle = {0};

    result = T32_RequestBufferObj(&buffer_handle, 0);

    if (result != T32_OK) {
        return result;
    }

    if (awidth == 32) {
        result = T32_RequestAddressObjA32(&address_handle, address);
    } else if (awidth == 64) {
        result = T32_RequestAddressObjA64(&address_handle, address);
    } else {
        return T32_ERR_READMEMOBJ_PARAFAIL;
    }

    if (result != 0) {
        return result;
    }

    result = T32_ReadMemoryObj(buffer_handle, address_handle, len);

    if (result != T32_OK) {
        return result;
    }

    result = T32_CopyDataFromBufferObj((uint8_t *) outbuf, len, buffer_handle);

    if (result != T32_OK) {
        return result;
    }

    return T32_ReleaseBufferObj(&buffer_handle);
}

int write_memory(size_t address, uint8_t awidth, const char *inbuf, int len)
{
    int result = -1;
    T32_BufferHandle buffer_handle = {0};
    T32_AddressHandle address_handle = {0};

    result = T32_RequestBufferObj(&buffer_handle, 0);

    if (result != T32_OK) {
        return result;
    }

    if (awidth == 32) {
        result = T32_RequestAddressObjA32(&address_handle, address);
    } else if (awidth == 64) {
        result = T32_RequestAddressObjA64(&address_handle, address);
    } else {
        return T32_ERR_WRITEMEMOBJ_PARAFAIL;
    }

    if (result != 0) {
        return result;
    }

    result = T32_CopyDataToBufferObj(buffer_handle, len,
                                     (const uint8_t *) inbuf);

    if (result != T32_OK) {
        return result;
    }

    result = T32_WriteMemoryObj(buffer_handle, address_handle, len);

    if (result != T32_OK) {
        return result;
    }

    return T32_ReleaseBufferObj(&buffer_handle);
}
