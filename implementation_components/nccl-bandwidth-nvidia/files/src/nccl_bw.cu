// File: src/nccl_bw.cu
// Description: Single-process NCCL AllReduce/AllGather/Broadcast/Reduce/ReduceScatter.
// Requires libnccl. One GPU is a real 1-rank NCCL run, not cudaMemcpy.
#include <cuda_runtime.h>
#include <nccl.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#define CUDA_OK(cmd) do { cudaError_t e = (cmd); if (e != cudaSuccess) { \
    std::fprintf(stderr, "CUDA %s\n", cudaGetErrorString(e)); return 2; } } while (0)
#define NCCL_OK(cmd) do { ncclResult_t e = (cmd); if (e != ncclSuccess) { \
    std::fprintf(stderr, "NCCL %s\n", ncclGetErrorString(e)); return 2; } } while (0)

static double elapsed_ms(cudaEvent_t a, cudaEvent_t b) {
    float ms = 0;
    cudaEventElapsedTime(&ms, a, b);
    return (double)ms;
}

int main(int argc, char **argv) {
    if (argc < 6) {
        std::fprintf(stderr, "usage: nccl_bw <bytes> <warmup> <iters> <num_gpus> <collective>\n");
        return 2;
    }
    size_t bytes = strtoull(argv[1], 0, 10);
    int warmup = atoi(argv[2]);
    int iters = atoi(argv[3]);
    int want = atoi(argv[4]);
    const char *name = argv[5];
    if (bytes < 8) bytes = 8;
    if (warmup < 0) warmup = 0;
    if (iters < 1) iters = 1;
    int available = 0;
    CUDA_OK(cudaGetDeviceCount(&available));
    if (available < 1) {
        std::fprintf(stderr, "no CUDA devices\n");
        return 2;
    }
    int ndev = want > 0 ? want : available;
    if (ndev > available) ndev = available;
    if (ndev > 8) ndev = 8;
    size_t count = bytes / sizeof(float);
    if (count < 1) count = 1;
    if (ndev > 1 && (count % (size_t)ndev) != 0) {
        count -= count % (size_t)ndev;
    }
    if (count < (size_t)ndev) count = (size_t)ndev;
    bytes = count * sizeof(float);
    std::vector<int> devs(ndev);
    std::vector<ncclComm_t> comms(ndev);
    std::vector<float *> send(ndev), recv(ndev);
    std::vector<cudaStream_t> streams(ndev);
    for (int i = 0; i < ndev; ++i) {
        devs[i] = i;
        CUDA_OK(cudaSetDevice(i));
        CUDA_OK(cudaMalloc(&send[i], bytes));
        CUDA_OK(cudaMalloc(&recv[i], bytes));
        CUDA_OK(cudaMemset(send[i], 1, bytes));
        CUDA_OK(cudaStreamCreate(&streams[i]));
    }
    NCCL_OK(ncclCommInitAll(comms.data(), ndev, devs.data()));
    auto once = [&]() -> int {
        NCCL_OK(ncclGroupStart());
        for (int i = 0; i < ndev; ++i) {
            CUDA_OK(cudaSetDevice(i));
            if (std::strcmp(name, "all_gather") == 0) {
                NCCL_OK(ncclAllGather(send[i], recv[i], count / (size_t)ndev, ncclFloat, comms[i], streams[i]));
            } else if (std::strcmp(name, "broadcast") == 0) {
                NCCL_OK(ncclBroadcast(send[i], recv[i], count, ncclFloat, 0, comms[i], streams[i]));
            } else if (std::strcmp(name, "reduce") == 0) {
                NCCL_OK(ncclReduce(send[i], recv[i], count, ncclFloat, ncclSum, 0, comms[i], streams[i]));
            } else if (std::strcmp(name, "reduce_scatter") == 0) {
                NCCL_OK(ncclReduceScatter(send[i], recv[i], count / (size_t)ndev, ncclFloat, ncclSum, comms[i], streams[i]));
            } else {
                NCCL_OK(ncclAllReduce(send[i], recv[i], count, ncclFloat, ncclSum, comms[i], streams[i]));
            }
        }
        NCCL_OK(ncclGroupEnd());
        for (int i = 0; i < ndev; ++i) CUDA_OK(cudaStreamSynchronize(streams[i]));
        return 0;
    };
    for (int i = 0; i < warmup; ++i) if (once()) return 2;
    CUDA_OK(cudaSetDevice(0));
    cudaEvent_t a, b;
    CUDA_OK(cudaEventCreate(&a));
    CUDA_OK(cudaEventCreate(&b));
    CUDA_OK(cudaEventRecord(a));
    for (int i = 0; i < iters; ++i) if (once()) return 2;
    CUDA_OK(cudaEventRecord(b));
    CUDA_OK(cudaEventSynchronize(b));
    double ms = elapsed_ms(a, b);
    double sec = ms / 1000.0;
    if (sec <= 0) sec = 1e-9;
    double algbw = (double)bytes * (double)iters / (sec * 1e9);
    // Bus bandwidth factors follow the nccl-tests convention, with bytes the
    // full buffer size: all_gather and reduce_scatter (n-1)/n, broadcast and
    // reduce 1, all_reduce (the dispatch default above) 2(n-1)/n. The
    // collector publishes all_reduce only, so its headline is unchanged.
    double busbw = algbw;
    if (ndev > 1) {
        if (std::strcmp(name, "all_gather") == 0 || std::strcmp(name, "reduce_scatter") == 0) {
            busbw = algbw * (double)(ndev - 1) / (double)ndev;
        } else if (std::strcmp(name, "broadcast") == 0 || std::strcmp(name, "reduce") == 0) {
            busbw = algbw;
        } else {
            busbw = algbw * 2.0 * (ndev - 1) / (double)ndev;
        }
    }
    double latency_us = (sec / (double)iters) * 1e6;
    std::printf("collective=%s num_gpus=%d bytes=%zu algbw_gb_s=%.6f busbw_gb_s=%.6f latency_us=%.6f\n",
                name, ndev, bytes, algbw, busbw, latency_us);
    for (int i = 0; i < ndev; ++i) {
        ncclCommDestroy(comms[i]);
        cudaSetDevice(i);
        cudaFree(send[i]);
        cudaFree(recv[i]);
        cudaStreamDestroy(streams[i]);
    }
    return 0;
}
