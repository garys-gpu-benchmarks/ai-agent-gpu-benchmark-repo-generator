// File: src/rochpl.cpp
// Description: Single-GPU FP64 Linpack (PA=LU, Ly=Pb, Ux=y) using rocSOLVER.
// Host matrix length must be size_t. Signed 32-bit n*n overflows at N=65536
// (65536^2 == 2^32), which is the workbook extended problem_size_N.
#include <hip/hip_runtime.h>
#include <rocblas/rocblas.h>
#include <rocsolver/rocsolver.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <vector>
#include <string>
#include <chrono>

#define HIP_OK(cmd) do { hipError_t e=(cmd); if(e!=hipSuccess){ std::fprintf(stderr,"HIP %s\n", hipGetErrorString(e)); return 1; } } while(0)
#define BLAS_OK(cmd) do { rocblas_status e=(cmd); if(e!=rocblas_status_success){ std::fprintf(stderr,"rocBLAS/rocSOLVER status %d\n", (int)e); return 1; } } while(0)

int main(int argc, char** argv) {
    // One dense LU solve on one GPU. The solver library picks its own blocking
    // and panel factorization, so only N is an input. --NB, --P, --Q and
    // --pfact are still accepted (and ignored) so an older command line runs.
    int n = 4096;
    for (int i = 1; i < argc; i++) {
        if (!std::strcmp(argv[i], "--N") && i + 1 < argc) n = std::atoi(argv[++i]);
        else if ((!std::strcmp(argv[i], "--NB") || !std::strcmp(argv[i], "--P") ||
                  !std::strcmp(argv[i], "--Q") || !std::strcmp(argv[i], "--pfact")) && i + 1 < argc) ++i;
    }
    if (n < 16) n = 16;
    const size_t n64 = static_cast<size_t>(n);
    const size_t nn = n64 * n64;
    const size_t bytes = nn * sizeof(double);
    HIP_OK(hipSetDevice(0));
    rocblas_handle handle;
    BLAS_OK(rocblas_create_handle(&handle));
    std::vector<double> host_a(nn), host_b(n64), host_x(n64);
    for (size_t i = 0; i < n64; i++) {
        host_b[i] = 1.0;
        for (size_t j = 0; j < n64; j++) {
            host_a[j * n64 + i] = ((i == j) ? static_cast<double>(n64) : 0.1);
        }
    }
    double *dA = nullptr, *dB = nullptr;
    rocblas_int *dipiv = nullptr, *dinfo = nullptr;
    HIP_OK(hipMalloc(&dA, bytes));
    HIP_OK(hipMalloc(&dB, n64 * sizeof(double)));
    HIP_OK(hipMalloc(&dipiv, n64 * sizeof(rocblas_int)));
    HIP_OK(hipMalloc(&dinfo, sizeof(rocblas_int)));
    HIP_OK(hipMemcpy(dA, host_a.data(), bytes, hipMemcpyHostToDevice));
    HIP_OK(hipMemcpy(dB, host_b.data(), n64 * sizeof(double), hipMemcpyHostToDevice));
    HIP_OK(hipDeviceSynchronize());
    auto t0 = std::chrono::steady_clock::now();
    BLAS_OK(rocsolver_dgetrf(handle, n, n, dA, n, dipiv, dinfo));
    BLAS_OK(rocsolver_dgetrs(handle, rocblas_operation_none, n, 1, dA, n, dipiv, dB, n));
    HIP_OK(hipDeviceSynchronize());
    auto t1 = std::chrono::steady_clock::now();
    double seconds = std::chrono::duration<double>(t1 - t0).count();
    if (seconds <= 0) seconds = 1e-6;
    HIP_OK(hipMemcpy(host_x.data(), dB, n64 * sizeof(double), hipMemcpyDeviceToHost));
    rocblas_int info = 0;
    HIP_OK(hipMemcpy(&info, dinfo, sizeof(rocblas_int), hipMemcpyDeviceToHost));
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
    const double peak = 163.4;
    std::printf("peak_fp64_tflops=%.1f problem_size_N=%d\n", peak, n);
    std::printf("RESULT problem_size_N=%d time_s=%.4f gflops=%.3e\n", n, seconds, gflops);
    std::printf("Final Score:    %.4e GFLOPS\n", gflops);
    std::printf("Residual Check: %s  residual=%.3e threshold=%.3e\n", passed ? "PASSED" : "FAILED", resid, thresh);
    rocblas_destroy_handle(handle);
    hipFree(dA);
    hipFree(dB);
    hipFree(dipiv);
    hipFree(dinfo);
    return passed ? 0 : 1;
}
