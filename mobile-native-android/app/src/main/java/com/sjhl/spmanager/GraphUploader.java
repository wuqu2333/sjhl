package com.sjhl.spmanager;

import org.json.JSONObject;
import org.json.JSONArray;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URLEncoder;
import java.util.HashMap;
import java.util.Map;

final class GraphUploader {
    private static final String DEFAULT_GRAPH_BASE = "https://microsoftgraph.chinacloudapi.cn/v1.0";
    private static final String DEFAULT_AUTH_BASE = "https://login.partner.microsoftonline.cn";
    private static final int GRAPH_CHUNK_UNIT = 320 * 1024;
    private static final int GRAPH_MAX_CHUNK_SIZE = 191 * GRAPH_CHUNK_UNIT;
    private static final int SMALL_CHUNK_SIZE = 20 * 1024 * 1024;
    private static final int MID_CHUNK_SIZE = 40 * 1024 * 1024;

    JSONObject driveInfo(JSONObject profile) throws Exception {
        String driveId = required(profile, "driveId", "SP Drive ID 不能为空");
        return request(profile, "GET", "/drives/" + encode(driveId), null);
    }

    JSONArray listChildren(JSONObject profile, String remoteDir) throws Exception {
        String driveId = required(profile, "driveId", "SP Drive ID 不能为空");
        String cleanDir = cleanPath(joinPath(profile.optString("rootPath"), remoteDir, ""));
        String path = cleanDir.isEmpty()
                ? "/drives/" + encode(driveId) + "/root/children"
                : "/drives/" + encode(driveId) + "/root:/" + encodePath(cleanDir) + ":/children";
        JSONArray items = new JSONArray();
        String next = path;
        while (next != null && !next.isEmpty()) {
            JSONObject payload = request(profile, "GET", next, null);
            JSONArray value = payload.optJSONArray("value");
            for (int i = 0; value != null && i < value.length(); i++) {
                JSONObject raw = value.optJSONObject(i);
                if (raw == null) {
                    continue;
                }
                JSONObject item = new JSONObject();
                item.put("id", raw.optString("id"));
                item.put("name", raw.optString("name"));
                item.put("path", joinPath(remoteDir, raw.optString("name"), ""));
                item.put("type", raw.has("folder") ? "folder" : "file");
                item.put("size", raw.optLong("size"));
                item.put("childCount", raw.optJSONObject("folder") == null ? 0 : raw.optJSONObject("folder").optInt("childCount"));
                item.put("lastModifiedDateTime", raw.optString("lastModifiedDateTime"));
                item.put("webUrl", raw.optString("webUrl"));
                JSONObject file = raw.optJSONObject("file");
                JSONObject hashes = file == null ? null : file.optJSONObject("hashes");
                item.put("sha1", hashes == null ? "" : hashes.optString("sha1Hash"));
                item.put("quickXorHash", hashes == null ? "" : hashes.optString("quickXorHash"));
                items.put(item);
            }
            next = payload.optString("@odata.nextLink", "");
        }
        return items;
    }

    JSONArray scanTree(JSONObject profile, String remoteDir) throws Exception {
        JSONArray files = new JSONArray();
        scanInto(profile, remoteDir == null ? "" : remoteDir, files);
        return files;
    }

