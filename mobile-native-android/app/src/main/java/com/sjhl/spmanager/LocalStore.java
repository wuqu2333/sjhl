package com.sjhl.spmanager;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.UUID;

final class LocalStore {
    private static final String PREFS = "sjhl_mobile_store";
    private static final String KEY_STATE = "state";
    private static final long SP_CAPACITY_BYTES = 25L * 1024L * 1024L * 1024L * 1024L;

    private final SharedPreferences prefs;
    private final MobileDatabase database;

    LocalStore(Context context) {
        prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        database = new MobileDatabase(context.getApplicationContext());
        migrateSharedPreferencesIfNeeded();
    }

    synchronized JSONObject state() {
        try {
            JSONObject state = ensureDefaults(database.loadState());
            if (!database.hasAnyData()) {
                database.saveState(state);
            }
            return state;
        } catch (JSONException ignored) {
            return ensureDefaults(new JSONObject());
        }
    }

    synchronized void save(JSONObject state) {
        try {
            database.saveState(ensureDefaults(state));
        } catch (JSONException ignored) {
        }
    }

    private void migrateSharedPreferencesIfNeeded() {
        if (database.isMigrated()) {
            return;
        }
        String raw = prefs.getString(KEY_STATE, "");
        if (raw != null && !raw.isEmpty()) {
            try {
                database.saveState(ensureDefaults(new JSONObject(raw)));
                prefs.edit().remove(KEY_STATE).apply();
            } catch (JSONException ignored) {
            }
        }
        database.markMigrated();
    }

    synchronized JSONObject addPool(String name) throws JSONException {
        JSONObject state = state();
        JSONObject pool = new JSONObject();
        pool.put("id", UUID.randomUUID().toString());
        pool.put("name", clean(name, "未命名容量池"));
        pool.put("createdAt", System.currentTimeMillis());
        state.getJSONArray("capacityPools").put(pool);
        save(state);
        return pool;
    }

    synchronized void removePool(String poolId) throws JSONException {
        if ("default".equals(poolId)) {
            throw new JSONException("默认容量池不能删除");
        }
        JSONObject state = state();
        JSONArray profiles = state.getJSONArray("profiles");
        for (int i = 0; i < profiles.length(); i++) {
            if (poolId.equals(profiles.getJSONObject(i).optString("capacityPoolId"))) {
                throw new JSONException("容量池仍有关联的 SP，不能删除");
            }
        }
        state.put("capacityPools", removeById(state.getJSONArray("capacityPools"), poolId));
        save(state);
    }

    synchronized JSONObject addSharePointProfile(
            String name,
            String tenantId,
            String clientId,
            String clientSecret,
            String driveId,
            String rootPath,
            String poolId
    ) throws JSONException {
        if (trim(driveId).isEmpty()) {
            throw new JSONException("SP Drive ID 不能为空。请填写文档库 Drive ID，或在“租户”里用发现并导入自动获取。");
        }
        JSONObject state = state();
        JSONObject profile = new JSONObject();
        profile.put("id", UUID.randomUUID().toString());
        profile.put("name", clean(name, "未命名 SP"));
        profile.put("tenantId", trim(tenantId));
        profile.put("clientId", trim(clientId));
        profile.put("clientSecret", trim(clientSecret));
        profile.put("driveId", trim(driveId));
        profile.put("rootPath", trim(rootPath));
        profile.put("capacityPoolId", clean(poolId, "default"));
        profile.put("capacityEnabled", true);
        profile.put("quotaTotal", SP_CAPACITY_BYTES);
        profile.put("quotaUsed", 0L);
        profile.put("quotaRemaining", SP_CAPACITY_BYTES);
        profile.put("graphBaseUrl", "https://microsoftgraph.chinacloudapi.cn/v1.0");
        profile.put("authBaseUrl", "https://login.partner.microsoftonline.cn");
        state.getJSONArray("profiles").put(profile);
        save(state);
        return profile;
    }

