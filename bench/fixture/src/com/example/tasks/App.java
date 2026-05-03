package com.example.tasks;

import com.example.tasks.queue.ConcurrentQueue;
import com.example.tasks.queue.Queue;
import com.example.tasks.model.Task;
import com.example.tasks.worker.WorkerPool;
import com.example.tasks.worker.WorkerConfig;
import com.example.tasks.store.MemoryStore;
import com.example.tasks.store.Store;

/** Application entry point. Wires queue, worker pool, and store. */
public final class App {

    private final Queue<Task> queue;
    private final WorkerPool pool;
    private final Store<Task> store;

    public App(Queue<Task> queue, WorkerPool pool, Store<Task> store) {
        this.queue = queue;
        this.pool = pool;
        this.store = store;
    }

    /** Start workers and accept submissions until shutdown. */
    public void start() {
        pool.start();
    }

    /** Drain the queue and stop workers. */
    public void stop() {
        pool.stop();
    }

    public static void main(String[] args) {
        Queue<Task> q = new ConcurrentQueue<>();
        Store<Task> s = new MemoryStore<>();
        WorkerConfig cfg = new WorkerConfig(4, 1000);
        WorkerPool p = new WorkerPool(q, s, cfg);
        App app = new App(q, p, s);
        app.start();
    }
}
