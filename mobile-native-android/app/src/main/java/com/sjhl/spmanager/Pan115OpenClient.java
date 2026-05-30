package com.sjhl.spmanager;

import org.json.JSONObject;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;

final class Pan115OpenClient {
    static final String USER_AGENT = "Mozilla/5.0 (Linux; Android) AppleWebKit/537.36";
    private static final int CLOUDDRIVE_CLIENT_ID = 100195313;
    private static final String CLOUDDRIVE_REDIRECT_URI = "https://redirect115.zhenyunpan.com";

    DownUrl downUrl(JSONObject account, String pickCode) throws Exception {
        if (pickCode == null || pickCode.trim().isEmpty()) {
            throw new IOException("115 pickCode 不能为空");
        }
        TokenPair tokens = ensureOpenToken(account);
        String accessToken = tokens.accessToken;
        String refreshToken = tokens.refreshToken;
        try {
            return openDownUrl(accessToken, refreshToken, pickCode.trim());
        } catch (Exception firstError) {
            if (refreshToken.isEmpty()) {
                throw firstError;
            }
            TokenPair refreshed = refreshToken(refreshToken);
            return openDownUrl(refreshed.accessToken, refreshed.refreshToken, pickCode.trim());
        }
    }

    JSONArrayResult listDir(JSONObject account, String cid) throws Exception {
        TokenPair tokens = ensureOpenToken(account);
        JSONArrayResult result = new JSONArrayResult();
        result.accessToken = tokens.accessToken;
        result.refreshToken = tokens.refreshToken;
        int offset = 0;
        int limit = 1150;
        while (true) {
            Map<String, String> params = new HashMap<>();
            params.put("cid", String.valueOf(cid == null || cid.trim().isEmpty() ? "0" : cid.trim()));
            params.put("limit", String.valueOf(limit));
            params.put("offset", String.valueOf(offset));
            params.put("show_dir", "1");
            params.put("cur", "1");
            params.put("asc", "1");
            params.put("o", "file_name");
            JSONObject response = openGet(tokens, "https://proapi.115.com/open/ufile/files?" + query(params));
            if (!response.optBoolean("state")) {
                throw new IOException("115 目录列表失败: " + response.optString("message", response.toString()));
            }
            org.json.JSONArray data = response.optJSONArray("data");
            for (int i = 0; data != null && i < data.length(); i++) {
                JSONObject raw = data.optJSONObject(i);
                if (raw == null) {
                    continue;
                }
                boolean isDir = "0".equals(String.valueOf(raw.opt("fc")));
                JSONObject item = new JSONObject();
                String fid = raw.optString("fid");
                item.put("fid", fid);
                item.put("cid", isDir ? fid : raw.optString("pid"));
                item.put("name", raw.optString("fn"));
                item.put("size", raw.optLong("fs"));
                item.put("isDir", isDir);
                item.put("pickCode", raw.optString("pc", raw.optString("pick_code")));
                item.put("sha1", raw.optString("sha1", raw.optString("sha")));
                item.put("mtime", raw.optString("upt", raw.optString("uet")));
                result.items.put(item);
            }
            int count = response.optInt("count", result.items.length());
            int got = data == null ? 0 : data.length();
            offset += got;
            if (got <= 0 || offset >= count) {
                break;
            }
        }
        result.accessToken = tokens.accessToken;
        result.refreshToken = tokens.refreshToken;
        return result;
    }

    JSONArrayResult listFilesRecursive(JSONObject account, String cid) throws Exception {
        JSONArrayResult result = new JSONArrayResult();
        TokenPair tokens = ensureOpenToken(account);
        result.accessToken = tokens.accessToken;
        result.refreshToken = tokens.refreshToken;
        walkFiles(tokens, cid == null || cid.trim().isEmpty() ? "0" : cid.trim(), "", result.items);
        return result;
    }

