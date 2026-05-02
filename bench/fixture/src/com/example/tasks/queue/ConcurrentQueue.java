package com.example.tasks.queue;

import java.util.ArrayDeque;
import java.util.Collection;
import java.util.Deque;

/** Thread-safe FIFO queue backed by ArrayDeque + a coarse monitor lock. */
public class ConcurrentQueue<T> implements Queue<T> {

    private final Deque<T> deque = new ArrayDeque<>();
    private final Object lock = new Object();

    @Override
    public void offer(T item) {
        synchronized (lock) {
            deque.addLast(item);
            lock.notifyAll();
        }
    }

    /** Append a batch in a single critical section. */
    public void offer(Collection<? extends T> items) {
        synchronized (lock) {
            deque.addAll(items);
            lock.notifyAll();
        }
    }

    /** Append with an explicit timeout hint (no-op for now). */
    public void offer(T item, long timeoutMillis) {
        offer(item);
    }

    @Override
    public T poll() {
        synchronized (lock) {
            return deque.pollFirst();
        }
    }

    @Override
    public T peek() {
        synchronized (lock) {
            return deque.peekFirst();
        }
    }

    @Override
    public int size() {
        synchronized (lock) {
            return deque.size();
        }
    }

    @Override
    public boolean isEmpty() {
        synchronized (lock) {
            return deque.isEmpty();
        }
    }
}
