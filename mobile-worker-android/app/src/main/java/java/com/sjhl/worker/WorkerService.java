package com.sjhl.worker;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

public class WorkerService extends Service {
    private static final String TAG = "WorkerService";
    private static final String CHANNEL_ID = "sjhl_worker";
    private static final int NOTIFY_ID = 1;

    private ApiClient api;
    private Thread workerThread;
    final AtomicBoolean running = new AtomicBoolean(false);
    private PowerManager.WakeLock wakeLock;

    // ── UI 可读取的状态 ────────────────────────────────
    static WorkerService instance;

    volatile String phase = "空闲";          // 空闲 / 下载中 / 上传中 / 连接失败
    volatile String dlFile = "";             // 正在下载的文件名
    volatile String ulFile = "";             // 正在上传的文件名
    volatile long dlDone = 0, dlTotal = 0;   // 下载进度
    volatile long ulDone = 0, ulTotal = 0;   // 上传进度
    volatile long dlSpeed = 0, ulSpeed = 0;  // 当前速度 B/s
    volatile long dlAvgSpeed = 0, ulAvgSpeed = 0; // 平均速度
    volatile long dlBytes = 0, ulBytes = 0;  // 累计传输量
    volatile long dlStartTime = 0, ulStartTime = 0; // 开始时间
    volatile int pendingCount = 0;
    volatile int completedCount = 0;

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
        if (serverUrl.isEmpty()) { stopSelf(); return; }
        if (running.getAndSet(true)) return;

