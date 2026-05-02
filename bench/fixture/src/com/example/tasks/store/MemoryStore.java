package com.example.tasks.store;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

/** In-memory Store backed by a synchronized LinkedHashMap. */
public class MemoryStore<V> implements Store<V> {

    private final Map<String, V> data = new LinkedHashMap<>();

    @Override
    public synchronized void put(String key, V value) {
        data.put(key, value);
    }

    /** Bulk put; convenience overload. */
    public synchronized void put(Map<String, V> entries) {
        data.putAll(entries);
    }

    @Override
    public synchronized Optional<V> get(String key) {
        return Optional.ofNullable(data.get(key));
    }

    @Override
    public synchronized boolean delete(String key) {
        return data.remove(key) != null;
    }

    @Override
    public synchronized int size() {
        return data.size();
    }

    @Override
    public synchronized Iterable<V> values() {
        return new java.util.ArrayList<>(data.values());
    }
}
