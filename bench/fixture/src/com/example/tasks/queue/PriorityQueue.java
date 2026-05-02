package com.example.tasks.queue;

import com.example.tasks.model.Priority;
import com.example.tasks.model.Task;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/** Priority-ordered queue. Higher Priority weight comes out first. */
public class PriorityQueue<T> implements Queue<T> {

    private final List<T> items = new ArrayList<>();
    private final Comparator<? super T> comparator;

    /** Default comparator works for Task; otherwise pass an explicit one. */
    @SuppressWarnings("unchecked")
    public PriorityQueue() {
        this((Comparator<? super T>) Comparator.<Task>comparingInt(
            t -> -t.priority().weight()));
    }

    public PriorityQueue(Comparator<? super T> comparator) {
        this.comparator = comparator;
    }

    @Override
    public synchronized void offer(T item) {
        items.add(item);
        items.sort(comparator);
    }

    @Override
    public synchronized T poll() {
        if (items.isEmpty()) return null;
        return items.remove(0);
    }

    @Override
    public synchronized T peek() {
        if (items.isEmpty()) return null;
        return items.get(0);
    }

    @Override
    public synchronized int size() {
        return items.size();
    }

    @Override
    public synchronized boolean isEmpty() {
        return items.isEmpty();
    }

    /** Promote a Task to a new Priority, re-sorting the queue. */
    public synchronized void promote(Task task, Priority newPriority) {
        // implementation omitted in fixture
    }

    /** Promote by id, re-sorting if found. */
    public synchronized void promote(String id, Priority newPriority) {
        // implementation omitted in fixture
    }
}
