package com.example.tasks.exceptions;

/** Raised by Queue implementations on capacity or shutdown errors. */
public class QueueException extends TaskException {

    public QueueException(String message) {
        super(message);
    }

    public QueueException(String message, Throwable cause) {
        super(message, cause);
    }
}