    synchronized void removeSharePointProfile(String profileId) throws JSONException {
        JSONObject state = state();
        state.put("profiles", removeById(state.getJSONArray("profiles"), profileId));
        save(state);
    }

    synchronized void toggleSharePointProfileEnabled(String profileId, boolean enabled) throws JSONException {
        JSONObject state = state();
        JSONObject profile = findById(state.getJSONArray("profiles"), profileId);
        if (profile != null) {
            profile.put("capacityEnabled", enabled);
            save(state);
        }
    }

    synchronized void moveSharePointProfilePool(String profileId, String poolId) throws JSONException {
        JSONObject state = state();
        JSONObject profile = findById(state.getJSONArray("profiles"), profileId);
        if (profile != null) {
            profile.put("capacityPoolId", clean(poolId, "default"));
            save(state);
        }
    }

    synchronized void renamePool(String poolId, String name) throws JSONException {
        JSONObject state = state();
        JSONObject pool = findById(state.getJSONArray("capacityPools"), poolId);
        if (pool != null) {
            pool.put("name", clean(name, pool.optString("name")));
            save(state);
        }
    }

    synchronized JSONObject addPan115Account(String name, String cookie, String accessToken, String refreshToken) throws JSONException {
        JSONObject state = state();
        JSONObject account = new JSONObject();
        account.put("id", UUID.randomUUID().toString());
        account.put("name", clean(name, "115 账号"));
        account.put("cookie", trim(cookie));
        account.put("accessToken", trim(accessToken));
        account.put("refreshToken", trim(refreshToken));
        state.getJSONArray("pan115Accounts").put(account);
        save(state);
        return account;
    }

    synchronized void removePan115Account(String accountId) throws JSONException {
        JSONObject state = state();
        state.put("pan115Accounts", removeById(state.getJSONArray("pan115Accounts"), accountId));
        save(state);
    }

    synchronized JSONObject addTenantConnection(
            String name,
            String authMode,
            String region,
            String tenantId,
            String clientId,
            String clientSecret,
            String refreshToken,
            String defaultRootPath,
            boolean importDocumentsOnly
    ) throws JSONException {
        JSONObject state = state();
        JSONObject connection = new JSONObject();
        connection.put("id", UUID.randomUUID().toString());
        connection.put("name", clean(name, "租户连接"));
        connection.put("authMode", clean(authMode, "client_credentials"));
        connection.put("region", clean(region, "cn"));
        connection.put("tenantId", trim(tenantId));
        connection.put("clientId", trim(clientId));
        connection.put("clientSecret", trim(clientSecret));
        connection.put("refreshToken", trim(refreshToken));
        connection.put("defaultRootPath", trim(defaultRootPath));
        connection.put("importDocumentsOnly", importDocumentsOnly);
        connection.put("graphBaseUrl", "https://microsoftgraph.chinacloudapi.cn/v1.0");
        connection.put("authBaseUrl", "https://login.partner.microsoftonline.cn");
        state.getJSONArray("tenantConnections").put(connection);
        save(state);
        return connection;
    }

    synchronized void removeTenantConnection(String connectionId) throws JSONException {
        JSONObject state = state();
        state.put("tenantConnections", removeById(state.getJSONArray("tenantConnections"), connectionId));
        save(state);
    }

    synchronized JSONObject findTenantConnection(JSONObject state, String connectionId) {
        JSONArray connections = state.optJSONArray("tenantConnections");
        if (connections == null) {
            return null;
        }
        for (int i = 0; i < connections.length(); i++) {
            JSONObject connection = connections.optJSONObject(i);
            if (connection != null && connectionId.equals(connection.optString("id"))) {
                return connection;
            }
        }
        return null;
    }