        api = new ApiClient(serverUrl);
        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        if (pm != null) {
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "sjhl:worker");
            wakeLock.acquire(30 * 60 * 1000L);
        }

        startForeground(NOTIFY_ID, buildNotification("初始化..."));
        phase = "连接中";

        workerThread = new Thread(this::workerLoop, "SJHL-Worker");
        workerThread.start();
    }

    private void stopWorker() {
        running.set(false);
        if (workerThread != null) { workerThread.interrupt(); workerThread = null; }
        if (wakeLock != null && wakeLock.isHeld()) { wakeLock.release(); wakeLock = null; }
        stopForeground(true);
        stopSelf();
    }

    private void workerLoop() {
        phase = "等待任务";
        updateNotify("就绪");

        while (running.get()) {
            try {
                List<JSONObject> tasks = api.fetchTasks();
                pendingCount = tasks.size();
                phase = pendingCount > 0 ? "拉取中" : "等待任务";

                for (JSONObject task : tasks) {
                    if (!running.get()) break;
                    String status = task.optString("status", "");
                    // 只认领待处理的任务
                    if (!"queued".equals(status) && !"retry".equals(status)) continue;
                    try {
                        processTask(task);
                        completedCount++;
                    } catch (Exception e) {
                        Log.w(TAG, "Task failed: " + e.getMessage());
                    }
                }

                int waitSec = pendingCount > 0 ? 5 : 15;
                for (int i = 0; i < waitSec && running.get(); i++) Thread.sleep(1000);
            } catch (IOException e) {
                phase = "连接失败";
                updateNotify("连接失败，10秒后重试");
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

        // Step 1: Claim
        phase = "认领中";
        api.claimTask(taskId);

        try {
            if (!"local".equals(type)) {
                // ── 下载阶段 ──
                dlFile = fileName;
                ulFile = "";
                dlDone = 0; dlTotal = size; dlSpeed = 0;
                dlStartTime = System.currentTimeMillis();
                phase = "下载中";

                JSONObject dlResp = api.getDownloadUrl(taskId);
                JSONObject download = dlResp.getJSONObject("download");
                String dlUrl = download.getString("url");

                if (dlUrl.isEmpty()) throw new IOException("下载链接为空");

                File dlDir = getDownloadDir(); dlDir.mkdirs();
                File tmpFile = new File(dlDir, taskId + ".download");
                long existing = tmpFile.exists() ? tmpFile.length() : 0;
                long resumeFrom = (existing > 0 && existing < size) ? existing : 0;
                if (resumeFrom == 0 && tmpFile.exists()) tmpFile.delete();

                java.util.Map<String, String> headers = new java.util.HashMap<>();
                JSONObject dlHeaders = download.optJSONObject("headers");
                if (dlHeaders != null) {
                    java.util.Iterator<String> keys = dlHeaders.keys();
                    while (keys.hasNext()) { String k = keys.next(); headers.put(k, dlHeaders.optString(k, "")); }
                }

                dlDone = resumeFrom;
                api.downloadFile(dlUrl, headers, tmpFile.getAbsolutePath(), resumeFrom,
                    (downloaded, total, speed) -> {
                        dlDone = downloaded; dlTotal = total; dlSpeed = speed;
                        long elapsed = Math.max(1, System.currentTimeMillis() - dlStartTime);
                        dlAvgSpeed = downloaded * 1000 / elapsed;
                        updateNotify("下载: " + fileName);
                        try { api.reportProgress(taskId, downloaded, 0, total, speed); } catch (IOException ignored) {}
                    });

                dlDone = size; dlTotal = size;
                dlBytes += size;
                api.reportProgress(taskId, size, 0, size, 0);

                dlFile = "";
                phase = "下载完成";
            }

            if (!running.get()) return;

            // ── 上传阶段 ──
            ulFile = fileName;
            ulDone = 0; ulSpeed = 0;
            ulStartTime = System.currentTimeMillis();
            phase = "上传中";

            JSONObject sessionResp = api.getUploadSession(taskId);
            JSONObject session = sessionResp.getJSONObject("session");
            String uploadUrl = session.getString("uploadUrl");
            long totalSize = session.optLong("totalSize", size);
            int chunkSize = session.optInt("chunkSize", 20 * 1024 * 1024);
            ulTotal = totalSize;

            if ("local".equals(type)) {
                api.completeTask(taskId);
                phase = "完成";
                ulFile = "";
                return;
            }

            File uploadFile = new File(getDownloadDir(), taskId + ".download");
            uploadChunked(uploadFile, uploadUrl, totalSize, chunkSize, taskId, fileName);

            api.completeTask(taskId);
            ulBytes += totalSize;
            ulFile = "";
            phase = "完成";
            updateNotify("完成: " + fileName);

            if (uploadFile.exists()) uploadFile.delete();

        } catch (Exception e) {
            Log.e(TAG, "Task error: " + taskId, e);
            dlFile = ""; ulFile = "";
            phase = "失败";
            try { api.failTask(taskId, e.getMessage()); } catch (IOException ignored) {}
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
            int n;

            while ((n = fis.read(buf)) > 0 && running.get()) {
                byte[] chunk = new byte[n];
                System.arraycopy(buf, 0, chunk, 0, n);
                api.putChunk(uploadUrl, chunk, uploaded, totalSize);
                uploaded += n;
                ulDone = uploaded;
                ulTotal = totalSize;

                long now = System.currentTimeMillis();
                if (now - lastCbTime >= 3000) {
                    long elapsed = Math.max(1, now - startTime);
                    ulSpeed = uploaded * 1000 / elapsed;
                    ulAvgSpeed = ulSpeed;
                    updateNotify("上传: " + fileName);
                    try { api.reportProgress(taskId, 0, uploaded, totalSize, ulSpeed); } catch (IOException ignored) {}
                    lastCbTime = now;
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

    private Notification buildNotification(String text) {
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

        builder.setContentTitle("SJHL Worker")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .setContentIntent(pi)
            .addAction(android.R.drawable.ic_media_pause, "停止", stopPi);

        return builder.build();
    }

    private void updateNotify(String text) {
        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm != null) nm.notify(NOTIFY_ID, buildNotification(text));
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }

    @Override
    public void onDestroy() {
        stopWorker();
        super.onDestroy();
    }
}