    JSONObject createFolder(JSONObject account, String pid, String name) throws Exception {
        TokenPair tokens = ensureOpenToken(account);
        Map<String, String> form = new HashMap<>();
        form.put("pid", pid == null || pid.trim().isEmpty() ? "0" : pid.trim());
        form.put("file_name", name == null ? "" : name.trim());
        JSONObject response = openPost(tokens, "https://proapi.115.com/open/folder/add", form);
        if (!response.optBoolean("state")) {
            throw new IOException("115 新建文件夹失败: " + response.optString("message", response.toString()));
        }
        response.put("accessToken", tokens.accessToken);
        response.put("refreshToken", tokens.refreshToken);
        return response;
    }

    JSONArrayResult searchFiles(JSONObject account, String keyword, String cid) throws Exception {
        String cleanKeyword = keyword == null ? "" : keyword.trim();
        if (cleanKeyword.isEmpty()) {
            throw new IOException("搜索关键词不能为空");
        }
        TokenPair tokens = ensureOpenToken(account);
        JSONArrayResult result = new JSONArrayResult();
        result.accessToken = tokens.accessToken;
        result.refreshToken = tokens.refreshToken;
        int offset = 0;
        int limit = 100;
        while (true) {
            Map<String, String> params = new HashMap<>();
            params.put("search_value", cleanKeyword);
            params.put("limit", String.valueOf(limit));
            params.put("offset", String.valueOf(offset));
            String cleanCid = cid == null ? "" : cid.trim();
            if (!cleanCid.isEmpty() && !"0".equals(cleanCid)) {
                params.put("cid", cleanCid);
            }
            JSONObject response = openGet(tokens, "https://proapi.115.com/open/ufile/search?" + query(params));
            if (!response.optBoolean("state")) {
                throw new IOException("115 搜索失败: " + response.optString("message", response.toString()));
            }
            org.json.JSONArray data = response.optJSONArray("data");
            for (int i = 0; data != null && i < data.length(); i++) {
                JSONObject raw = data.optJSONObject(i);
                if (raw == null) {
                    continue;
                }
                result.items.put(openSearchItem(raw));
            }
            int count = response.optInt("count", result.items.length());
            int got = data == null ? 0 : data.length();
            offset += got;
            if (got <= 0 || offset >= count || result.items.length() >= 500) {
                break;
            }
        }
        result.accessToken = tokens.accessToken;
        result.refreshToken = tokens.refreshToken;
        return result;
    }

    JSONObject renameFile(JSONObject account, String fileId, String name) throws Exception {
        String cleanId = fileId == null ? "" : fileId.trim();
        String cleanName = name == null ? "" : name.trim();
        if (cleanId.isEmpty()) {
            throw new IOException("115 文件 ID 不能为空");
        }
        if (cleanName.isEmpty()) {
            throw new IOException("新名称不能为空");
        }
        TokenPair tokens = ensureOpenToken(account);
        Map<String, String> form = new HashMap<>();
        form.put("file_id", cleanId);
        form.put("file_name", cleanName);
        JSONObject response = openPost(tokens, "https://proapi.115.com/open/ufile/update", form);
        if (!response.optBoolean("state")) {
            throw new IOException("115 重命名失败: " + response.optString("message", response.toString()));
        }
        response.put("accessToken", tokens.accessToken);
        response.put("refreshToken", tokens.refreshToken);
        return response;
    }

    JSONObject deleteFiles(JSONObject account, String fileIds, String parentId) throws Exception {
        String cleanIds = fileIds == null ? "" : fileIds.trim();
        if (cleanIds.isEmpty()) {
            throw new IOException("115 文件 ID 不能为空");
        }
        TokenPair tokens = ensureOpenToken(account);
        Map<String, String> form = new HashMap<>();
        form.put("file_ids", cleanIds);
        form.put("parent_id", parentId == null || parentId.trim().isEmpty() ? "0" : parentId.trim());
        JSONObject response = openPost(tokens, "https://proapi.115.com/open/ufile/delete", form);
        if (!response.optBoolean("state")) {
            throw new IOException("115 删除失败: " + response.optString("message", response.toString()));
        }
        response.put("accessToken", tokens.accessToken);
        response.put("refreshToken", tokens.refreshToken);
        return response;
    }