    synchronized JSONObject findSharePointProfileByDriveId(JSONObject state, String driveId) {
        JSONArray profiles = state.optJSONArray("profiles");
        if (profiles == null) {
            return null;
        }
        for (int i = 0; i < profiles.length(); i++) {
            JSONObject profile = profiles.optJSONObject(i);
            if (profile != null && driveId.equals(profile.optString("driveId"))) {
                return profile;
            }
        }
        return null;
    }

    synchronized JSONObject addTask(
            String name,
            String sourceType,
            String source,
            String targetDir,
            String targetPoolId,
            String accountId,
            long size
    ) throws JSONException {
        return addTaskWithMeta(name, sourceType, source, targetDir, targetPoolId, accountId, size, "", "");
    }

    synchronized JSONObject addTaskWithMeta(
            String name,
            String sourceType,
            String source,
            String targetDir,
            String targetPoolId,
            String accountId,
            long size,
            String sha1,
            String relativePath
    ) throws JSONException {
        JSONObject state = state();
        if (isDuplicate(state, size, sha1, name)) {
            appendLogLocked(state, "去重", "跳过重复文件: " + clean(name, "未命名文件"));
            save(state);
            return null;
        }
        JSONObject task = newTask(name, sourceType, source, targetDir, targetPoolId, accountId, size, sha1, relativePath);
        state.getJSONArray("tasks").put(task);
        appendLogLocked(state, "任务", "已加入队列: " + task.optString("name"));
        save(state);
        return task;
    }

    synchronized int addTasksFromPan115Files(
            JSONArray files,
            String targetDir,
            String targetPoolId,
            String accountId
    ) throws JSONException {
        JSONObject state = state();
        int added = 0;
        for (int i = 0; files != null && i < files.length(); i++) {
            JSONObject file = files.optJSONObject(i);
            if (file == null || file.optBoolean("isDir")) {
                continue;
            }
            String name = clean(file.optString("name"), file.optString("pickCode"));
            long size = file.optLong("size");
            String sha1 = file.optString("sha1");
            if (isDuplicate(state, size, sha1, name)) {
                continue;
            }
            String rel = file.optString("relativePath", name);
            String dir = joinPath(targetDir, parentPath(rel));
            state.getJSONArray("tasks").put(newTask(
                    name,
                    "pan115-open",
                    file.optString("pickCode"),
                    dir,
                    targetPoolId,
                    accountId,
                    size,
                    sha1,
                    rel
            ));
            added++;
        }
        appendLogLocked(state, "同步", "已导入 " + added + " 个 115 文件任务");
        save(state);
        return added;
    }

    synchronized void deleteTask(String taskId) throws JSONException {
        JSONObject state = state();
        state.put("tasks", removeById(state.getJSONArray("tasks"), taskId));
        save(state);
    }

    synchronized void retryTask(String taskId) throws JSONException {
        JSONObject state = state();
        JSONObject task = findById(state.getJSONArray("tasks"), taskId);
        if (task != null) {
            task.put("status", "queued");
            task.put("phase", "");
            task.put("uploaded", 0L);
            task.put("lastError", "");
            task.put("speed", 0L);
            task.put("updatedAt", System.currentTimeMillis());
            save(state);
        }
    }

    synchronized void updateTask(String taskId, TaskUpdater updater) throws JSONException {
        JSONObject state = state();
        JSONObject task = findById(state.getJSONArray("tasks"), taskId);
        if (task != null) {
            updater.update(task, state);
            task.put("updatedAt", System.currentTimeMillis());
            save(state);
        }
    }

