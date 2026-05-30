package com.sjhl.worker;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Environment;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

public class WorkerService extends Service {
    private static final String TAG = "WorkerService";
    private static final String CHANNEL_ID = "sjhl_worker";
    private static final int NOTIFY_ID = 1;

    static WorkerService instance;
    private ApiClient api;
    private Thread workerThread;
    final AtomicBoolean running = new AtomicBoolean(false);
    private PowerManager.WakeLock wakeLock;

    // Current progress state (read from MainActivity for UI)
    volatile String statusText = "等待连接...";
    volatile String taskFile = "";
    volatile long progressDone = 0;
    volatile long progressTotal = 0;
    volatile long speedBps = 0;
    volatile int pendingCount = 0;

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
        instance = this;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && "STOP".equals(intent.getAction())) {
            stopWorker();
            return START_NOT_STICKY;
        }
        startWorker();
        return START_STICKY;
    }

    private void startWorker() {
        AppSettings settings = new AppSettings(this);
        String serverUrl = settings.getServerUrl();
        if (serverUrl.isEmpty()) {
            stopSelf();
            return;
        }

        if (running.getAndSet(true)) return;

        api = new ApiClient(serverUrl);

        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        if (pm != null) {
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "sjhl:worker");
            wakeLock.acquire(30 * 60 * 1000L);
        }

        startForeground(NOTIFY_ID, buildNotification("初始化中...", 0, 0));
        statusText = "连接主控...";

        workerThread = new Thread(this::workerLoop, "SJHL-Worker");
        workerThread.start();
    }

    private void stopWorker() {
        running.set(false);
        if (workerThread != null) {
            workerThread.interrupt();
            workerThread = null;
        }
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
            wakeLock = null;
        }
        stopForeground(true);
        stopSelf();
    }

    private void workerLoop() {
        statusText = "已连接，等待任务...";
        updateNotify("已连接", 0, 0);

        while (running.get()) {
            try {
                // 1. Check for available tasks
                statusText = "正在检查任务...";
                JSONObject state = api.fetchState();
                pendingCount = state.optInt("totalPending", 0);
                statusText = "待处理: " + pendingCount + " 个任务";

                if (pendingCount > 0) {
                    List<JSONObject> tasks = api.fetchTasks();
                    for (JSONObject task : tasks) {
                        if (!running.get()) break;
                        try {
                            processTask(task);
                        } catch (Exception e) {
                            Log.w(TAG, "Task failed: " + e.getMessage());
                        }
                    }
                }

                // 2. Wait before next poll
                int waitSec = pendingCount > 0 ? 5 : 15;
                for (int i = 0; i < waitSec && running.get(); i++) {
                    Thread.sleep(1000);
                }
            } catch (IOException e) {
                statusText = "连接失败: " + e.getMessage();
                updateNotify("连接失败，10秒后重试", 0, 0);
                try { Thread.sleep(10000); } catch (InterruptedException ignored) {}
            } catch (Exception e) {
                Log.e(TAG, "Worker error", e);
                try { Thread.sleep(5000); } catch (InterruptedException ignored) {}
            }
        }
    }

    private void processTask(JSONObject task) throws Exception {
        String taskId = task.getString("id");
        String fileName = task.optString("fileName", "unknown");
        String type = task.optString("type", "115-url");
        long size = task.optLong("size", 0);

        this.taskFile = fileName;

        // Step 1: Claim task
        statusText = "认领: " + fileName;
        updateNotify("认领: " + fileName, 0, 0);
        JSONObject claimed = api.claimTask(taskId);

        try {
            if ("local".equals(type)) {
                // Local files: server-side files, worker can't access them directly
                // The file is already on the server, just need to get upload session
                statusText = "准备上传: " + fileName;
            } else {
                // Step 2: Get download URL
                statusText = "获取下载链接: " + fileName;
                JSONObject dlResp = api.getDownloadUrl(taskId);
                JSONObject download = dlResp.getJSONObject("download");
                String dlUrl = download.getString("url");
                long dlSize = download.optLong("size", size);

                if (dlUrl.isEmpty()) {
                    throw new IOException("下载链接为空");
                }

                // Step 3: Download file
                File dlDir = getDownloadDir();
                dlDir.mkdirs();
                File tmpFile = new File(dlDir, taskId + ".download");
                long existing = tmpFile.exists() ? tmpFile.length() : 0;
                long resumeFrom = (existing > 0 && existing < dlSize) ? existing : 0;
                if (resumeFrom == 0 && tmpFile.exists()) {
                    tmpFile.delete();
                }

                statusText = "下载中: " + fileName;
                updateNotify("下载中: " + fileName, 0, 0);
                progressDone = resumeFrom;
                progressTotal = dlSize;
                speedBps = 0;

                // Parse headers
                JSONObject dlHeaders = download.optJSONObject("headers");
                java.util.Map<String, String> headers = new java.util.HashMap<>();
                if (dlHeaders != null) {
                    java.util.Iterator<String> keys = dlHeaders.keys();
                    while (keys.hasNext()) {
                        String k = keys.next();
                        headers.put(k, dlHeaders.optString(k, ""));
                    }
                }

                api.downloadFile(dlUrl, headers, tmpFile.getAbsolutePath(), resumeFrom,
                    (downloaded, total, speed) -> {
                        progressDone = downloaded;
                        progressTotal = total;
                        speedBps = speed;
                        updateNotify("下载: " + fileName, downloaded, total);
                        try {
                            api.reportProgress(taskId, downloaded, 0, total, speed);
                        } catch (IOException ignored) {}
                    });

                // Report download complete
                api.reportProgress(taskId, dlSize, 0, dlSize, 0);
                progressDone = dlSize;
                progressTotal = dlSize;

                statusText = "下载完成: " + fileName;
                updateNotify("下载完成: " + fileName, dlSize, dlSize);
            }

            // Step 4: Get upload session
            if (!running.get()) return;
            statusText = "获取上传会话: " + fileName;
            JSONObject sessionResp = api.getUploadSession(taskId);
            JSONObject session = sessionResp.getJSONObject("session");
            String uploadUrl = session.getString("uploadUrl");
            long totalSize = session.optLong("totalSize", size);
            int chunkSize = session.optInt("chunkSize", 20 * 1024 * 1024);

            // Step 5: Upload file
            File uploadFile;
            if ("local".equals(type)) {
                // For local type, file stays on server - nothing to do
                api.completeTask(taskId);
                statusText = "完成: " + fileName;
                updateNotify("完成: " + fileName, totalSize, totalSize);
                return;
            } else {
                uploadFile = new File(getDownloadDir(), taskId + ".download");
            }

            statusText = "上传中: " + fileName;
            updateNotify("上传中: " + fileName, 0, totalSize);
            progressDone = 0;
            progressTotal = totalSize;
            speedBps = 0;

            uploadChunked(uploadFile, uploadUrl, totalSize, chunkSize, taskId, fileName);

            // Step 6: Complete
            api.completeTask(taskId);
            statusText = "完成: " + fileName;
            updateNotify("完成: " + fileName, totalSize, totalSize);

            // Clean up temp file
            if (uploadFile.exists()) uploadFile.delete();

        } catch (Exception e) {
            Log.e(TAG, "Task error: " + taskId, e);
            try {
                api.failTask(taskId, e.getMessage());
            } catch (IOException ignored) {}
            statusText = "失败: " + fileName + " - " + e.getMessage();
            updateNotify("失败: " + fileName, 0, 0);
            throw e;
        }
    }

    private void uploadChunked(File file, String uploadUrl, long totalSize,
                               int chunkSize, String taskId, String fileName) throws Exception {
        FileInputStream fis = new FileInputStream(file);
        try {
            byte[] buf = new byte[chunkSize];
            long uploaded = 0;
            long startTime = System.currentTimeMillis();
            long lastCbTime = startTime;
            long lastUploaded = 0;
            int n;

            while ((n = fis.read(buf)) > 0 && running.get()) {
                byte[] chunk = new byte[n];
                System.arraycopy(buf, 0, chunk, 0, n);

                api.putChunk(uploadUrl, chunk, uploaded, totalSize);
                uploaded += n;
                progressDone = uploaded;
                progressTotal = totalSize;

                long now = System.currentTimeMillis();
                if (now - lastCbTime >= 3000) {
                    long elapsed = Math.max(1, now - startTime);
                    long speed = uploaded * 1000 / elapsed;
                    speedBps = speed;
                    updateNotify("上传: " + fileName, uploaded, totalSize);
                    try {
                        api.reportProgress(taskId, 0, uploaded, totalSize, speed);
                    } catch (IOException ignored) {}
                    lastCbTime = now;
                    lastUploaded = uploaded;
                }
            }
        } finally {
            try { fis.close(); } catch (Exception ignored) {}
        }
    }

    private File getDownloadDir() {
        File dir = new File(getExternalFilesDir(null), "downloads");
        dir.mkdirs();
        return dir;
    }

    // ── Notification ──────────────────────────────────────
    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID, "传输服务", NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("后台文件传输");
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm != null) nm.createNotificationChannel(channel);
        }
    }

    private Notification buildNotification(String text, long done, long total) {
        Intent intent = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0));

        Intent stopIntent = new Intent(this, WorkerService.class);
        stopIntent.setAction("STOP");
        PendingIntent stopPi = PendingIntent.getService(this, 1, stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0));

        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(this, CHANNEL_ID);
        } else {
            builder = new Notification.Builder(this);
        }

        String progressStr = total > 0
            ? " (" + fmtSize(done) + "/" + fmtSize(total) + ")"
            : "";
        int pct = total > 0 ? (int)(done * 100 / total) : 0;

        builder.setContentTitle("SJHL Worker")
            .setContentText(text + progressStr)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .setContentIntent(pi)
            .addAction(android.R.drawable.ic_media_pause, "停止", stopPi);

        if (total > 0) {
            builder.setProgress(100, pct, false);
        } else {
            builder.setProgress(0, 0, true);
        }

        return builder.build();
    }

    private void updateNotify(String text, long done, long total) {
        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm != null) {
            nm.notify(NOTIFY_ID, buildNotification(text, done, total));
        }
    }

    private static String fmtSize(long bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return String.format("%.1f KB", bytes / 1024.0);
        if (bytes < 1024L * 1024 * 1024) return String.format("%.1f MB", bytes / (1024.0 * 1024));
        return String.format("%.2f GB", bytes / (1024.0 * 1024 * 1024));
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        stopWorker();
        super.onDestroy();
    }
}
