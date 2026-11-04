// File: src/babelstream.cu
// BabelStream-style CUDA Copy/Mul/Add/Triad/Dot kernels.
#include <cuda_runtime.h>
#include <cstdio>
#include <cstdlib>
#include <string>

#define CHECK(cmd) do { cudaError_t e = (cmd); if (e != cudaSuccess) { \
  fprintf(stderr, "CUDA error %s\n", cudaGetErrorString(e)); return 1; } } while (0)

__global__ void k_copy(const double* a, double* c, size_t n) {
    size_t i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) c[i] = a[i];
}
__global__ void k_mul(const double* b, double* c, double scalar, size_t n) {
    size_t i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) c[i] = scalar * b[i];
}
__global__ void k_add(const double* a, const double* b, double* c, size_t n) {
    size_t i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) c[i] = a[i] + b[i];
}
__global__ void k_triad(const double* a, const double* b, double* c, double scalar, size_t n) {
    size_t i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) c[i] = a[i] + scalar * b[i];
}
__global__ void k_dot(const double* a, const double* b, double* partial, size_t n) {
    extern __shared__ double sh[];  // block_size doubles, sized at launch
    size_t i = blockIdx.x * blockDim.x + threadIdx.x;
    double sum = 0;
    if (i < n) sum = a[i] * b[i];
    sh[threadIdx.x] = sum;
    __syncthreads();
    for (int s = blockDim.x / 2; s > 0; s >>= 1) {
        if ((int)threadIdx.x < s) sh[threadIdx.x] += sh[threadIdx.x + s];
        __syncthreads();
    }
    if (threadIdx.x == 0) partial[blockIdx.x] = sh[0];
}

static float elapsed(cudaEvent_t start, cudaEvent_t stop) {
    float ms = 0;
    cudaEventElapsedTime(&ms, start, stop);
    return ms;
}