    synchronized JSONObject claimNextQueuedTask() throws JSONException {
        JSONObject state = state();
        JSONObject settings = state.optJSONObject("settings");
        long dailyLimit = settings == null ? 0L : settings.optLong("dailyUploadLimitBytes");
        if (dailyLimit > 0 && todayUploadedBytes(state) >= dailyLimit) {
            appendLogLocked(state, "限额", "今日上传量已达到限制，暂停领取新任务");
            save(state);
            return null;
        }
        JSONArray tasks = state.getJSONArray("tasks");
        for (int i = 0; i < tasks.length(); i++) {
            JSONObject task = tasks.getJSONObject(i);
            String status = task.optString("status");
            if ("queued".equals(status)) {
                task.put("status", "running");
                task.put("phase", "准备");
                task.put("speed", 0L);
                task.put("lastError", "");
                task.put("startedAt", System.currentTimeMillis());
                task.put("updatedAt", System.currentTimeMillis());
                appendLogLocked(state, "任务", "开始上传: " + task.optString("name"));
                save(state);
                return new JSONObject(task.toString());
            }
        }
        return null;
    }

    synchronized JSONObject addSyncJob(
            String name,
            String pan115AccountId,
            String sourceCid,
            String sourcePath,
            String targetPoolId,
            String targetDir,
            int intervalMinutes
    ) throws JSONException {
        JSONObject state = state();
        JSONObject job = new JSONObject();
        job.put("id", UUID.randomUUID().toString());
        job.put("name", clean(name, "同步作业"));
        job.put("pan115AccountId", trim(pan115AccountId));
        job.put("sourceCid", clean(sourceCid, "0"));
        job.put("sourcePath", trim(sourcePath));
        job.put("targetPoolId", clean(targetPoolId, "default"));
        job.put("targetDir", trim(targetDir));
        job.put("intervalMinutes", Math.max(0, intervalMinutes));
        job.put("enabled", true);
        job.put("lastRunAt", 0L);
        job.put("createdAt", System.currentTimeMillis());
        state.getJSONArray("syncJobs").put(job);
        appendLogLocked(state, "同步", "已创建同步作业: " + job.optString("name"));
        save(state);
        return job;
    }

    synchronized void deleteSyncJob(String jobId) throws JSONException {
        JSONObject state = state();
        state.put("syncJobs", removeById(state.getJSONArray("syncJobs"), jobId));
        save(state);
    }

    synchronized void markSyncJobRun(String jobId, int added, String error) throws JSONException {
        JSONObject state = state();
        JSONObject job = findById(state.getJSONArray("syncJobs"), jobId);
        if (job != null) {
            job.put("lastRunAt", System.currentTimeMillis());
            job.put("lastAdded", added);
            job.put("lastError", trim(error));
            appendLogLocked(state, "同步", trim(error).isEmpty()
                    ? job.optString("name") + " 完成，新增 " + added + " 个任务"
                    : job.optString("name") + " 失败: " + error);
            save(state);
        }
    }

    synchronized void rebuildFingerprints(String profileId, JSONArray files) throws JSONException {
        JSONObject state = state();
        JSONArray old = state.getJSONArray("fingerprints");
        JSONArray next = new JSONArray();
        for (int i = 0; i < old.length(); i++) {
            JSONObject fp = old.optJSONObject(i);
            if (fp != null && !profileId.equals(fp.optString("profileId"))) {
                next.put(fp);
            }
        }
        for (int i = 0; files != null && i < files.length(); i++) {
            JSONObject file = files.optJSONObject(i);
            if (file == null) {
                continue;
            }
            JSONObject fp = new JSONObject();
            fp.put("id", UUID.randomUUID().toString());
            fp.put("profileId", profileId);
            fp.put("name", file.optString("name"));
            fp.put("path", file.optString("path"));
            fp.put("size", file.optLong("size"));
            fp.put("sha1", file.optString("sha1"));
            fp.put("quickXorHash", file.optString("quickXorHash"));
            fp.put("scannedAt", System.currentTimeMillis());
            next.put(fp);
        }
        state.put("fingerprints", next);
        appendLogLocked(state, "扫描", "SP 扫描完成，指纹数 " + next.length());
        save(state);
    }

