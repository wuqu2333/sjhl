package com.sjhl.worker;

import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

class ApiClient {
    private static final String TAG = "ApiClient";
    private final String baseUrl;

    ApiClient(String serverUrl) {
        this.baseUrl = serverUrl + "/api/worker";
    }

    // ── GET /api/worker/tasks ────────────────────────────
    List<JSONObject> fetchTasks() throws IOException {
        JSONObject resp = get("/tasks");
        JSONArray arr = resp.optJSONArray("tasks");
        List<JSONObject> tasks = new ArrayList<>();
        if (arr != null) {
            for (int i = 0; i < arr.length(); i++) {
                tasks.add(arr.optJSONObject(i));
            }
        }
        return tasks;
    }

    // ── GET /api/worker/state ────────────────────────────
    JSONObject fetchState() throws IOException {
        return get("/state");
    }

    // ── POST /api/worker/tasks/{id}/claim ─────────────────
    JSONObject claimTask(String taskId) throws IOException {
        return post("/tasks/" + taskId + "/claim", null);
    }

    // ── POST /api/worker/tasks/{id}/download-url ──────────
    JSONObject getDownloadUrl(String taskId) throws IOException {
        return post("/tasks/" + taskId + "/download-url", null);
    }

    // ── POST /api/worker/tasks/{id}/progress ──────────────
    void reportProgress(String taskId, long downloaded, long uploaded, long total, long speed) throws IOException {
        JSONObject body = new JSONObject();
        try {
            body.put("downloaded", downloaded);
            body.put("uploaded", uploaded);
            body.put("total", total);
            body.put("percent", total > 0 ? (int)(Math.max(uploaded, downloaded) * 100 / total) : 0);
            body.put("speed", speed);
        } catch (Exception ignored) {}
        post("/tasks/" + taskId + "/progress", body);
    }

    // ── POST /api/worker/tasks/{id}/upload-session ────────
    JSONObject getUploadSession(String taskId) throws IOException {
        return post("/tasks/" + taskId + "/upload-session", null);
    }

    // ── POST /api/worker/tasks/{id}/complete ──────────────
    void completeTask(String taskId) throws IOException {
        post("/tasks/" + taskId + "/complete", null);
    }

    // ── POST /api/worker/tasks/{id}/failed ────────────────
    void failTask(String taskId, String error) throws IOException {
        JSONObject body = new JSONObject();
        try { body.put("error", error != null ? error : "unknown error"); } catch (Exception ignored) {}
        post("/tasks/" + taskId + "/failed", body);
    }

    // ── HTTP helpers ──────────────────────────────────────
    private JSONObject get(String path) throws IOException {
        HttpURLConnection conn = open("GET", path);
        return readJson(conn);
    }

    private JSONObject post(String path, JSONObject body) throws IOException {
        HttpURLConnection conn = open("POST", path);
        if (body != null) {
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/json");
            byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
            try (OutputStream os = conn.getOutputStream()) {
                os.write(bytes);
            }
        }
        return readJson(conn);
    }

    HttpURLConnection open(String method, String path) throws IOException {
        URL url = new URL(baseUrl + path);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod(method);
        conn.setConnectTimeout(10000);
        conn.setReadTimeout(15000);
        conn.setRequestProperty("Accept", "application/json");
        return conn;
    }

