// File: src/ecc_walk.cu
// Description: CUDA fixed-pattern fill/verify on device memory. Alternates 0x00000001 and 0xFFFFFFFF. Verifies on device.
#include <cuda_runtime.h>
#include <cstdio>
#include <cstdlib>

__global__ void fill_pattern(unsigned int *buf, size_t n, unsigned int value) {
    size_t i = (size_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) buf[i] = value;
}

__global__ void count_mismatch(const unsigned int *buf, size_t n, unsigned int expected, unsigned long long *out) {
    size_t i = (size_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n && buf[i] != expected) atomicAdd(out, 1ULL);
}

#define CUDA_OK(cmd) do { cudaError_t e = (cmd); if (e != cudaSuccess) { \
    std::fprintf(stderr, "CUDA %s\n", cudaGetErrorString(e)); return 2; } } while (0)

int main(int argc, char **argv) {
    if (argc < 4) {
        std::fprintf(stderr, "usage: ecc_walk <num_ints> <seconds> <iters>\n");
        return 2;
    }
    size_t n = strtoull(argv[1], 0, 10);
    double seconds = atof(argv[2]);
    int iters = atoi(argv[3]);
    int device = argc >= 5 ? atoi(argv[4]) : 0;
    int walking = argc >= 6 && (argv[5][0] == 'w' || argv[5][0] == 'W');
    if (n < 1024) n = 1024;
    CUDA_OK(cudaSetDevice(device));
    if (seconds < 0.1) seconds = 0.1;
    if (iters < 1) iters = 1;
    unsigned int *buf = 0;
    unsigned long long *d_fail = 0;
    CUDA_OK(cudaMalloc(&buf, n * sizeof(unsigned int)));
    CUDA_OK(cudaMalloc(&d_fail, sizeof(unsigned long long)));
    int threads = 256;
    int blocks = (int)((n + threads - 1) / threads);
    cudaEvent_t start;
    CUDA_OK(cudaEventCreate(&start));
    CUDA_OK(cudaEventRecord(start));
    int loops = 0;
    unsigned long long failures = 0;
    unsigned long long failed_loops = 0;
    while (true) {
        float ms = 0;
        cudaEvent_t now;
        CUDA_OK(cudaEventCreate(&now));
        CUDA_OK(cudaEventRecord(now));
        CUDA_OK(cudaEventSynchronize(now));
        CUDA_OK(cudaEventElapsedTime(&ms, start, now));
        CUDA_OK(cudaEventDestroy(now));
        if (loops > 0 && (ms / 1000.0) >= seconds) break;
        if ((ms / 1000.0) >= seconds + 1.0) break;
        for (int k = 0; k < iters; ++k) {
            unsigned int value = walking ? (1u << (loops % 32)) : ((loops & 1) ? 0xFFFFFFFFu : 0x00000001u);
            fill_pattern<<<blocks, threads>>>(buf, n, value);
            // A rejected launch (e.g. no SASS for this GPU) is only visible here;
            // without this check the walk counts zero failures and passes.
            CUDA_OK(cudaGetLastError());
            CUDA_OK(cudaMemset(d_fail, 0, sizeof(unsigned long long)));
            count_mismatch<<<blocks, threads>>>(buf, n, value, d_fail);
            CUDA_OK(cudaGetLastError());
            CUDA_OK(cudaDeviceSynchronize());
            unsigned long long batch = 0;
            CUDA_OK(cudaMemcpy(&batch, d_fail, sizeof(batch), cudaMemcpyDeviceToHost));
            failures += batch;
            if (batch > 0) failed_loops++;
            loops++;
        }
    }
    std::printf(
        "loops=%d failed_loops=%llu failures=%llu bytes=%zu\n",
        loops,
        (unsigned long long)failed_loops,
        (unsigned long long)failures,
        n * sizeof(unsigned int));
    cudaFree(buf);
    cudaFree(d_fail);
    return failures ? 1 : 0;
}