    JSONArray discoverSharePointDrives(JSONObject connection, String search, boolean documentsOnly) throws Exception {
        JSONArray sites = discoverSharePointSites(connection, search);
        JSONArray result = new JSONArray();
        for (int i = 0; i < sites.length(); i++) {
            JSONObject site = sites.optJSONObject(i);
            if (site == null || isExcludedDiscoverySite(site)) {
                continue;
            }
            String siteId = site.optString("id");
            if (siteId.isEmpty()) {
                continue;
            }
            String next = "/sites/" + encode(siteId) + "/drives";
            while (next != null && !next.isEmpty()) {
                JSONObject payload = request(connection, "GET", next, null);
                JSONArray drives = payload.optJSONArray("value");
                for (int j = 0; drives != null && j < drives.length(); j++) {
                    JSONObject drive = drives.optJSONObject(j);
                    if (drive == null) {
                        continue;
                    }
                    String driveType = drive.optString("driveType").toLowerCase(java.util.Locale.ROOT);
                    if (documentsOnly && !driveType.isEmpty() && !"documentlibrary".equals(driveType) && !"business".equals(driveType)) {
                        continue;
                    }
                    result.put(driveSummary(site, drive));
                }
                next = payload.optString("@odata.nextLink", "");
            }
        }
        return result;
    }

    JSONArray mountSharePointSite(JSONObject connection, String siteUrl, String libraryName, boolean documentsOnly) throws Exception {
        JSONObject site = request(connection, "GET", sharePointSiteApiPath(siteUrl), null);
        JSONArray result = new JSONArray();
        String wantedLibrary = libraryName == null ? "" : libraryName.trim().toLowerCase(java.util.Locale.ROOT);
        String next = "/sites/" + encode(site.optString("id")) + "/drives";
        while (next != null && !next.isEmpty()) {
            JSONObject payload = request(connection, "GET", next, null);
            JSONArray drives = payload.optJSONArray("value");
            for (int i = 0; drives != null && i < drives.length(); i++) {
                JSONObject drive = drives.optJSONObject(i);
                if (drive == null) {
                    continue;
                }
                String driveType = drive.optString("driveType").toLowerCase(java.util.Locale.ROOT);
                String driveName = drive.optString("name");
                if (documentsOnly && !driveType.isEmpty() && !"documentlibrary".equals(driveType) && !"business".equals(driveType)) {
                    continue;
                }
                if (!wantedLibrary.isEmpty() && !wantedLibrary.equals(driveName.toLowerCase(java.util.Locale.ROOT))) {
                    continue;
                }
                result.put(driveSummary(site, drive));
            }
            next = payload.optString("@odata.nextLink", "");
        }
        if (!wantedLibrary.isEmpty() && result.length() == 0) {
            throw new IOException("站点中未找到文档库: " + libraryName);
        }
        return result;
    }

    private JSONArray discoverSharePointSites(JSONObject connection, String search) throws Exception {
        String searchText = search == null || search.trim().isEmpty() ? "*" : search.trim();
        java.util.LinkedHashMap<String, JSONObject> deduped = new java.util.LinkedHashMap<>();
        String[] sources = new String[]{"/sites/getAllSites", "/sites?search=" + encode(searchText)};
        Exception lastError = null;
        for (String source : sources) {
            String next = source;
            while (next != null && !next.isEmpty()) {
                try {
                    JSONObject payload = request(connection, "GET", next, null);
                    JSONArray sites = payload.optJSONArray("value");
                    for (int i = 0; sites != null && i < sites.length(); i++) {
                        JSONObject site = sites.optJSONObject(i);
                        if (site == null) {
                            continue;
                        }
                        String key = site.optString("id", site.optString("webUrl"));
                        if (key.isEmpty()) {
                            continue;
                        }
                        if (!"*".equals(searchText)) {
                            String haystack = (site.optString("displayName") + " " + site.optString("name") + " " + site.optString("webUrl")).toLowerCase(java.util.Locale.ROOT);
                            if (!haystack.contains(searchText.toLowerCase(java.util.Locale.ROOT))) {
                                continue;
                            }
                        }
                        deduped.put(key, site);
                    }
                    next = payload.optString("@odata.nextLink", "");
                } catch (Exception error) {
                    lastError = error;
                    break;
                }
            }
        }
        if (deduped.isEmpty() && lastError != null) {
            throw lastError;
        }
        JSONArray result = new JSONArray();
        for (JSONObject site : deduped.values()) {
            result.put(site);
        }
        return result;
    }

