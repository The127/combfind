package com.example.tasks.worker;

import com.example.tasks.model.Task;
import com.example.tasks.model.TaskState;
import com.example.tasks.queue.Queue;
import com.example.tasks.store.Store;

/** Pulls Tasks off a Queue and executes them, persisting state via Store. */
public class Worker implements Runnable {

    private final int id;
    private final Queue<Task> queue;
    private final Store<Task> store;
    private volatile boolean running = true;

    public Worker(int id, Queue<Task> queue, Store<Task> store) {
        this.id = id;
        this.queue = queue;
        this.store = store;
    }

    @Override
    public void run() {
        while (running) {
            Task t = queue.poll();
            if (t == null) {
                sleep(10);
                continue;
            }
            execute(t);
        }
    }

    /** Execute a single Task synchronously. */
    public void execute(Task task) {
        task.transition(TaskState.RUNNING);
        try {
            // simulated work
            task.transition(TaskState.SUCCEEDED);
        } catch (Exception e) {
            task.transition(TaskState.FAILED);
        } finally {
            store.put(task.id().toString(), task);
        }
    }

    public void stop() {
        this.running = false;
    }

    public int id() {
        return id;
    }

    private static void sleep(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