    CloudDriveToken authorizeCloudDrive(String cookie) throws Exception {
        if (cookie == null || cookie.trim().isEmpty()) {
            throw new IOException("115 Cookie 不能为空");
        }
        String params = "client_id=" + CLOUDDRIVE_CLIENT_ID
                + "&redirect_uri=" + encode(CLOUDDRIVE_REDIRECT_URI)
                + "&response_type=code"
                + "&state=" + encode(CLOUDDRIVE_REDIRECT_URI);
        String firstUrl = "https://passportapi.115.com/open/authorize?" + params;
        String firstLocation = requestRedirect(firstUrl, cookie);
        CloudDriveToken firstTokens = parseCloudDriveTokens(firstLocation);
        if (firstTokens != null) {
            return firstTokens;
        }
        String secondLocation = requestRedirect(firstLocation, cookie);
        CloudDriveToken tokens = parseCloudDriveTokens(secondLocation);
        if (tokens == null || tokens.accessToken.isEmpty()) {
            throw new IOException("CloudDrive 授权失败，Cookie 可能已过期");
        }
        return tokens;
    }

    TokenPair ensureOpenToken(JSONObject account) throws Exception {
        String accessToken = account.optString("accessToken").trim();
        String refreshToken = account.optString("refreshToken").trim();
        String cookie = account.optString("cookie").trim();
        if (accessToken.isEmpty() && refreshToken.isEmpty()) {
            if (cookie.isEmpty()) {
                throw new IOException("手机端 115 直传需要 Open Token 或 Cookie");
            }
            CloudDriveToken tokens = authorizeCloudDrive(cookie);
            accessToken = tokens.accessToken;
            refreshToken = tokens.refreshToken;
        }
        if (accessToken.isEmpty()) {
            TokenPair tokens = refreshToken(refreshToken);
            accessToken = tokens.accessToken;
            refreshToken = tokens.refreshToken;
        }
        TokenPair pair = new TokenPair();
        pair.accessToken = accessToken;
        pair.refreshToken = refreshToken;
        return pair;
    }

    private DownUrl openDownUrl(String accessToken, String refreshToken, String pickCode) throws Exception {
        Map<String, String> form = new HashMap<>();
        form.put("pick_code", pickCode);
        Map<String, String> headers = new HashMap<>();
        headers.put("Authorization", "Bearer " + accessToken);
        headers.put("User-Agent", USER_AGENT);
        JSONObject response = HttpJson.postForm("https://proapi.115.com/open/ufile/downurl", form, headers);
        if (!response.optBoolean("state")) {
            throw new IOException("115 下载链接获取失败: " + response.optString("message", response.toString()));
        }
        JSONObject data = response.optJSONObject("data");
        if (data == null) {
            throw new IOException("115 下载链接返回格式无效");
        }
        JSONObject item = data.optJSONObject(pickCode);
        if (item == null) {
            Iterator<String> keys = data.keys();
            if (keys.hasNext()) {
                item = data.optJSONObject(keys.next());
            }
        }
        if (item == null) {
            throw new IOException("115 下载链接为空");
        }
        Object rawUrl = item.opt("url");
        String url = "";
        if (rawUrl instanceof JSONObject) {
            url = ((JSONObject) rawUrl).optString("url");
        } else if (rawUrl != null) {
            url = String.valueOf(rawUrl);
        }
        if (url.isEmpty()) {
            url = item.optString("download_url", item.optString("file_url"));
        }
        if (url.isEmpty()) {
            throw new IOException("115 未返回可用下载地址");
        }
        DownUrl result = new DownUrl();
        result.url = url;
        result.fileName = item.optString("file_name", item.optString("name", ""));
        result.size = item.optLong("file_size", item.optLong("size", 0L));
        result.sha1 = item.optString("sha1", "");
        result.pickCode = item.optString("pick_code", item.optString("pickcode", pickCode));
        result.accessToken = accessToken;
        result.refreshToken = refreshToken;
        result.headers.put("User-Agent", USER_AGENT);
        return result;
    }