    synchronized void addFingerprint(String profileId, String name, String path, long size, String sha1) throws JSONException {
        JSONObject state = state();
        JSONObject fp = new JSONObject();
        fp.put("id", UUID.randomUUID().toString());
        fp.put("profileId", profileId);
        fp.put("name", clean(name, ""));
        fp.put("path", trim(path));
        fp.put("size", Math.max(0L, size));
        fp.put("sha1", trim(sha1));
        fp.put("scannedAt", System.currentTimeMillis());
        state.getJSONArray("fingerprints").put(fp);
        save(state);
    }

    synchronized void clearFingerprints() throws JSONException {
        JSONObject state = state();
        state.put("fingerprints", new JSONArray());
        save(state);
    }

    synchronized void appendLog(String type, String message) throws JSONException {
        JSONObject state = state();
        appendLogLocked(state, type, message);
        save(state);
    }

    synchronized void clearLogs() throws JSONException {
        JSONObject state = state();
        state.put("logs", new JSONArray());
        save(state);
    }

    synchronized void updateSettings(long dailyUploadLimitBytes, int transferConcurrency) throws JSONException {
        JSONObject state = state();
        JSONObject settings = state.getJSONObject("settings");
        settings.put("dailyUploadLimitBytes", Math.max(0L, dailyUploadLimitBytes));
        settings.put("transferConcurrency", Math.max(1, Math.min(4, transferConcurrency)));
        save(state);
    }

    JSONArray dueSyncJobs(JSONObject state) {
        JSONArray result = new JSONArray();
        JSONArray jobs = state.optJSONArray("syncJobs");
        long now = System.currentTimeMillis();
        for (int i = 0; jobs != null && i < jobs.length(); i++) {
            JSONObject job = jobs.optJSONObject(i);
            if (job == null || !job.optBoolean("enabled", true)) {
                continue;
            }
            int interval = job.optInt("intervalMinutes");
            long lastRunAt = job.optLong("lastRunAt");
            if (interval > 0 && (lastRunAt <= 0 || now - lastRunAt >= interval * 60_000L)) {
                result.put(job);
            }
        }
        return result;
    }

    JSONObject findProfileForTask(JSONObject state, JSONObject task) {
        JSONArray profiles = state.optJSONArray("profiles");
        if (profiles == null) {
            return null;
        }
        String targetPoolId = task.optString("targetPoolId", "default");
        for (int i = 0; i < profiles.length(); i++) {
            JSONObject profile = profiles.optJSONObject(i);
            if (profile == null || !profile.optBoolean("capacityEnabled", true)) {
                continue;
            }
            if (trim(profile.optString("driveId")).isEmpty()
                    || trim(profile.optString("tenantId")).isEmpty()
                    || trim(profile.optString("clientId")).isEmpty()
                    || trim(profile.optString("clientSecret")).isEmpty()) {
                continue;
            }
            if (targetPoolId.equals(profile.optString("capacityPoolId", "default"))) {
                return profile;
            }
        }
        return null;
    }

    JSONObject findPan115Account(JSONObject state, String accountId) {
        JSONArray accounts = state.optJSONArray("pan115Accounts");
        if (accounts == null) {
            return null;
        }
        for (int i = 0; i < accounts.length(); i++) {
            JSONObject account = accounts.optJSONObject(i);
            if (account != null && accountId.equals(account.optString("id"))) {
                return account;
            }
        }
        return null;
    }

    synchronized void updatePan115Tokens(String accountId, String accessToken, String refreshToken) throws JSONException {
        if (accountId == null || accountId.isEmpty()) {
            return;
        }
        JSONObject state = state();
        JSONObject account = findPan115Account(state, accountId);
        if (account != null) {
            if (accessToken != null && !accessToken.isEmpty()) {
                account.put("accessToken", accessToken);
            }
            if (refreshToken != null && !refreshToken.isEmpty()) {
                account.put("refreshToken", refreshToken);
            }
            save(state);
        }
    }

