package com.example.tasks.store;

import java.nio.file.Path;
import java.util.Optional;

/** File-backed Store stub. Implementation deferred. */
public class FileStore<V> implements Store<V> {

    private final Path root;

    public FileStore(Path root) {
        this.root = root;
    }

    public FileStore(String root) {
        this(Path.of(root));
    }

    @Override
    public void put(String key, V value) {
        throw new UnsupportedOperationException("file store: not implemented");
    }

    @Override
    public Optional<V> get(String key) {
        return Optional.empty();
    }

    @Override
    public boolean delete(String key) {
        return false;
    }

    @Override
    public int size() {
        return 0;
    }

    @Override
    public Iterable<V> values() {
        return java.util.Collections.emptyList();
    }

    public Path root() {
        return root;
    }
}