    private TokenPair refreshToken(String refreshToken) throws Exception {
        Map<String, String> form = new HashMap<>();
        form.put("refresh_token", refreshToken);
        JSONObject response = HttpJson.postForm("https://passportapi.115.com/open/refreshToken", form, null);
        if (response.optInt("code", -1) != 0) {
            throw new IOException("115 Token 刷新失败: " + response.optString("message", response.toString()));
        }
        JSONObject data = response.optJSONObject("data");
        if (data == null || data.optString("access_token").isEmpty()) {
            throw new IOException("115 Token 刷新返回格式无效");
        }
        TokenPair pair = new TokenPair();
        pair.accessToken = data.optString("access_token");
        pair.refreshToken = data.optString("refresh_token", refreshToken);
        return pair;
    }

    private JSONObject openGet(TokenPair tokens, String url) throws Exception {
        try {
            JSONObject response = HttpJson.getJson(url, bearerHeaders(tokens.accessToken));
            if (shouldRefreshToken(response) && !tokens.refreshToken.isEmpty()) {
                refreshInto(tokens);
                response = HttpJson.getJson(url, bearerHeaders(tokens.accessToken));
            }
            return response;
        } catch (Exception error) {
            if (!tokens.refreshToken.isEmpty() && shouldRefreshToken(error)) {
                refreshInto(tokens);
                return HttpJson.getJson(url, bearerHeaders(tokens.accessToken));
            }
            throw error;
        }
    }

    private JSONObject openPost(TokenPair tokens, String url, Map<String, String> form) throws Exception {
        try {
            JSONObject response = HttpJson.postForm(url, form, bearerHeaders(tokens.accessToken));
            if (shouldRefreshToken(response) && !tokens.refreshToken.isEmpty()) {
                refreshInto(tokens);
                response = HttpJson.postForm(url, form, bearerHeaders(tokens.accessToken));
            }
            return response;
        } catch (Exception error) {
            if (!tokens.refreshToken.isEmpty() && shouldRefreshToken(error)) {
                refreshInto(tokens);
                return HttpJson.postForm(url, form, bearerHeaders(tokens.accessToken));
            }
            throw error;
        }
    }

    private void refreshInto(TokenPair tokens) throws Exception {
        TokenPair refreshed = refreshToken(tokens.refreshToken);
        tokens.accessToken = refreshed.accessToken;
        tokens.refreshToken = refreshed.refreshToken;
    }

    private boolean shouldRefreshToken(JSONObject response) {
        if (response == null || response.optBoolean("state") || (response.has("code") && response.optInt("code", -1) == 0)) {
            return false;
        }
        return shouldRefreshTokenText(response.optString("message") + " " + response.optString("error") + " " + response);
    }

    private boolean shouldRefreshToken(Exception error) {
        return shouldRefreshTokenText(error == null ? "" : error.getMessage());
    }

    private boolean shouldRefreshTokenText(String message) {
        String text = message == null ? "" : message.toLowerCase(java.util.Locale.ROOT);
        return text.contains("access_token")
                || text.contains("invalid token")
                || text.contains("token invalid")
                || text.contains("token expired")
                || text.contains("401")
                || text.contains("403")
                || text.contains("token 无效")
                || text.contains("token 过期")
                || text.contains("登录失效");
    }

    private void walkFiles(TokenPair tokens, String cid, String parentPath, org.json.JSONArray out) throws Exception {
        JSONObject account = new JSONObject();
        account.put("accessToken", tokens.accessToken);
        account.put("refreshToken", tokens.refreshToken);
        JSONArrayResult listing = listDir(account, cid);
        tokens.accessToken = listing.accessToken;
        tokens.refreshToken = listing.refreshToken;
        for (int i = 0; i < listing.items.length(); i++) {
            JSONObject item = listing.items.getJSONObject(i);
            String name = item.optString("name");
            String path = parentPath.isEmpty() ? name : parentPath + "/" + name;
            if (item.optBoolean("isDir")) {
                walkFiles(tokens, item.optString("cid"), path, out);
            } else {
                JSONObject file = new JSONObject(item.toString());
                file.put("relativePath", path);
                out.put(file);
            }
        }
    }