    JSONObject createFolder(JSONObject profile, String remoteDir, String folderName) throws Exception {
        String name = folderName == null ? "" : folderName.trim();
        if (name.isEmpty()) {
            throw new IOException("文件夹名称不能为空");
        }
        String driveId = required(profile, "driveId", "SP Drive ID 不能为空");
        String cleanDir = cleanPath(joinPath(profile.optString("rootPath"), remoteDir, ""));
        String path = cleanDir.isEmpty()
                ? "/drives/" + encode(driveId) + "/root/children"
                : "/drives/" + encode(driveId) + "/root:/" + encodePath(cleanDir) + ":/children";
        JSONObject body = new JSONObject();
        body.put("name", name);
        body.put("folder", new JSONObject());
        body.put("@microsoft.graph.conflictBehavior", "rename");
        return request(profile, "POST", path, body);
    }

    void deleteItem(JSONObject profile, String itemId) throws Exception {
        if (itemId == null || itemId.trim().isEmpty()) {
            throw new IOException("SP Item ID 不能为空");
        }
        String driveId = required(profile, "driveId", "SP Drive ID 不能为空");
        request(profile, "DELETE", "/drives/" + encode(driveId) + "/items/" + encode(itemId), null);
    }

    JSONObject renameItem(JSONObject profile, String itemId, String newName) throws Exception {
        if (itemId == null || itemId.trim().isEmpty()) {
            throw new IOException("SP Item ID 不能为空");
        }
        String name = newName == null ? "" : newName.trim();
        if (name.isEmpty()) {
            throw new IOException("新名称不能为空");
        }
        String driveId = required(profile, "driveId", "SP Drive ID 不能为空");
        JSONObject body = new JSONObject();
        body.put("name", name);
        return request(profile, "PATCH", "/drives/" + encode(driveId) + "/items/" + encode(itemId), body);
    }

    JSONObject request(JSONObject profile, String method, String apiPath, JSONObject body) throws Exception {
        String path = apiPath == null ? "" : apiPath;
        String url = path.startsWith("http") ? path : graphBase(profile) + path;
        return HttpJson.requestJson(method, url, body, bearerHeaders(token(profile)));
    }

    String uploadInputStream(
            JSONObject profile,
            InputStream input,
            long totalSize,
            String targetDir,
            String fileName,
            ProgressCallback callback
    ) throws Exception {
        if (totalSize < 0) {
            throw new IOException("本地文件大小未知，无法创建 Graph 分片上传会话");
        }
        String remotePath = joinPath(profile.optString("rootPath"), targetDir, fileName);
        if (totalSize == 0) {
            uploadEmptyFile(profile, remotePath);
            if (callback != null) {
                callback.onProgress(0L, 0L, 0L);
            }
            return remotePath;
        }
        String uploadUrl = createUploadSession(profile, remotePath, fileName);
        uploadKnownSizeStream(input, totalSize, uploadUrl, callback, uploadChunkSize(totalSize));
        return remotePath;
    }

    String uploadFile(
            JSONObject profile,
            File file,
            long totalSize,
            String targetDir,
            String fileName,
            ProgressCallback callback
    ) throws Exception {
        try (InputStream input = new FileInputStream(file)) {
            return uploadInputStream(profile, input, totalSize, targetDir, fileName, callback);
        }
    }

