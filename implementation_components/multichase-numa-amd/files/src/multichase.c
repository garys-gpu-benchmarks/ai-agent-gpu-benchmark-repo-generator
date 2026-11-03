/* Git-compiled C (not C++) multichase pointer-chase for workload 109/309.
 * gcc -O2 must not dead-code-eliminate the chase. Load each next pointer
 * through a volatile pointer so baseline 1.33e9 iters report real ns/load.
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <pthread.h>

static uint64_t now_ns(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static void *chase(void *start, unsigned long long n) {
  void *p = start;
  for (unsigned long long i = 0; i < n; i++) {
    p = *(void * volatile *)p;
  }
  return p;
}

struct chase_job {
  void *start;
  unsigned long long n;
  void *result;
};

static void *chase_start(void *arg) {
  struct chase_job *job = (struct chase_job *)arg;
  job->result = chase(job->start, job->n);
  return NULL;
}

int main(int argc, char **argv) {
  if (argc < 5) {
    fprintf(stderr, "usage: multichase <bytes> <stride> <iters> <warmup>\n");
    return 2;
  }
  size_t bytes = (size_t)strtoull(argv[1], NULL, 10);
  size_t stride = (size_t)strtoull(argv[2], NULL, 10);
  unsigned long long iters = strtoull(argv[3], NULL, 10);
  unsigned long long warmup = strtoull(argv[4], NULL, 10);
  int threads = argc >= 6 ? atoi(argv[5]) : 1;
  if (threads < 1) threads = 1;
  if (stride < sizeof(void *)) stride = sizeof(void *);
  if (bytes < stride * 8) bytes = stride * 8;
  size_t n = bytes / sizeof(void *);
  void **buf = (void **)aligned_alloc(64, n * sizeof(void *));
  if (!buf) return 3;
  size_t step = stride / sizeof(void *);
  if (step == 0) step = 1;
  size_t *order = (size_t *)malloc(n * sizeof(size_t));
  if (!order) {
    free(buf);
    return 3;
  }
  for (size_t i = 0; i < n; i++) order[i] = i;
  uint64_t rng = 0x9e3779b97f4a7c15ull;
  for (size_t i = n; i > 1; i--) {
    rng = rng * 6364136223846793005ull + 1ull;
    size_t j = (size_t)((rng >> 11) % i);
    size_t tmp = order[i - 1];
    order[i - 1] = order[j];
    order[j] = tmp;
  }
  for (size_t i = 0; i < n; i++) {
    size_t nxt = (i + step) % n;
    buf[order[i]] = &buf[order[nxt]];
  }
  void *p = chase(buf[0], warmup);
  uint64_t t0 = now_ns();
  if (threads == 1) {
    p = chase(p, iters);
  } else {
    pthread_t *handles = (pthread_t *)calloc((size_t)threads, sizeof(pthread_t));
    struct chase_job *jobs = (struct chase_job *)calloc((size_t)threads, sizeof(struct chase_job));
    if (!handles || !jobs) return 3;
    for (int t = 0; t < threads; t++) {
      jobs[t].start = buf[0];
      jobs[t].n = iters;
      pthread_create(&handles[t], NULL, chase_start, &jobs[t]);
    }
    for (int t = 0; t < threads; t++) pthread_join(handles[t], NULL);
    p = jobs[0].result;
    free(handles);
    free(jobs);
  }
  uint64_t t1 = now_ns();
  if ((uintptr_t)p == 1ull) {
    fputc('x', stderr);
  }
  double latency = (double)(t1 - t0) / (double)(iters ? iters : 1);
  printf("latency_ns %.6f\n", latency);
  free(order);
  free(buf);
  return latency > 0.0 ? 0 : 4;
}