    synchronized void addProfileUsed(String profileId, long bytes) throws JSONException {
        JSONObject state = state();
        JSONObject profile = findById(state.getJSONArray("profiles"), profileId);
        if (profile != null && bytes > 0) {
            long total = profile.optLong("quotaTotal", SP_CAPACITY_BYTES);
            long used = Math.max(0L, profile.optLong("quotaUsed") + bytes);
            profile.put("quotaUsed", used);
            profile.put("quotaRemaining", Math.max(0L, total - used));
            appendLogLocked(state, "容量", profile.optString("name") + " 已用容量增加 " + bytes + " B");
            save(state);
        }
    }

    synchronized void updateProfileQuota(String profileId, long total, long used, long remaining) throws JSONException {
        JSONObject state = state();
        JSONObject profile = findById(state.getJSONArray("profiles"), profileId);
        if (profile != null) {
            if (total > 0) {
                profile.put("quotaTotal", total);
            }
            profile.put("quotaUsed", Math.max(0L, used));
            profile.put("quotaRemaining", Math.max(0L, remaining));
            save(state);
        }
    }

    private JSONObject ensureDefaults(JSONObject state) {
        try {
            if (!state.has("capacityPools")) {
                JSONArray pools = new JSONArray();
                JSONObject pool = new JSONObject();
                pool.put("id", "default");
                pool.put("name", "默认容量池");
                pool.put("createdAt", System.currentTimeMillis());
                pools.put(pool);
                state.put("capacityPools", pools);
            }
            if (!state.has("profiles")) {
                state.put("profiles", new JSONArray());
            }
            if (!state.has("pan115Accounts")) {
                state.put("pan115Accounts", new JSONArray());
            }
            if (!state.has("tenantConnections")) {
                state.put("tenantConnections", new JSONArray());
            }
            if (!state.has("tasks")) {
                state.put("tasks", new JSONArray());
            }
            if (!state.has("syncJobs")) {
                state.put("syncJobs", new JSONArray());
            }
            if (!state.has("fingerprints")) {
                state.put("fingerprints", new JSONArray());
            }
            if (!state.has("logs")) {
                state.put("logs", new JSONArray());
            }
            if (!state.has("settings")) {
                JSONObject settings = new JSONObject();
                settings.put("transferConcurrency", 4);
                settings.put("dailyUploadLimitBytes", 0L);
                state.put("settings", settings);
            }
        } catch (JSONException ignored) {
        }
        return state;
    }

    private JSONObject newTask(
            String name,
            String sourceType,
            String source,
            String targetDir,
            String targetPoolId,
            String accountId,
            long size,
            String sha1,
            String relativePath
    ) throws JSONException {
        JSONObject task = new JSONObject();
        task.put("id", UUID.randomUUID().toString());
        task.put("name", clean(name, "上传任务"));
        task.put("sourceType", clean(sourceType, "local-uri"));
        task.put("source", trim(source));
        task.put("targetDir", trim(targetDir));
        task.put("targetPoolId", clean(targetPoolId, "default"));
        task.put("pan115AccountId", trim(accountId));
        task.put("size", Math.max(0L, size));
        task.put("sha1", trim(sha1));
        task.put("relativePath", trim(relativePath));
        task.put("uploaded", 0L);
        task.put("speed", 0L);
        task.put("phase", "");
        task.put("retryCount", 0);
        task.put("status", "queued");
        task.put("createdAt", System.currentTimeMillis());
        task.put("updatedAt", System.currentTimeMillis());
        return task;
    }

