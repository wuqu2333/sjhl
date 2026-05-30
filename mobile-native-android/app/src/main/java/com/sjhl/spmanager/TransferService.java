package com.sjhl.spmanager;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.IBinder;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.util.HashMap;
import java.util.Map;

public class TransferService extends Service {
    static final String ACTION_START = "com.sjhl.spmanager.START_TRANSFERS";
    static final String ACTION_STOP = "com.sjhl.spmanager.STOP_TRANSFERS";

    private static final String CHANNEL_ID = "sjhl_transfer";
    private static final int NOTIFICATION_ID = 11;

    private volatile boolean running;
    private Thread worker;
    private final Object uploadLock = new Object();
    private int activeUploads;

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? ACTION_START : intent.getAction();
        if (ACTION_STOP.equals(action)) {
            stopSelf();
            return START_NOT_STICKY;
        }
        ensureChannel();
        startForeground(NOTIFICATION_ID, notification("传输服务运行中", "正在等待本机任务"));
        startWorker();
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        running = false;
        if (worker != null) {
            worker.interrupt();
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void startWorker() {
        if (worker != null && worker.isAlive()) {
            return;
        }
        running = true;
        worker = new Thread(this::loop, "sjhl-mobile-transfer");
        worker.start();
    }

    private void loop() {
        LocalStore store = new LocalStore(this);
        while (running) {
            try {
                processDueSyncJobs(store);
                JSONObject state = store.state();
                int concurrency = Math.max(1, Math.min(4, state.optJSONObject("settings") == null
                        ? 4
                        : state.optJSONObject("settings").optInt("transferConcurrency", 4)));
                boolean started = false;
                while (activeUploadCount() < concurrency) {
                    JSONObject task = store.claimNextQueuedTask();
                    if (task == null) {
                        break;
                    }
                    started = true;
                    synchronized (uploadLock) {
                        activeUploads++;
                    }
                    new Thread(() -> {
                        try {
                            processTask(store, task);
                        } finally {
                            synchronized (uploadLock) {
                                activeUploads = Math.max(0, activeUploads - 1);
                            }
                        }
                    }, "sjhl-upload-task").start();
                }
                updateNotification("传输服务运行中", started ? "已启动上传任务" : "等待任务，当前上传 " + activeUploadCount());
                Thread.sleep(3000L);
            } catch (InterruptedException error) {
                return;
            } catch (Exception ignored) {
                try {
                    Thread.sleep(3000L);
                } catch (InterruptedException error) {
                    return;
                }
            }
        }
    }

    private int activeUploadCount() {
        synchronized (uploadLock) {
            return activeUploads;
        }
    }

    private void processDueSyncJobs(LocalStore store) {
        try {
            JSONObject state = store.state();
            org.json.JSONArray jobs = store.dueSyncJobs(state);
            Pan115OpenClient pan115 = new Pan115OpenClient();
            for (int i = 0; i < jobs.length(); i++) {
                JSONObject job = jobs.getJSONObject(i);
                try {
                    JSONObject account = store.findPan115Account(state, job.optString("pan115AccountId"));
                    if (account == null) {
                        throw new IllegalStateException("没有找到 115 账号");
                    }
                    Pan115OpenClient.JSONArrayResult result = pan115.listFilesRecursive(account, job.optString("sourceCid", "0"));
                    store.updatePan115Tokens(account.optString("id"), result.accessToken, result.refreshToken);
                    int added = store.addTasksFromPan115Files(
                            result.items,
                            job.optString("targetDir"),
                            job.optString("targetPoolId", "default"),
                            account.optString("id")
                    );
                    store.markSyncJobRun(job.optString("id"), added, "");
                } catch (Exception error) {
                    store.markSyncJobRun(job.optString("id"), 0, error.getMessage());
                }
            }
        } catch (Exception ignored) {
        }
    }

    private void processTask(LocalStore store, JSONObject claimedTask) {
        String taskId = claimedTask.optString("id");
        String profileId = "";
        long completedSize = 0L;
        try {
            JSONObject state = store.state();
            JSONObject profile = store.findProfileForTask(state, claimedTask);
            if (profile == null) {
                throw new IllegalStateException("没有可用的目标 SP，请先在手机端添加 SP 并启用容量池");
            }
            profileId = profile.optString("id");
            GraphUploader uploader = new GraphUploader();
            String sourceType = claimedTask.optString("sourceType");
            String targetDir = claimedTask.optString("targetDir");
            String name = claimedTask.optString("name");
            long size = claimedTask.optLong("size");
            updateNotification("正在上传", name);

            if ("local-uri".equals(sourceType)) {
                Uri uri = Uri.parse(claimedTask.optString("source"));
                try (InputStream input = getContentResolver().openInputStream(uri)) {
                    if (input == null) {
                        throw new IllegalStateException("无法打开本地文件");
                    }
                    uploader.uploadInputStream(profile, input, size, targetDir, name, (uploaded, total, speed) -> {
                        updateRunningTask(store, taskId, uploaded, total, speed);
                    });
                }
                completedSize = size;
            } else if ("pan115-open".equals(sourceType)) {
                JSONObject account = store.findPan115Account(state, claimedTask.optString("pan115AccountId"));
                if (account == null) {
                    throw new IllegalStateException("没有找到 115 Open 账号");
                }
                Pan115OpenClient pan115 = new Pan115OpenClient();
                updateTaskPhase(store, taskId, "取链");
                Pan115OpenClient.DownUrl downUrl = pan115.downUrl(account, claimedTask.optString("source"));
                store.updatePan115Tokens(account.optString("id"), downUrl.accessToken, downUrl.refreshToken);
                String fileName = name == null || name.trim().isEmpty() ? downUrl.fileName : name;
                if (fileName == null || fileName.trim().isEmpty()) {
                    fileName = downUrl.pickCode;
                }
                name = fileName;
                File tempFile = downloadPan115ToTemp(store, taskId, pan115, account, downUrl, claimedTask.optString("source"), fileName);
                updateTaskPhase(store, taskId, "上传");
                uploader.uploadFile(profile, tempFile, downUrl.size, targetDir, fileName, (uploaded, total, speed) -> {
                    updateRunningTask(store, taskId, uploaded, total, speed);
                });
                if (!tempFile.delete()) {
                    tempFile.deleteOnExit();
                }
                completedSize = downUrl.size;
            } else {
                throw new IllegalStateException("不支持的任务类型: " + sourceType);
            }

            long finalSize = completedSize;
            store.updateTask(taskId, (task, currentState) -> {
                task.put("status", "done");
                task.put("phase", "完成");
                task.put("uploaded", finalSize);
                task.put("speed", 0L);
                task.put("lastError", "");
                task.put("finishedAt", System.currentTimeMillis());
            });
            store.addProfileUsed(profileId, completedSize);
            store.addFingerprint(profileId, claimedTask.optString("name"), claimedTask.optString("targetDir"), completedSize, claimedTask.optString("sha1"));
            updateNotification("上传完成", claimedTask.optString("name"));
        } catch (Exception error) {
            String message = error.getMessage() == null ? String.valueOf(error) : error.getMessage();
            try {
                store.updateTask(taskId, (task, currentState) -> {
                    task.put("status", "failed");
                    task.put("phase", "失败");
                    task.put("speed", 0L);
                    task.put("lastError", message);
                    task.put("retryCount", task.optInt("retryCount") + 1);
                });
            } catch (Exception ignored) {
            }
            updateNotification("上传失败", message);
        }
    }

    private File downloadPan115ToTemp(
            LocalStore store,
            String taskId,
            Pan115OpenClient pan115,
            JSONObject account,
            Pan115OpenClient.DownUrl downUrl,
            String pickCode,
            String fileName
    ) throws Exception {
        if (downUrl.size <= 0L) {
            throw new IllegalStateException("115 下载链接没有返回文件大小");
        }
        File dir = new File(getCacheDir(), "sjhl-downloads");
        if (!dir.exists() && !dir.mkdirs()) {
            throw new IllegalStateException("无法创建临时下载目录: " + dir.getAbsolutePath());
        }
        File tempFile = new File(dir, taskId + ".download");
        long downloaded = tempFile.exists() ? tempFile.length() : 0L;
        if (downloaded > downUrl.size) {
            if (!tempFile.delete()) {
                throw new IllegalStateException("无法清理异常临时文件: " + tempFile.getAbsolutePath());
            }
            downloaded = 0L;
        }

        store.appendLog("下载", "开始下载到手机临时文件: " + fileName);
        updateTaskPhase(store, taskId, "下载");
        updateTaskMeta(store, taskId, fileName, downUrl.size, downUrl.sha1);

        int retry = 0;
        int refresh = 0;
        long lastUpdateAt = System.currentTimeMillis();
        long lastUpdateBytes = downloaded;
        long startedAt = System.currentTimeMillis();

        while (downloaded < downUrl.size) {
            if (!running) {
                throw new InterruptedException("传输服务已停止");
            }
            HttpURLConnection conn = null;
            try {
                Map<String, String> headers = new HashMap<>();
                if (downUrl.headers != null) {
                    headers.putAll(downUrl.headers);
                }
                if (downloaded > 0L) {
                    headers.put("Range", "bytes=" + downloaded + "-");
                }
                conn = HttpJson.open(downUrl.url, "GET", headers);
                int code = conn.getResponseCode();
                if ((code == 401 || code == 403) && refresh < 3) {
                    refresh++;
                    store.appendLog("下载", "115 下载链接失效，刷新第 " + refresh + " 次");
                    Pan115OpenClient.DownUrl fresh = pan115.downUrl(account, pickCode);
                    store.updatePan115Tokens(account.optString("id"), fresh.accessToken, fresh.refreshToken);
                    account.put("accessToken", fresh.accessToken);
                    account.put("refreshToken", fresh.refreshToken);
                    copyDownUrl(fresh, downUrl);
                    continue;
                }
                if (downloaded > 0L && code == 200) {
                    if (!tempFile.delete()) {
                        throw new IllegalStateException("服务器不支持断点续传，且临时文件无法重建");
                    }
                    downloaded = 0L;
                }
                if (code >= 400) {
                    throw new IllegalStateException("下载失败 HTTP " + code + ": " + HttpJson.readText(conn.getErrorStream()));
                }
                try (InputStream input = conn.getInputStream(); FileOutputStream output = new FileOutputStream(tempFile, downloaded > 0L)) {
                    byte[] buffer = new byte[4 * 1024 * 1024];
                    int read;
                    while ((read = input.read(buffer)) != -1) {
                        if (!running) {
                            throw new InterruptedException("传输服务已停止");
                        }
                        output.write(buffer, 0, read);
                        downloaded += read;
                        long now = System.currentTimeMillis();
                        if (now - lastUpdateAt >= 1000L) {
                            long deltaBytes = downloaded - lastUpdateBytes;
                            long deltaTime = Math.max(1L, now - lastUpdateAt);
                            updateTaskProgress(store, taskId, downloaded, downUrl.size, deltaBytes * 1000L / deltaTime, "下载");
                            lastUpdateAt = now;
                            lastUpdateBytes = downloaded;
                        }
                    }
                }
                retry = 0;
                refresh = 0;
            } catch (InterruptedException error) {
                throw error;
            } catch (Exception error) {
                if (downloaded >= downUrl.size) {
                    break;
                }
                retry++;
                if (retry > 6) {
                    throw new IllegalStateException("下载中断重试耗尽: " + error.getMessage(), error);
                }
                store.appendLog("下载", "下载中断，准备重试 " + retry + "/6: " + error.getMessage());
                Thread.sleep(Math.min(30000L, retry * 3000L));
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        }
        if (tempFile.length() != downUrl.size) {
            throw new IllegalStateException("下载文件大小不一致: " + tempFile.length() + "/" + downUrl.size);
        }
        long elapsed = Math.max(1L, System.currentTimeMillis() - startedAt);
        long speed = downUrl.size * 1000L / elapsed;
        updateTaskProgress(store, taskId, downUrl.size, downUrl.size, speed, "下载完成");
        store.appendLog("下载", "下载完成，平均速度 " + formatSpeed(speed));
        return tempFile;
    }

    private void copyDownUrl(Pan115OpenClient.DownUrl source, Pan115OpenClient.DownUrl target) {
        target.url = source.url;
        target.fileName = source.fileName;
        target.size = source.size;
        target.sha1 = source.sha1;
        target.pickCode = source.pickCode;
        target.accessToken = source.accessToken;
        target.refreshToken = source.refreshToken;
        target.headers = source.headers;
    }

    private void updateTaskMeta(LocalStore store, String taskId, String fileName, long total, String sha1) throws Exception {
        store.updateTask(taskId, (task, state) -> {
            if (fileName != null && !fileName.trim().isEmpty()) {
                task.put("name", fileName);
            }
            task.put("size", total);
            task.put("sha1", sha1 == null ? "" : sha1);
        });
    }

    private void updateTaskPhase(LocalStore store, String taskId, String phase) throws Exception {
        store.updateTask(taskId, (task, state) -> task.put("phase", phase));
        updateNotification(phase, taskId);
    }

    private void updateTaskProgress(LocalStore store, String taskId, long uploaded, long total, long speed, String phase) throws Exception {
        store.updateTask(taskId, (task, state) -> {
            task.put("status", "running");
            task.put("phase", phase);
            task.put("uploaded", uploaded);
            task.put("size", total);
            task.put("speed", speed);
        });
        updateNotification(phase, formatBytes(uploaded) + " / " + formatBytes(total) + "  " + formatSpeed(speed));
    }

    private void updateRunningTask(LocalStore store, String taskId, long uploaded, long total, long speed) throws Exception {
        store.updateTask(taskId, (task, state) -> {
            task.put("status", "running");
            task.put("phase", "上传");
            task.put("uploaded", uploaded);
            task.put("size", total);
            task.put("speed", speed);
        });
        updateNotification("正在上传", formatBytes(uploaded) + " / " + formatBytes(total) + "  " + formatSpeed(speed));
    }

    private void ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }
        NotificationChannel channel = new NotificationChannel(CHANNEL_ID, "上传任务", NotificationManager.IMPORTANCE_LOW);
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager != null) {
            manager.createNotificationChannel(channel);
        }
    }

    private void updateNotification(String title, String text) {
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (manager != null) {
            manager.notify(NOTIFICATION_ID, notification(title, text));
        }
    }

    private Notification notification(String title, String text) {
        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        return builder
                .setContentTitle(title)
                .setContentText(text)
                .setSmallIcon(android.R.drawable.stat_sys_upload)
                .setOngoing(true)
                .build();
    }

    private String formatSpeed(long bytesPerSecond) {
        return formatBytes(bytesPerSecond) + "/s";
    }

    private String formatBytes(long bytes) {
        if (bytes <= 0) {
            return "0 B";
        }
        String[] units = {"B", "KB", "MB", "GB", "TB"};
        double value = bytes;
        int index = 0;
        while (value >= 1024 && index < units.length - 1) {
            value /= 1024;
            index++;
        }
        return String.format(java.util.Locale.CHINA, index >= 3 ? "%.2f %s" : "%.0f %s", value, units[index]);
    }
}
