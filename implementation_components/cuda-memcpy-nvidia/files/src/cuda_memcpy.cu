// File: src/cuda_memcpy.cu
// Description: Timed H2D, D2H, and D2D copies. Prints one direction per invocation.
#include <cuda_runtime.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#define CUDA_OK(cmd) do { cudaError_t e = (cmd); if (e != cudaSuccess) { \
    std::fprintf(stderr, "CUDA %s\n", cudaGetErrorString(e)); return 2; } } while (0)

int main(int argc, char **argv) {
    if (argc < 5) {
        std::fprintf(stderr, "usage: cuda_memcpy <bytes> <warmup> <iters> <H2D|D2H|D2D|H2D_pageable|D2H_pageable>\n");
        return 2;
    }
    size_t bytes = strtoull(argv[1], 0, 10);
    int warmup = atoi(argv[2]);
    int iters = atoi(argv[3]);
    const char *kind = argv[4];
    // H2D_pageable and D2H_pageable use malloc'd host memory instead of
    // cudaMallocHost; the copy direction comes from the part before "_pageable".
    char base[16] = {0};
    std::strncpy(base, kind, sizeof(base) - 1);
    char *suffix = std::strstr(base, "_pageable");
    int pageable = suffix != 0;
    if (suffix) *suffix = '\0';
    if (std::strcmp(base, "H2D") && std::strcmp(base, "D2H") && std::strcmp(base, "D2D")) {
        std::fprintf(stderr, "unknown copy kind %s\n", kind);
        return 2;
    }
    if (pageable && std::strcmp(base, "D2D") == 0) {
        std::fprintf(stderr, "D2D has no host buffer; D2D_pageable is not a copy kind\n");
        return 2;
    }
    if (bytes < 8) bytes = 8;
    if (warmup < 0) warmup = 0;
    if (iters < 1) iters = 1;
    void *h = 0, *d = 0, *d2 = 0;
    if (pageable) {
        h = std::malloc(bytes);
        if (!h) return 2;
        std::memset(h, 1, bytes);
    } else {
        CUDA_OK(cudaMallocHost(&h, bytes));
    }
    CUDA_OK(cudaMalloc(&d, bytes));
    CUDA_OK(cudaMalloc(&d2, bytes));
    cudaMemcpyKind dir = cudaMemcpyHostToDevice;
    void *dst = d;
    void *src = h;
    if (std::strcmp(base, "D2H") == 0) {
        dir = cudaMemcpyDeviceToHost;
        dst = h;
        src = d;
        CUDA_OK(cudaMemcpy(d, h, bytes, cudaMemcpyHostToDevice));
    } else if (std::strcmp(base, "D2D") == 0) {
        dir = cudaMemcpyDeviceToDevice;
        dst = d2;
        src = d;
        CUDA_OK(cudaMemcpy(d, h, bytes, cudaMemcpyHostToDevice));
    }
    cudaEvent_t a, b;
    CUDA_OK(cudaEventCreate(&a));
    CUDA_OK(cudaEventCreate(&b));
    for (int i = 0; i < warmup; ++i) CUDA_OK(cudaMemcpy(dst, src, bytes, dir));
    CUDA_OK(cudaEventRecord(a));
    for (int i = 0; i < iters; ++i) CUDA_OK(cudaMemcpy(dst, src, bytes, dir));
    CUDA_OK(cudaEventRecord(b));
    CUDA_OK(cudaEventSynchronize(b));
    float ms = 0;
    CUDA_OK(cudaEventElapsedTime(&ms, a, b));
    double sec = ms / 1000.0;
    if (sec <= 0) sec = 1e-9;
    double gb_s = (double)bytes * (double)iters / (sec * 1e9);
    double latency_us = (sec / (double)iters) * 1e6;
    std::printf("kind=%s bytes=%zu bandwidth_gb_s=%.6f latency_us=%.6f elapsed_s=%.6f\n",
                kind, bytes, gb_s, latency_us, sec);
    cudaFree(d);
    cudaFree(d2);
    if (pageable) std::free(h);
    else cudaFreeHost(h);
    return 0;
}
