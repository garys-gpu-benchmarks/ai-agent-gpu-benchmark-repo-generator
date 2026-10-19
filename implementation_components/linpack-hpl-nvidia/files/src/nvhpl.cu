// File: src/nvhpl.cu
// Description: Single-GPU FP64 Linpack (PA=LU, solve) using cuSOLVER. Host length is size_t.
#include <cuda_runtime.h>
#include <cusolverDn.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <vector>
#include <chrono>

#define CUDA_OK(cmd) do { cudaError_t e = (cmd); if (e != cudaSuccess) { \
    std::fprintf(stderr, "CUDA %s\n", cudaGetErrorString(e)); return 1; } } while (0)
#define SOLVER_OK(cmd) do { cusolverStatus_t e = (cmd); if (e != CUSOLVER_STATUS_SUCCESS) { \
    std::fprintf(stderr, "cuSOLVER status %d\n", (int)e); return 1; } } while (0)

int main(int argc, char **argv) {
    int n = 4096, nb = 256, p = 1, q = 1, pfact = 2;
    for (int i = 1; i < argc; i++) {
        if (!std::strcmp(argv[i], "--N") && i + 1 < argc) n = std::atoi(argv[++i]);
        else if (!std::strcmp(argv[i], "--NB") && i + 1 < argc) nb = std::atoi(argv[++i]);
        else if (!std::strcmp(argv[i], "--P") && i + 1 < argc) p = std::atoi(argv[++i]);
        else if (!std::strcmp(argv[i], "--Q") && i + 1 < argc) q = std::atoi(argv[++i]);
        else if (!std::strcmp(argv[i], "--pfact") && i + 1 < argc) pfact = std::atoi(argv[++i]);
    }
    if (n < 16) n = 16;
    if (nb < 1) nb = 256;
    const size_t n64 = static_cast<size_t>(n);
    const size_t nn = n64 * n64;
    const size_t bytes = nn * sizeof(double);
    CUDA_OK(cudaSetDevice(0));
    cudaDeviceProp prop;
    CUDA_OK(cudaGetDeviceProperties(&prop, 0));
    // FP64 peak = SMs x FP64 flops/clock/SM x boost clock. An FMA counts as 2 flops.
    // cuSOLVER DGETRF is DGEMM-bound and uses FP64 tensor cores (DMMA) where present,
    // so percent-of-peak is reported against the tensor-core peak. Unknown archs print
    // 0 and the collector leaves percent-of-peak blank instead of guessing.
    int clock_khz = 0;
    if (cudaDeviceGetAttribute(&clock_khz, cudaDevAttrClockRate, 0) != cudaSuccess) clock_khz = 0;
    const double clock_ghz = clock_khz / 1.0e6;
    double vec_per_sm = 0.0, tc_per_sm = 0.0;
    if (prop.major == 9)                           { vec_per_sm = 128.0; tc_per_sm = 256.0; }  // Hopper H100/H200: 34/67 TF SXM, 30/60 TF NVL
    else if (prop.major == 8 && prop.minor == 0)   { vec_per_sm = 64.0;  tc_per_sm = 128.0; }  // A100/A30: 9.7/19.5 TF A100
    const double sms = static_cast<double>(prop.multiProcessorCount);
    const double peak_vector_tflops = sms * vec_per_sm * clock_ghz / 1000.0;
    const double peak_tflops = sms * tc_per_sm * clock_ghz / 1000.0;
    cusolverDnHandle_t handle;
    SOLVER_OK(cusolverDnCreate(&handle));
    std::vector<double> host_a(nn), host_b(n64), host_x(n64);
    for (size_t i = 0; i < n64; i++) {
        host_b[i] = 1.0;
        for (size_t j = 0; j < n64; j++) {
            host_a[j * n64 + i] = ((i == j) ? static_cast<double>(n64) : 0.1);
        }
    }
    double *dA = nullptr, *dB = nullptr, *dwork = nullptr;
    int *dipiv = nullptr, *dinfo = nullptr, lwork = 0;
    CUDA_OK(cudaMalloc(&dA, bytes));
    CUDA_OK(cudaMalloc(&dB, n64 * sizeof(double)));
    CUDA_OK(cudaMalloc(&dipiv, n64 * sizeof(int)));
    CUDA_OK(cudaMalloc(&dinfo, sizeof(int)));
    CUDA_OK(cudaMemcpy(dA, host_a.data(), bytes, cudaMemcpyHostToDevice));
    CUDA_OK(cudaMemcpy(dB, host_b.data(), n64 * sizeof(double), cudaMemcpyHostToDevice));
    SOLVER_OK(cusolverDnDgetrf_bufferSize(handle, n, n, dA, n, &lwork));
    CUDA_OK(cudaMalloc(&dwork, (size_t)lwork * sizeof(double)));
    CUDA_OK(cudaDeviceSynchronize());
    auto t0 = std::chrono::steady_clock::now();
    SOLVER_OK(cusolverDnDgetrf(handle, n, n, dA, n, dwork, dipiv, dinfo));
    SOLVER_OK(cusolverDnDgetrs(handle, CUBLAS_OP_N, n, 1, dA, n, dipiv, dB, n, dinfo));
    CUDA_OK(cudaDeviceSynchronize());
    auto t1 = std::chrono::steady_clock::now();
    double seconds = std::chrono::duration<double>(t1 - t0).count();
    if (seconds <= 0) seconds = 1e-6;
    CUDA_OK(cudaMemcpy(host_x.data(), dB, n64 * sizeof(double), cudaMemcpyDeviceToHost));
    int info = 0;
    CUDA_OK(cudaMemcpy(&info, dinfo, sizeof(int), cudaMemcpyDeviceToHost));
    double resid = 0.0, xnorm = 0.0;
    for (size_t i = 0; i < n64; i++) {
        double acc = -host_b[i];
        for (size_t j = 0; j < n64; j++) acc += host_a[j * n64 + i] * host_x[j];
        resid += acc * acc;
        xnorm += host_x[i] * host_x[i];
    }
    resid = std::sqrt(resid);
    xnorm = std::sqrt(xnorm);
    double thresh = 16.0 * static_cast<double>(n64) * 2.22e-16 * (xnorm + 1.0);
    int passed = (info == 0 && resid <= thresh) ? 1 : 0;
    double flops = (2.0 / 3.0) * static_cast<double>(n64) * static_cast<double>(n64) * static_cast<double>(n64);
    double gflops = flops / seconds / 1.0e9;
    std::printf("peak_fp64_tflops=%.4f peak_fp64_vector_tflops=%.4f sm_arch=%d.%d sm_count=%d clock_ghz=%.3f problem_size_N=%d block_size=%d\n",
                peak_tflops, peak_vector_tflops, prop.major, prop.minor, prop.multiProcessorCount, clock_ghz, n, nb);
    std::printf("T/V                N    NB     P     Q               Time                 Gflops\n");
    std::printf("WR10R%dR2        %d   %d     %d     %d               %.4f              %.3e\n",
                pfact, n, nb, p, q, seconds, gflops);
    std::printf("Final Score:    %.4e GFLOPS\n", gflops);
    std::printf("Residual Check: %s  residual=%.3e threshold=%.3e\n", passed ? "PASSED" : "FAILED", resid, thresh);
    cusolverDnDestroy(handle);
    cudaFree(dA);
    cudaFree(dB);
    cudaFree(dwork);
    cudaFree(dipiv);
    cudaFree(dinfo);
    return passed ? 0 : 1;
}
