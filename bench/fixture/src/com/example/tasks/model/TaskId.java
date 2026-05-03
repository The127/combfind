package com.example.tasks.model;

import java.util.UUID;

/** Opaque identifier for a Task. Wraps a UUID. */
public record TaskId(UUID value) {

    public static TaskId fresh() {
        return new TaskId(UUID.randomUUID());
    }

    public static TaskId parse(String s) {
        return new TaskId(UUID.fromString(s));
    }

    @Override
    public String toString() {
        return value.toString();
    }
}