    private JSONObject openSearchItem(JSONObject raw) throws Exception {
        JSONObject item = new JSONObject();
        String fid = raw.optString("file_id", raw.optString("fid"));
        String parentId = raw.optString("parent_id", raw.optString("pid"));
        boolean isDir = "0".equals(String.valueOf(raw.opt("file_category")));
        item.put("fid", fid);
        item.put("cid", isDir ? fid : parentId);
        item.put("name", raw.optString("file_name", raw.optString("fn")));
        item.put("size", raw.optLong("file_size", raw.optLong("fs")));
        item.put("isDir", isDir);
        item.put("pickCode", raw.optString("pick_code", raw.optString("pc")));
        item.put("sha1", raw.optString("sha1", raw.optString("sha")));
        item.put("mtime", raw.optString("user_utime", raw.optString("upt")));
        return item;
    }

    private Map<String, String> bearerHeaders(String accessToken) {
        Map<String, String> headers = new HashMap<>();
        headers.put("Authorization", "Bearer " + accessToken);
        headers.put("User-Agent", USER_AGENT);
        return headers;
    }

    private String requestRedirect(String url, String cookie) throws Exception {
        URL current = new URL(url);
        HttpURLConnection conn = (HttpURLConnection) current.openConnection();
        conn.setInstanceFollowRedirects(false);
        conn.setRequestMethod("GET");
        conn.setConnectTimeout(30000);
        conn.setReadTimeout(30000);
        conn.setUseCaches(false);
        conn.setRequestProperty("Cookie", cookie);
        conn.setRequestProperty("User-Agent", USER_AGENT);
        int code = conn.getResponseCode();
        if (code >= 300 && code < 400) {
            String location = conn.getHeaderField("Location");
            if (location == null || location.isEmpty()) {
                throw new IOException("115 授权跳转地址为空");
            }
            return new URL(current, location).toString();
        }
        String text = HttpJson.readText(code >= 400 ? conn.getErrorStream() : conn.getInputStream());
        throw new IOException("115 授权失败 HTTP " + code + ": " + text);
    }

    private CloudDriveToken parseCloudDriveTokens(String location) throws Exception {
        String payload = "";
        URL url = new URL(location);
        if (url.getQuery() != null) {
            payload = url.getQuery();
        }
        if (payload.isEmpty() && url.getRef() != null) {
            payload = url.getRef();
        }
        if (payload.isEmpty()) {
            return null;
        }
        Map<String, String> values = new HashMap<>();
        for (String part : payload.split("&")) {
            int index = part.indexOf('=');
            if (index <= 0) {
                continue;
            }
            String key = URLDecoder.decode(part.substring(0, index), "UTF-8");
            String value = URLDecoder.decode(part.substring(index + 1), "UTF-8");
            values.put(key, value);
        }
        String accessToken = values.get("access_token");
        if (accessToken == null || accessToken.isEmpty()) {
            return null;
        }
        CloudDriveToken token = new CloudDriveToken();
        token.accessToken = accessToken;
        token.refreshToken = values.get("refresh_token") == null ? "" : values.get("refresh_token");
        return token;
    }

    private String encode(String value) throws Exception {
        return URLEncoder.encode(value, "UTF-8").replace("+", "%20");
    }

    private String query(Map<String, String> params) throws Exception {
        StringBuilder builder = new StringBuilder();
        for (Map.Entry<String, String> entry : params.entrySet()) {
            if (builder.length() > 0) {
                builder.append('&');
            }
            builder.append(encode(entry.getKey()));
            builder.append('=');
            builder.append(encode(entry.getValue()));
        }
        return builder.toString();
    }

    static final class DownUrl {
        String url;
        String fileName;
        long size;
        String sha1;
        String pickCode;
        String accessToken;
        String refreshToken;
        Map<String, String> headers = new HashMap<>();
    }

    static final class CloudDriveToken {
        String accessToken;
        String refreshToken;
    }

    static final class JSONArrayResult {
        final org.json.JSONArray items = new org.json.JSONArray();
        String accessToken;
        String refreshToken;
    }

    static final class TokenPair {
        String accessToken;
        String refreshToken;
    }
}
