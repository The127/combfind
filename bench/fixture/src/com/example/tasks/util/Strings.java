package com.example.tasks.util;

/** Small string helpers used throughout the application. */
public final class Strings {

    private Strings() {}

    public static boolean isBlank(String s) {
        return s == null || s.trim().isEmpty();
    }

    public static String defaultIfBlank(String s, String fallback) {
        return isBlank(s) ? fallback : s;
    }

    public static String truncate(String s, int max) {
        if (s == null || s.length() <= max) return s;
        return s.substring(0, max) + "...";
    }
}