    private JSONObject readJson(HttpURLConnection conn) throws IOException {
        int code = conn.getResponseCode();
        InputStream is = (code >= 200 && code < 300) ? conn.getInputStream() : conn.getErrorStream();
        if (is == null) {
            throw new IOException("HTTP " + code + " (empty body)");
        }
        BufferedReader reader = new BufferedReader(new InputStreamReader(is, StandardCharsets.UTF_8));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            sb.append(line);
        }
        reader.close();
        conn.disconnect();
        String text = sb.toString();
        if (text.isEmpty()) {
            throw new IOException("HTTP " + code + " (empty response)");
        }
        try {
            JSONObject obj = new JSONObject(text);
            if (code >= 400) {
                String detail = obj.optString("detail", text);
                throw new IOException("HTTP " + code + ": " + detail);
            }
            return obj;
        } catch (org.json.JSONException e) {
            throw new IOException("Invalid JSON: " + text);
        }
    }

    // ── Download file to local path ───────────────────────
    interface ProgressCallback {
        void onProgress(long downloaded, long total, long speed);
    }

    void downloadFile(String url, Map<String, String> headers, String destPath,
                      long resumeFrom, ProgressCallback cb) throws IOException {
        HttpURLConnection conn = null;
        InputStream is = null;
        java.io.FileOutputStream fos = null;
        long startTime = System.currentTimeMillis();
        long lastCbTime = startTime;
        long lastDownloaded = resumeFrom;
        try {
            conn = (HttpURLConnection) new URL(url).openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(15000);
            conn.setReadTimeout(60000);
            if (headers != null) {
                for (Map.Entry<String, String> e : headers.entrySet()) {
                    conn.setRequestProperty(e.getKey(), e.getValue());
                }
            }
            if (resumeFrom > 0) {
                conn.setRequestProperty("Range", "bytes=" + resumeFrom + "-");
            }

            int code = conn.getResponseCode();
            if (code != 200 && code != 206) {
                throw new IOException("Download HTTP " + code);
            }

            long total = conn.getContentLength();
            if (total > 0 && code == 206) total += resumeFrom;
            is = conn.getInputStream();
            fos = new java.io.FileOutputStream(destPath, resumeFrom > 0);
            byte[] buf = new byte[256 * 1024];
            int n;
            long dl = resumeFrom;
            while ((n = is.read(buf)) > 0) {
                fos.write(buf, 0, n);
                dl += n;
                long now = System.currentTimeMillis();
                if (cb != null && now - lastCbTime >= 3000) {
                    long elapsed = Math.max(1, now - startTime);
                    long speed = dl * 1000 / elapsed;
                    cb.onProgress(dl, total > 0 ? total : dl, speed);
                    lastCbTime = now;
                    lastDownloaded = dl;
                }
            }
        } finally {
            try { if (fos != null) fos.close(); } catch (Exception ignored) {}
            try { if (is != null) is.close(); } catch (Exception ignored) {}
            if (conn != null) conn.disconnect();
        }
    }

    // ── Upload chunk to Graph upload URL ──────────────────
    int putChunk(String uploadUrl, byte[] chunk, long start, long total) throws IOException {
        long end = start + chunk.length - 1;
        for (int attempt = 0; attempt < 4; attempt++) {
            HttpURLConnection conn = null;
            try {
                conn = (HttpURLConnection) new URL(uploadUrl).openConnection();
                conn.setRequestMethod("PUT");
                conn.setDoOutput(true);
                conn.setConnectTimeout(15000);
                conn.setReadTimeout(30000);
                conn.setRequestProperty("Content-Length", String.valueOf(chunk.length));
                conn.setRequestProperty("Content-Range", "bytes " + start + "-" + end + "/" + total);
                conn.setRequestProperty("Content-Type", "application/octet-stream");

                try (OutputStream os = conn.getOutputStream()) {
                    os.write(chunk);
                }

                int code = conn.getResponseCode();
                if (code == 200 || code == 201 || code == 202) {
                    conn.disconnect();
                    return 0; // done
                }
                if (code == 416) {
                    // already uploaded, range is beyond file
                    conn.disconnect();
                    return 0;
                }
                if (code == 423 || code == 429 || code == 500 || code == 502 || code == 503 || code == 504) {
                    if (attempt < 3) {
                        try { Thread.sleep((attempt + 1) * 1500); } catch (InterruptedException ignored) {}
                        continue;
                    }
                }
                conn.disconnect();
                throw new IOException("Chunk upload HTTP " + code);
            } finally {
                if (conn != null) conn.disconnect();
            }
        }
        throw new IOException("Chunk upload exhausted retries");
    }
}
