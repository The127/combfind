package com.example.tasks.worker;

import com.example.tasks.model.Task;
import com.example.tasks.queue.Queue;
import com.example.tasks.store.Store;

import java.util.ArrayList;
import java.util.List;

/** A fixed-size pool of Workers sharing a Queue and Store. */
public class WorkerPool {

    private final Queue<Task> queue;
    private final Store<Task> store;
    private final WorkerConfig config;
    private final List<Worker> workers = new ArrayList<>();
    private final List<Thread> threads = new ArrayList<>();

    public WorkerPool(Queue<Task> queue, Store<Task> store, WorkerConfig config) {
        this.queue = queue;
        this.store = store;
        this.config = config;
    }

    /** Spawn the configured number of workers. */
    public void start() {
        for (int i = 0; i < config.workers(); i++) {
            Worker w = new Worker(i, queue, store);
            workers.add(w);
            Thread t = new Thread(w, "worker-" + i);
            threads.add(t);
            t.start();
        }
    }

    /** Signal all workers to stop and join their threads. */
    public void stop() {
        for (Worker w : workers) {
            w.stop();
        }
        for (Thread t : threads) {
            try {
                t.join(config.shutdownMillis());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
    }

    public int activeCount() {
        return workers.size();
    }
}
