#include <stdint.h>
#include <stddef.h>

int32_t convert_sample_arith(int32_t raw_32) {
    return raw_32 >> 8;
}

void convert_buffer(int32_t *dest, const int32_t *src, size_t count) {
    for (size_t i = 0; i < count; i++) {
        dest[i] = src[i] >> 8;
    }
}

void convert_buffer_inplace(int32_t *buf, size_t count) {
    for (size_t i = 0; i < count; i++) {
        buf[i] >>= 8;
    }
}
