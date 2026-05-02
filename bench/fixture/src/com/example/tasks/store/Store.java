package com.example.tasks.store;

import java.util.Optional;

/** Persistence contract: keyed get/put/delete with optional bulk read. */
public interface Store<V> {

    void put(String key, V value);

    Optional<V> get(String key);

    boolean delete(String key);

    int size();

    /** Iterate values in insertion order. */
    Iterable<V> values();
}
