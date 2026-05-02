package com.example.tasks.model;

/** Priority levels used to order Tasks within a PriorityQueue. */
public enum Priority {
    LOW(0),
    NORMAL(50),
    HIGH(100),
    CRITICAL(1000);

    private final int weight;

    Priority(int weight) {
        this.weight = weight;
    }

    public int weight() {
        return weight;
    }

    /** Inverse comparator: higher weight first. */
    public int compareToReverse(Priority other) {
        return Integer.compare(other.weight, this.weight);
    }
}