    private boolean isDuplicate(JSONObject state, long size, String sha1, String name) {
        String cleanName = MobileDatabase.normalizeName(name);
        if (cleanName.isEmpty()) {
            return false;
        }
        long cleanSize = Math.max(0L, size);
        if (database.hasNameSize("fingerprints", cleanName, cleanSize)
                || database.hasNameSize("tasks", cleanName, cleanSize)) {
            return true;
        }
        JSONArray fingerprints = state.optJSONArray("fingerprints");
        for (int i = 0; fingerprints != null && i < fingerprints.length(); i++) {
            JSONObject fp = fingerprints.optJSONObject(i);
            if (fp == null || fp.optLong("size") != cleanSize) {
                continue;
            }
            if (cleanName.equals(MobileDatabase.normalizeName(fp.optString("name")))) {
                return true;
            }
        }
        JSONArray tasks = state.optJSONArray("tasks");
        for (int i = 0; tasks != null && i < tasks.length(); i++) {
            JSONObject task = tasks.optJSONObject(i);
            if (task == null || task.optLong("size") != cleanSize) {
                continue;
            }
            if (cleanName.equals(MobileDatabase.normalizeName(task.optString("name")))) {
                return true;
            }
        }
        return false;
    }

    private long todayUploadedBytes(JSONObject state) {
        long total = 0L;
        long start = startOfToday();
        JSONArray tasks = state.optJSONArray("tasks");
        for (int i = 0; tasks != null && i < tasks.length(); i++) {
            JSONObject task = tasks.optJSONObject(i);
            if (task != null && "done".equals(task.optString("status")) && task.optLong("finishedAt") >= start) {
                total += task.optLong("size");
            }
        }
        return total;
    }

    private long startOfToday() {
        java.util.Calendar calendar = java.util.Calendar.getInstance();
        calendar.set(java.util.Calendar.HOUR_OF_DAY, 0);
        calendar.set(java.util.Calendar.MINUTE, 0);
        calendar.set(java.util.Calendar.SECOND, 0);
        calendar.set(java.util.Calendar.MILLISECOND, 0);
        return calendar.getTimeInMillis();
    }

    private void appendLogLocked(JSONObject state, String type, String message) throws JSONException {
        JSONArray logs = state.getJSONArray("logs");
        JSONObject log = new JSONObject();
        log.put("id", UUID.randomUUID().toString());
        log.put("time", System.currentTimeMillis());
        log.put("type", clean(type, "日志"));
        log.put("message", clean(message, ""));
        logs.put(log);
        if (logs.length() > 500) {
            JSONArray next = new JSONArray();
            for (int i = logs.length() - 500; i < logs.length(); i++) {
                next.put(logs.get(i));
            }
            state.put("logs", next);
        }
    }

    private String parentPath(String relativePath) {
        String clean = trim(relativePath).replace("\\", "/");
        int index = clean.lastIndexOf('/');
        return index <= 0 ? "" : clean.substring(0, index);
    }

    private String joinPath(String left, String right) {
        String a = trim(left).replace("\\", "/");
        String b = trim(right).replace("\\", "/");
        while (a.endsWith("/")) a = a.substring(0, a.length() - 1);
        while (b.startsWith("/")) b = b.substring(1);
        if (a.isEmpty()) return b;
        if (b.isEmpty()) return a;
        return a + "/" + b;
    }

    private JSONArray removeById(JSONArray source, String id) throws JSONException {
        JSONArray next = new JSONArray();
        for (int i = 0; i < source.length(); i++) {
            JSONObject item = source.getJSONObject(i);
            if (!id.equals(item.optString("id"))) {
                next.put(item);
            }
        }
        return next;
    }

    private JSONObject findById(JSONArray source, String id) {
        for (int i = 0; i < source.length(); i++) {
            JSONObject item = source.optJSONObject(i);
            if (item != null && id.equals(item.optString("id"))) {
                return item;
            }
        }
        return null;
    }

    private String clean(String value, String fallback) {
        String raw = trim(value);
        return raw.isEmpty() ? fallback : raw;
    }

    private String trim(String value) {
        return value == null ? "" : value.trim();
    }

    interface TaskUpdater {
        void update(JSONObject task, JSONObject state) throws JSONException;
    }
}
