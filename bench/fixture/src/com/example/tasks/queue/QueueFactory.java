package com.example.tasks.queue;

import com.example.tasks.model.Task;

/** Constructs Queue<Task> implementations by name. */
public final class QueueFactory {

    private QueueFactory() {}

    public static Queue<Task> create(String kind) {
        return switch (kind) {
            case "concurrent" -> new ConcurrentQueue<>();
            case "priority" -> new PriorityQueue<>();
            default -> throw new IllegalArgumentException("unknown queue kind: " + kind);
        };
    }

    /** Convenience overload: default to "concurrent". */
    public static Queue<Task> create() {
        return create("concurrent");
    }
}
