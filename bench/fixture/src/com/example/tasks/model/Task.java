package com.example.tasks.model;

import java.time.Instant;

/** A unit of work tracked through the queue and worker pool. */
public class Task {

    private final TaskId id;
    private final String payload;
    private final Priority priority;
    private TaskState state;
    private Instant createdAt;

    public Task(TaskId id, String payload) {
        this(id, payload, Priority.NORMAL);
    }

    public Task(TaskId id, String payload, Priority priority) {
        this.id = id;
        this.payload = payload;
        this.priority = priority;
        this.state = TaskState.PENDING;
        this.createdAt = Instant.now();
    }

    public TaskId id() {
        return id;
    }

    public String payload() {
        return payload;
    }

    public Priority priority() {
        return priority;
    }

    public TaskState state() {
        return state;
    }

    /** Move to a new state if the transition is valid. */
    public void transition(TaskState next) {
        if (!state.canTransitionTo(next)) {
            throw new IllegalStateException(
                "invalid transition: " + state + " -> " + next);
        }
        this.state = next;
    }

    public Instant createdAt() {
        return createdAt;
    }
}
