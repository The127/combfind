package com.example.tasks.model;

/** Lifecycle states of a Task. Transitions are restricted to a small DAG. */
public enum TaskState {
    PENDING,
    RUNNING,
    SUCCEEDED,
    FAILED,
    CANCELLED;

    /** True if this state can legally transition to next. */
    public boolean canTransitionTo(TaskState next) {
        return switch (this) {
            case PENDING -> next == RUNNING || next == CANCELLED;
            case RUNNING -> next == SUCCEEDED || next == FAILED || next == CANCELLED;
            case SUCCEEDED, FAILED, CANCELLED -> false;
        };
    }

    public boolean isTerminal() {
        return this == SUCCEEDED || this == FAILED || this == CANCELLED;
    }
}
