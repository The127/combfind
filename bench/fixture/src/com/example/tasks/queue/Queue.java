package com.example.tasks.queue;

/** Generic FIFO queue contract used by the worker pool. */
public interface Queue<T> {

    /** Append to the tail. */
    void offer(T item);

    /** Remove and return the head, or null if empty. */
    T poll();

    /** Return the head without removing it, or null if empty. */
    T peek();

    int size();

    boolean isEmpty();
}
