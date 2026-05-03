package com.example.tasks.exceptions;

/** Base for any error originating from the Task subsystem. */
public class TaskException extends RuntimeException {

    public TaskException(String message) {
        super(message);
    }

    public TaskException(String message, Throwable cause) {
        super(message, cause);
    }
}
