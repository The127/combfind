package com.example.tasks.util;

/** Overloaded numeric helpers. Useful for exercising overload-aware reparse. */
public final class Math {

    private Math() {}

    /** Sum two ints. */
    public static int add(int a, int b) {
        return a + b;
    }

    /** Sum two longs. */
    public static long add(long a, long b) {
        return a + b;
    }

    /** Sum two doubles. */
    public static double add(double a, double b) {
        return a + b;
    }

    /** Sum three ints. */
    public static int add(int a, int b, int c) {
        return a + b + c;
    }

    public static int max(int a, int b) {
        return a >= b ? a : b;
    }

    public static long max(long a, long b) {
        return a >= b ? a : b;
    }

    public static double max(double a, double b) {
        return a >= b ? a : b;
    }
}
