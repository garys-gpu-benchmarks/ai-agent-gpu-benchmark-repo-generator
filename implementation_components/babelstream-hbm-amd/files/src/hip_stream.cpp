// File: src/hip_stream.cpp
// Description: BabelStream Copy/Mul/Add/Triad/Dot kernels. Prints GB/s per kernel.
// Options: --arraysize|-s N, --numtimes|-n N, --device N, --block-size N (1..1024,
//          default 256), --warmup N (untimed launches per kernel, default 1).
#include <hip/hip_runtime.h>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

__global__ void copy_k(const double *a, double *c, size_t n) {
    size_t i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        c[i] = a[i];
    }
}
__global__ void mul_k(const double *b, double *c, size_t n) {
    size_t i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        c[i] = 0.8 * b[i];
    }
}
__global__ void add_k(const double *a, const double *b, double *c, size_t n) {
    size_t i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        c[i] = a[i] + b[i];
    }
}
__global__ void triad_k(const double *a, const double *b, double *c, size_t n) {
    size_t i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        c[i] = a[i] + 0.8 * b[i];
    }
}
__global__ void dot_k(const double *a, const double *b, double *partial, size_t n) {
    extern __shared__ double tile[];  // blockDim.x doubles, sized at launch
    size_t i = blockIdx.x * blockDim.x + threadIdx.x;
    double acc = 0.0;
    if (i < n) {
        acc = a[i] * b[i];
    }
    tile[threadIdx.x] = acc;
    __syncthreads();
    if (threadIdx.x == 0) {
        double sum = 0.0;
        for (unsigned t = 0; t < blockDim.x; ++t) {
            sum += tile[t];
        }
        partial[blockIdx.x] = sum;
    }
}

template <typename Fn>
static double time_kernel(Fn launch, int warmup, int repeats, size_t bytes) {
    for (int i = 0; i < warmup; ++i) {
        launch();
    }
    hipDeviceSynchronize();
    const auto t0 = std::chrono::steady_clock::now();
    for (int i = 0; i < repeats; ++i) {
        launch();
    }
    hipDeviceSynchronize();
    const auto t1 = std::chrono::steady_clock::now();
    double seconds = std::chrono::duration<double>(t1 - t0).count() / repeats;
    if (seconds <= 0) {
        seconds = 1e-9;
    }
    return (static_cast<double>(bytes) / 1.0e9) / seconds;
}

int main(int argc, char **argv) {
    size_t n = 1 << 20;
    int times = 10;
    int device = 0;
    int block_size = 256;
    int warmup = 1;
    for (int i = 1; i < argc; ++i) {
        if ((!std::strcmp(argv[i], "--arraysize") || !std::strcmp(argv[i], "-s")) && i + 1 < argc) {
            n = static_cast<size_t>(std::atoll(argv[++i]));
        } else if ((!std::strcmp(argv[i], "--numtimes") || !std::strcmp(argv[i], "-n")) && i + 1 < argc) {
            times = std::max(1, std::atoi(argv[++i]));
        } else if (!std::strcmp(argv[i], "--device") && i + 1 < argc) {
            device = std::atoi(argv[++i]);
        } else if (!std::strcmp(argv[i], "--block-size") && i + 1 < argc) {
            block_size = std::atoi(argv[++i]);
        } else if (!std::strcmp(argv[i], "--warmup") && i + 1 < argc) {
            warmup = std::max(0, std::atoi(argv[++i]));
        }
    }
    if (n < 1024) {
        n = 1024;
    }
    if (block_size < 1 || block_size > 1024) {
        std::fprintf(stderr, "block_size must be from 1 to 1024 (got %d)\n", block_size);
        return 2;
    }
    if (hipSetDevice(device) != hipSuccess) {
        std::fprintf(stderr, "hipSetDevice failed\n");
        return 1;
    }
    double *a = nullptr;
    double *b = nullptr;
    double *c = nullptr;
    double *partial = nullptr;
    hipMalloc(&a, n * sizeof(double));
    hipMalloc(&b, n * sizeof(double));
    hipMalloc(&c, n * sizeof(double));
    dim3 block(static_cast<unsigned>(block_size));
    dim3 grid(static_cast<unsigned>((n + block_size - 1) / block_size));
    const size_t dot_shared = static_cast<size_t>(block_size) * sizeof(double);
    hipMalloc(&partial, grid.x * sizeof(double));
    std::vector<double> host(n, 1.0);
    hipMemcpy(a, host.data(), n * sizeof(double), hipMemcpyHostToDevice);
    hipMemcpy(b, host.data(), n * sizeof(double), hipMemcpyHostToDevice);
    const double copy = time_kernel([&]() { copy_k<<<grid, block>>>(a, c, n); }, warmup, times, 2 * n * sizeof(double));
    const double mul = time_kernel([&]() { mul_k<<<grid, block>>>(b, c, n); }, warmup, times, 2 * n * sizeof(double));
    const double add = time_kernel([&]() { add_k<<<grid, block>>>(a, b, c, n); }, warmup, times, 3 * n * sizeof(double));
    const double triad = time_kernel([&]() { triad_k<<<grid, block>>>(a, b, c, n); }, warmup, times, 3 * n * sizeof(double));
    const double dot = time_kernel([&]() { dot_k<<<grid, block, dot_shared>>>(a, b, partial, n); }, warmup, times, 2 * n * sizeof(double));
    std::printf("Copy: %.3f\nMul: %.3f\nAdd: %.3f\nTriad: %.3f\nDot: %.3f\n", copy, mul, add, triad, dot);
    hipFree(a);
    hipFree(b);
    hipFree(c);
    hipFree(partial);
    return 0;
}
