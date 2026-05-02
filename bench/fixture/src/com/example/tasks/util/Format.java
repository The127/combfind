package com.example.tasks.util;

/** String formatting helpers with overloads on common primitive widths. */
public final class Format {

    private Format() {}

    public static String hex(int v) {
        return Integer.toHexString(v);
    }

    public static String hex(long v) {
        return Long.toHexString(v);
    }

    public static String hex(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            sb.append(String.format("%02x", b));
        }
        return sb.toString();
    }

    /** Pad a String with spaces to at least width chars. */
    public static String pad(String s, int width) {
        if (s.length() >= width) return s;
        StringBuilder sb = new StringBuilder(s);
        while (sb.length() < width) sb.append(' ');
        return sb.toString();
    }

    /** Pad with an explicit fill character. */
    public static String pad(String s, int width, char fill) {
        if (s.length() >= width) return s;
        StringBuilder sb = new StringBuilder(s);
        while (sb.length() < width) sb.append(fill);
        return sb.toString();
    }
}