    String uploadRemoteUrl(
            JSONObject profile,
            String downloadUrl,
            Map<String, String> sourceHeaders,
            long totalSize,
            String targetDir,
            String fileName,
            ProgressCallback callback
    ) throws Exception {
        if (totalSize <= 0) {
            throw new IOException("115 下载链接没有返回文件大小");
        }
        String remotePath = joinPath(profile.optString("rootPath"), targetDir, fileName);
        String uploadUrl = createUploadSession(profile, remotePath, fileName);
        long offset = 0L;
        int retry = 0;
        while (offset < totalSize) {
            HttpURLConnection conn = null;
            try {
                Map<String, String> headers = new HashMap<>();
                if (sourceHeaders != null) {
                    headers.putAll(sourceHeaders);
                }
                if (offset > 0) {
                    headers.put("Range", "bytes=" + offset + "-");
                }
                conn = HttpJson.open(downloadUrl, "GET", headers);
                int code = conn.getResponseCode();
                if (code >= 400) {
                    throw new IOException("源文件读取失败 HTTP " + code + ": " + HttpJson.readText(conn.getErrorStream()));
                }
                if (offset > 0 && code != 206) {
                    throw new IOException("源站不支持断点续读，HTTP " + code);
                }
                try (InputStream input = conn.getInputStream()) {
                    offset = uploadFromCurrentOffset(input, totalSize, uploadUrl, offset, callback, uploadChunkSize(totalSize));
                }
                retry = 0;
            } catch (Exception error) {
                if (offset >= totalSize) {
                    break;
                }
                retry++;
                if (retry > 6) {
                    throw new IOException("源文件读取中断，断点续传失败，已上传 " + offset + "/" + totalSize + ": " + error.getMessage(), error);
                }
                Thread.sleep(Math.min(30000L, retry * 3000L));
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        }
        return remotePath;
    }

    private void uploadKnownSizeStream(InputStream input, long totalSize, String uploadUrl, ProgressCallback callback, int chunkSize) throws Exception {
        long uploaded = uploadFromCurrentOffset(input, totalSize, uploadUrl, 0L, callback, chunkSize);
        if (uploaded != totalSize) {
            throw new IOException("文件读取大小不一致，已读 " + uploaded + "，预期 " + totalSize);
        }
    }

    private long uploadFromCurrentOffset(InputStream input, long totalSize, String uploadUrl, long offset, ProgressCallback callback, int chunkSize) throws Exception {
        byte[] buffer = new byte[Math.max(GRAPH_CHUNK_UNIT, chunkSize)];
        while (offset < totalSize) {
            int wanted = (int) Math.min(buffer.length, totalSize - offset);
            int read = readChunk(input, buffer, wanted);
            if (read <= 0) {
                break;
            }
            long started = System.currentTimeMillis();
            putChunkWithRetry(uploadUrl, buffer, read, offset, totalSize);
            long elapsed = Math.max(1L, System.currentTimeMillis() - started);
            long speed = read * 1000L / elapsed;
            offset += read;
            if (callback != null) {
                callback.onProgress(offset, totalSize, speed);
            }
        }
        return offset;
    }

    private int uploadChunkSize(long totalSize) {
        int size;
        if (totalSize > 0 && totalSize <= 1024L * 1024L * 1024L) {
            size = SMALL_CHUNK_SIZE;
        } else if (totalSize >= 20L * 1024L * 1024L * 1024L) {
            size = GRAPH_MAX_CHUNK_SIZE;
        } else {
            size = MID_CHUNK_SIZE;
        }
        size -= size % GRAPH_CHUNK_UNIT;
        if (size <= 0) {
            size = GRAPH_CHUNK_UNIT;
        }
        return Math.min(GRAPH_MAX_CHUNK_SIZE, size);
    }

    private void putChunkWithRetry(String uploadUrl, byte[] buffer, int length, long start, long totalSize) throws Exception {
        Exception last = null;
        for (int attempt = 0; attempt < 4; attempt++) {
            try {
                HttpJson.putBytes(uploadUrl, buffer, length, start, totalSize);
                return;
            } catch (Exception error) {
                last = error;
                Thread.sleep((attempt + 1L) * 2000L);
            }
        }
        throw last == null ? new IOException("分片上传失败") : last;
    }

    private String createUploadSession(JSONObject profile, String remotePath, String fileName) throws Exception {
        String graphBase = graphBase(profile);
        String driveId = required(profile, "driveId", "SP Drive ID 不能为空");
        String url = graphBase + "/drives/" + encode(driveId) + "/root:/" + encodePath(remotePath) + ":/createUploadSession";
        JSONObject item = new JSONObject();
        item.put("@microsoft.graph.conflictBehavior", "rename");
        item.put("name", fileName);
        JSONObject body = new JSONObject();
        body.put("item", item);
        JSONObject response = HttpJson.postJson(url, body, bearerHeaders(token(profile)));
        String uploadUrl = response.optString("uploadUrl");
        if (uploadUrl.isEmpty()) {
            throw new IOException("Graph 未返回 uploadUrl");
        }
        return uploadUrl;
    }

    private void uploadEmptyFile(JSONObject profile, String remotePath) throws Exception {
        String graphBase = graphBase(profile);
        String driveId = required(profile, "driveId", "SP Drive ID 不能为空");
        String url = graphBase + "/drives/" + encode(driveId) + "/root:/" + encodePath(remotePath)
                + ":/content?@microsoft.graph.conflictBehavior=rename";
        HttpURLConnection conn = HttpJson.open(url, "PUT", bearerHeaders(token(profile)));
        conn.setRequestProperty("Content-Type", "application/octet-stream");
        conn.setDoOutput(true);
        conn.setFixedLengthStreamingMode(0);
        conn.getOutputStream().close();
        HttpJson.readJson(conn);
    }

    private String token(JSONObject profile) throws Exception {
        String graphBase = graphBase(profile);
        String graphOrigin = graphBase.replaceFirst("/v1\\.0/?$", "");
        String tenantId = required(profile, "tenantId", "Tenant ID 不能为空");
        String clientId = required(profile, "clientId", "Client ID 不能为空");
        String clientSecret = required(profile, "clientSecret", "Client Secret 不能为空");
        String url = authBase(profile) + "/" + tenantId + "/oauth2/v2.0/token";
        Map<String, String> form = new HashMap<>();
        form.put("client_id", clientId);
        form.put("client_secret", clientSecret);
        form.put("grant_type", "client_credentials");
        form.put("scope", graphOrigin + "/.default");
        JSONObject response = HttpJson.postForm(url, form, null);
        String accessToken = response.optString("access_token");
        if (accessToken.isEmpty()) {
            throw new IOException("SP 认证失败: " + response);
        }
        return accessToken;
    }

    private void scanInto(JSONObject profile, String remoteDir, JSONArray files) throws Exception {
        JSONArray children = listChildren(profile, remoteDir);
        for (int i = 0; i < children.length(); i++) {
            JSONObject item = children.getJSONObject(i);
            if ("folder".equals(item.optString("type"))) {
                scanInto(profile, item.optString("path"), files);
            } else {
                files.put(item);
            }
        }
    }

    private JSONObject driveSummary(JSONObject site, JSONObject drive) throws Exception {
        JSONObject result = new JSONObject();
        JSONObject quota = drive.optJSONObject("quota");
        result.put("siteId", site.optString("id"));
        result.put("siteName", site.optString("displayName", site.optString("name", "")));
        result.put("siteWebUrl", site.optString("webUrl", ""));
        result.put("driveId", drive.optString("id"));
        result.put("driveName", drive.optString("name", ""));
        result.put("driveType", drive.optString("driveType", ""));
        result.put("webUrl", drive.optString("webUrl", ""));
        result.put("quotaTotal", quota == null ? 0 : quota.optLong("total"));
        result.put("quotaUsed", quota == null ? 0 : quota.optLong("used"));
        result.put("quotaRemaining", quota == null ? 0 : quota.optLong("remaining"));
        result.put("quotaState", quota == null ? "" : quota.optString("state", ""));
        return result;
    }

    private boolean isExcludedDiscoverySite(JSONObject site) {
        String name = site.optString("displayName", site.optString("name", "")).trim().toLowerCase(java.util.Locale.ROOT);
        String webUrl = site.optString("webUrl", "").trim().toLowerCase(java.util.Locale.ROOT);
        return "team site".equals(name)
                || "communication site".equals(name)
                || webUrl.contains("-my.sharepoint.")
                || webUrl.contains("/personal/");
    }

    private String sharePointSiteApiPath(String siteUrl) throws Exception {
        java.net.URI uri = new java.net.URI(siteUrl.trim());
        if (uri.getScheme() == null || uri.getHost() == null) {
            throw new IOException("SharePoint 站点 URL 必须是完整地址，例如 https://tenant.sharepoint.cn/sites/media");
        }
        String host = uri.getHost().toLowerCase(java.util.Locale.ROOT);
        String path = uri.getPath() == null ? "/" : uri.getPath().trim();
        while (path.endsWith("/")) {
            path = path.substring(0, path.length() - 1);
        }
        if (path.isEmpty() || "/".equals(path)) {
            return "/sites/" + encode(host);
        }
        return "/sites/" + encode(host) + ":/" + encodePath(path.substring(1));
    }

    private Map<String, String> bearerHeaders(String token) {
        Map<String, String> headers = new HashMap<>();
        headers.put("Authorization", "Bearer " + token);
        return headers;
    }

    private int readChunk(InputStream input, byte[] buffer, int wanted) throws IOException {
        int total = 0;
        while (total < wanted) {
            int read = input.read(buffer, total, wanted - total);
            if (read == -1) {
                break;
            }
            total += read;
        }
        return total;
    }

    private String required(JSONObject object, String key, String message) throws IOException {
        String value = object.optString(key).trim();
        if (value.isEmpty()) {
            throw new IOException(message);
        }
        return value;
    }

    private String graphBase(JSONObject profile) {
        String value = profile.optString("graphBaseUrl").trim();
        return value.isEmpty() ? DEFAULT_GRAPH_BASE : trimSlash(value);
    }

    private String authBase(JSONObject profile) {
        String value = profile.optString("authBaseUrl").trim();
        return value.isEmpty() ? DEFAULT_AUTH_BASE : trimSlash(value);
    }

    private String trimSlash(String value) {
        while (value.endsWith("/")) {
            value = value.substring(0, value.length() - 1);
        }
        return value;
    }

    private String joinPath(String root, String dir, String fileName) {
        StringBuilder builder = new StringBuilder();
        appendPath(builder, root);
        appendPath(builder, dir);
        appendPath(builder, fileName);
        return builder.toString();
    }

    private String cleanPath(String value) {
        String clean = value == null ? "" : value.replace("\\", "/").trim();
        while (clean.startsWith("/")) {
            clean = clean.substring(1);
        }
        while (clean.endsWith("/")) {
            clean = clean.substring(0, clean.length() - 1);
        }
        return clean;
    }

    private void appendPath(StringBuilder builder, String part) {
        String clean = part == null ? "" : part.replace("\\", "/").trim();
        while (clean.startsWith("/")) {
            clean = clean.substring(1);
        }
        while (clean.endsWith("/")) {
            clean = clean.substring(0, clean.length() - 1);
        }
        if (clean.isEmpty()) {
            return;
        }
        if (builder.length() > 0) {
            builder.append('/');
        }
        builder.append(clean);
    }

    private String encodePath(String path) throws Exception {
        String[] parts = path.split("/");
        StringBuilder builder = new StringBuilder();
        for (String part : parts) {
            if (part.isEmpty()) {
                continue;
            }
            if (builder.length() > 0) {
                builder.append('/');
            }
            builder.append(encode(part));
        }
        return builder.toString();
    }

    private String encode(String value) throws Exception {
        return URLEncoder.encode(value, "UTF-8").replace("+", "%20");
    }

    interface ProgressCallback {
        void onProgress(long uploaded, long total, long speedBytesPerSecond) throws Exception;
    }
}
