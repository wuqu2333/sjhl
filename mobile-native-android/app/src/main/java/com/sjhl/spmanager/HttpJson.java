package com.sjhl.spmanager;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URLEncoder;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Map;

final class HttpJson {
    private HttpJson() {
    }

    static JSONObject postForm(String url, Map<String, String> form, Map<String, String> headers) throws Exception {
        byte[] body = formEncode(form).getBytes(StandardCharsets.UTF_8);
        HttpURLConnection conn = open(url, "POST", headers);
        conn.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
        conn.setDoOutput(true);
        conn.setFixedLengthStreamingMode(body.length);
        try (OutputStream out = conn.getOutputStream()) {
            out.write(body);
        }
        return readJson(conn);
    }

    static JSONObject postJson(String url, JSONObject body, Map<String, String> headers) throws Exception {
        byte[] data = body.toString().getBytes(StandardCharsets.UTF_8);
        HttpURLConnection conn = open(url, "POST", headers);
        conn.setRequestProperty("Content-Type", "application/json");
        conn.setDoOutput(true);
        conn.setFixedLengthStreamingMode(data.length);
        try (OutputStream out = conn.getOutputStream()) {
            out.write(data);
        }
        return readJson(conn);
    }

    static JSONObject getJson(String url, Map<String, String> headers) throws Exception {
        return readJson(open(url, "GET", headers));
    }

    static JSONObject requestJson(String method, String url, JSONObject body, Map<String, String> headers) throws Exception {
        HttpURLConnection conn = open(url, method, headers);
        if (body != null) {
            byte[] data = body.toString().getBytes(StandardCharsets.UTF_8);
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setDoOutput(true);
            conn.setFixedLengthStreamingMode(data.length);
            try (OutputStream out = conn.getOutputStream()) {
                out.write(data);
            }
        }
        return readJson(conn);
    }

    static JSONObject putBytes(String url, byte[] body, int length, long start, long total) throws Exception {
        HttpURLConnection conn = open(url, "PUT", null);
        conn.setRequestProperty("Content-Length", String.valueOf(length));
        conn.setRequestProperty("Content-Range", "bytes " + start + "-" + (start + length - 1) + "/" + total);
        conn.setDoOutput(true);
        conn.setFixedLengthStreamingMode(length);
        try (OutputStream out = conn.getOutputStream()) {
            out.write(body, 0, length);
        }
        return readJson(conn);
    }

    static HttpURLConnection open(String url, String method, Map<String, String> headers) throws IOException {
        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        conn.setRequestMethod(method);
        conn.setConnectTimeout(30000);
        conn.setReadTimeout(300000);
        conn.setUseCaches(false);
        if (headers != null) {
            for (Map.Entry<String, String> entry : headers.entrySet()) {
                if (entry.getKey() != null && entry.getValue() != null) {
                    conn.setRequestProperty(entry.getKey(), entry.getValue());
                }
            }
        }
        return conn;
    }

    static JSONObject readJson(HttpURLConnection conn) throws Exception {
        int code = conn.getResponseCode();
        String text = readText(code >= 400 ? conn.getErrorStream() : conn.getInputStream());
        if (code >= 400) {
            throw new IOException("HTTP " + code + ": " + text);
        }
        if (text.trim().isEmpty()) {
            return new JSONObject();
        }
        return new JSONObject(text);
    }

    static String readText(InputStream input) throws IOException {
        if (input == null) {
            return "";
        }
        try (InputStream in = input; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int read;
            while ((read = in.read(buffer)) != -1) {
                out.write(buffer, 0, read);
            }
            return out.toString("UTF-8");
        }
    }

    private static String formEncode(Map<String, String> form) throws Exception {
        StringBuilder builder = new StringBuilder();
        for (Map.Entry<String, String> entry : form.entrySet()) {
            if (builder.length() > 0) {
                builder.append('&');
            }
            builder.append(URLEncoder.encode(entry.getKey(), "UTF-8"));
            builder.append('=');
            builder.append(URLEncoder.encode(entry.getValue() == null ? "" : entry.getValue(), "UTF-8"));
        }
        return builder.toString();
    }
}
