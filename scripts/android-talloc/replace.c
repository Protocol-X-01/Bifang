#include <stddef.h>

void *rep_memset_explicit(void *buffer, int value, size_t length)
{
    volatile unsigned char *cursor = buffer;
    while (length != 0) {
        *cursor++ = (unsigned char)value;
        length--;
    }
    return buffer;
}