int main(int argc, char** argv) {
    int device = 0;
    size_t n = 1048576;
    int block = 256;
    int warmup = 1;
    int iters = 2;
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--device" && i + 1 < argc) device = atoi(argv[++i]);
        else if (arg == "--array-size" && i + 1 < argc) n = strtoull(argv[++i], nullptr, 10);
        else if (arg == "--block-size" && i + 1 < argc) block = atoi(argv[++i]);
        else if (arg == "--warmup" && i + 1 < argc) warmup = atoi(argv[++i]);
        else if (arg == "--iters" && i + 1 < argc) iters = atoi(argv[++i]);
    }
    CHECK(cudaSetDevice(device));
    double *a = nullptr, *b = nullptr, *c = nullptr, *partial = nullptr;
    size_t bytes = n * sizeof(double);
    CHECK(cudaMalloc(&a, bytes));
    CHECK(cudaMalloc(&b, bytes));
    CHECK(cudaMalloc(&c, bytes));
    if (block < 32 || block > 1024 || (block & (block - 1)) != 0) {
        std::fprintf(stderr, "block_size must be a power of two from 32 to 1024 (got %d)\n", block);
        return 2;
    }
    if (warmup < 0) warmup = 0;
    const size_t dot_shared = static_cast<size_t>(block) * sizeof(double);
    int grid = static_cast<int>((n + block - 1) / block);
    CHECK(cudaMalloc(&partial, static_cast<size_t>(grid) * sizeof(double)));
    CHECK(cudaMemset(a, 0, bytes));
    CHECK(cudaMemset(b, 0, bytes));
    cudaEvent_t start, stop;
    CHECK(cudaEventCreate(&start));
    CHECK(cudaEventCreate(&stop));

    for (int i = 0; i < warmup; ++i) k_copy<<<grid, block>>>(a, c, n);
    CHECK(cudaGetLastError());  // kernel launches are asynchronous; surface launch failures
    CHECK(cudaDeviceSynchronize());
    CHECK(cudaEventRecord(start));
    for (int i = 0; i < iters; ++i) k_copy<<<grid, block>>>(a, c, n);
    CHECK(cudaGetLastError());
    CHECK(cudaEventRecord(stop));
    CHECK(cudaEventSynchronize(stop));
    float copy_ms = elapsed(start, stop) / static_cast<float>(iters);

    for (int i = 0; i < warmup; ++i) k_mul<<<grid, block>>>(b, c, 1.1, n);
    CHECK(cudaGetLastError());  // kernel launches are asynchronous; surface launch failures
    CHECK(cudaDeviceSynchronize());
    CHECK(cudaEventRecord(start));
    for (int i = 0; i < iters; ++i) k_mul<<<grid, block>>>(b, c, 1.1, n);
    CHECK(cudaGetLastError());
    CHECK(cudaEventRecord(stop));
    CHECK(cudaEventSynchronize(stop));
    float mul_ms = elapsed(start, stop) / static_cast<float>(iters);

    for (int i = 0; i < warmup; ++i) k_add<<<grid, block>>>(a, b, c, n);
    CHECK(cudaGetLastError());  // kernel launches are asynchronous; surface launch failures
    CHECK(cudaDeviceSynchronize());
    CHECK(cudaEventRecord(start));
    for (int i = 0; i < iters; ++i) k_add<<<grid, block>>>(a, b, c, n);
    CHECK(cudaGetLastError());
    CHECK(cudaEventRecord(stop));
    CHECK(cudaEventSynchronize(stop));
    float add_ms = elapsed(start, stop) / static_cast<float>(iters);

    for (int i = 0; i < warmup; ++i) k_triad<<<grid, block>>>(a, b, c, 1.1, n);
    CHECK(cudaGetLastError());  // kernel launches are asynchronous; surface launch failures
    CHECK(cudaDeviceSynchronize());
    CHECK(cudaEventRecord(start));
    for (int i = 0; i < iters; ++i) k_triad<<<grid, block>>>(a, b, c, 1.1, n);
    CHECK(cudaGetLastError());
    CHECK(cudaEventRecord(stop));
    CHECK(cudaEventSynchronize(stop));
    float triad_ms = elapsed(start, stop) / static_cast<float>(iters);

    for (int i = 0; i < warmup; ++i) k_dot<<<grid, block, dot_shared>>>(a, b, partial, n);
    CHECK(cudaGetLastError());  // kernel launches are asynchronous; surface launch failures
    CHECK(cudaDeviceSynchronize());
    CHECK(cudaEventRecord(start));
    for (int i = 0; i < iters; ++i) k_dot<<<grid, block, dot_shared>>>(a, b, partial, n);
    CHECK(cudaGetLastError());
    CHECK(cudaEventRecord(stop));
    CHECK(cudaEventSynchronize(stop));
    float dot_ms = elapsed(start, stop) / static_cast<float>(iters);

    auto gbps = [&](float ms, int words) {
        return (static_cast<double>(n) * words * sizeof(double) / 1e9) / (static_cast<double>(ms) / 1e3);
    };
    // No GPU sustains > 20 TB/s from device memory; a larger figure means the kernels did not run.
    const double max_plausible_gb_s = 20000.0;
    const double worst = gbps(triad_ms, 3) > gbps(copy_ms, 2) ? gbps(triad_ms, 3) : gbps(copy_ms, 2);
    if (!(worst > 0.0) || worst > max_plausible_gb_s) {
        fprintf(stderr, "implausible bandwidth %.1f GB/s (triad_time_ms=%.6f): kernels did not execute\n", worst, triad_ms);
        return 2;
    }
    printf("array_size=%zu\n", n);
    printf("copy_bandwidth_gb_s=%.6f\n", gbps(copy_ms, 2));
    printf("mul_bandwidth_gb_s=%.6f\n", gbps(mul_ms, 2));
    printf("add_bandwidth_gb_s=%.6f\n", gbps(add_ms, 3));
    printf("triad_bandwidth_gb_s=%.6f\n", gbps(triad_ms, 3));
    printf("dot_bandwidth_gb_s=%.6f\n", gbps(dot_ms, 2));
    printf("triad_time_ms=%.6f\n", triad_ms);
    CHECK(cudaFree(a));
    CHECK(cudaFree(b));
    CHECK(cudaFree(c));
    CHECK(cudaFree(partial));
    return 0;
}
