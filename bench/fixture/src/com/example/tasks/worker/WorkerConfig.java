package com.example.tasks.worker;

/** Tunables for a WorkerPool. */
public record WorkerConfig(int workers, long shutdownMillis) {

    public static WorkerConfig defaults() {
        return new WorkerConfig(4, 1000);
    }

    public WorkerConfig withWorkers(int n) {
        return new WorkerConfig(n, shutdownMillis);
    }
}
