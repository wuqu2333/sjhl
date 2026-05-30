package com.sjhl.worker;

import android.app.Activity;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

public class MainActivity extends Activity {
    private AppSettings settings;
    private EditText serverInput;
    private TextView statusText, taskText, progressText, speedText, pendingText;
    private ProgressBar progressBar;
    private Button startBtn, stopBtn, saveBtn;
    private LinearLayout configCard, statusCard;
    private Handler uiHandler;
    private Runnable uiUpdater;
    private boolean serviceRunning = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        settings = new AppSettings(this);
        uiHandler = new Handler(Looper.getMainLooper());
        buildUI();
    }

    @Override
    protected void onResume() {
        super.onResume();
        startUIUpdates();
    }

    @Override
    protected void onPause() {
        super.onPause();
        stopUIUpdates();
    }

    private void startUIUpdates() {
        uiUpdater = new Runnable() {
            @Override
            public void run() {
                refreshUI();
                uiHandler.postDelayed(this, 1000);
            }
        };
        uiHandler.post(uiUpdater);
    }

    private void stopUIUpdates() {
        if (uiUpdater != null) {
            uiHandler.removeCallbacks(uiUpdater);
            uiUpdater = null;
        }
    }

    private void buildUI() {
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(16), dp(24), dp(16), dp(24));
        root.setBackgroundColor(Color.parseColor("#F5F5F5"));

        // ── Title ──
        TextView title = new TextView(this);
        title.setText("SJHL Worker");
        title.setTextSize(24);
        title.setTextColor(Color.parseColor("#1565C0"));
        title.setTypeface(null, Typeface.BOLD);
        title.setGravity(Gravity.CENTER);
        title.setPadding(0, 0, 0, dp(16));
        root.addView(title);

        // ── Server Config Card ──
        configCard = card();
        TextView configTitle = new TextView(this);
        configTitle.setText("主控地址");
        configTitle.setTextSize(16);
        configTitle.setTypeface(null, Typeface.BOLD);
        configTitle.setPadding(0, 0, 0, dp(8));
        configCard.addView(configTitle);

        serverInput = new EditText(this);
        serverInput.setHint("如 192.168.1.100:1115");
        serverInput.setTextSize(16);
        serverInput.setSingleLine();
        serverInput.setPadding(dp(12), dp(10), dp(12), dp(10));
        serverInput.setBackgroundColor(Color.parseColor("#F5F5F5"));
        String saved = settings.getServerUrl();
        if (!saved.isEmpty()) {
            serverInput.setText(saved.replace("http://", "").replace("https://", ""));
        }
        configCard.addView(serverInput);

        saveBtn = new Button(this);
        saveBtn.setText("保存 & 连接");
        saveBtn.setTextColor(Color.WHITE);
        saveBtn.setBackgroundColor(Color.parseColor("#1976D2"));
        saveBtn.setPadding(dp(12), dp(8), dp(12), dp(8));
        LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        bp.setMargins(0, dp(8), 0, 0);
        saveBtn.setLayoutParams(bp);
        saveBtn.setOnClickListener(v -> saveServer());
        configCard.addView(saveBtn);

        root.addView(configCard);

        // ── Status Card ──
        statusCard = card();

        TextView statusTitle = new TextView(this);
        statusTitle.setText("运行状态");
        statusTitle.setTextSize(16);
        statusTitle.setTypeface(null, Typeface.BOLD);
        statusCard.addView(statusTitle);

        statusText = new TextView(this);
        statusText.setText("未连接");
        statusText.setTextSize(14);
        statusText.setTextColor(Color.DKGRAY);
        statusText.setPadding(0, dp(4), 0, 0);
        statusCard.addView(statusText);

        pendingText = new TextView(this);
        pendingText.setText("待处理: -");
        pendingText.setTextSize(13);
        pendingText.setPadding(0, dp(2), 0, 0);
        statusCard.addView(pendingText);

        taskText = new TextView(this);
        taskText.setText("当前任务: -");
        taskText.setTextSize(13);
        taskText.setPadding(0, dp(2), 0, 0);
        statusCard.addView(taskText);

        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setMax(100);
        progressBar.setProgress(0);
        LinearLayout.LayoutParams pbp = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(6));
        pbp.setMargins(0, dp(8), 0, 0);
        progressBar.setLayoutParams(pbp);
        statusCard.addView(progressBar);

        progressText = new TextView(this);
        progressText.setText("0%");
        progressText.setTextSize(20);
        progressText.setTypeface(null, Typeface.BOLD);
        progressText.setTextColor(Color.parseColor("#1976D2"));
        progressText.setGravity(Gravity.CENTER);
        progressText.setPadding(0, dp(4), 0, 0);
        statusCard.addView(progressText);

        speedText = new TextView(this);
        speedText.setText("速度: -");
        speedText.setTextSize(13);
        speedText.setGravity(Gravity.CENTER);
        statusCard.addView(speedText);

        root.addView(statusCard);

        // ── Buttons Card ──
        LinearLayout btnCard = card();
        btnCard.setOrientation(LinearLayout.HORIZONTAL);
        btnCard.setGravity(Gravity.CENTER);

        startBtn = new Button(this);
        startBtn.setText("启动 Worker");
        startBtn.setTextColor(Color.WHITE);
        startBtn.setBackgroundColor(Color.parseColor("#4CAF50"));
        startBtn.setPadding(dp(24), dp(10), dp(24), dp(10));
        startBtn.setOnClickListener(v -> startWorker());
        btnCard.addView(startBtn);

        View spacer = new View(this);
        spacer.setLayoutParams(new LinearLayout.LayoutParams(dp(16), 1));
        btnCard.addView(spacer);

        stopBtn = new Button(this);
        stopBtn.setText("停止");
        stopBtn.setTextColor(Color.WHITE);
        stopBtn.setBackgroundColor(Color.parseColor("#F44336"));
        stopBtn.setPadding(dp(24), dp(10), dp(24), dp(10));
        stopBtn.setEnabled(false);
        stopBtn.setOnClickListener(v -> stopWorker());
        btnCard.addView(stopBtn);

        root.addView(btnCard);

        // ── Info ──
        TextView info = new TextView(this);
        info.setText("Worker 模式：手机从主控拉取任务并在本机完成下载和上传。\n"
            + "请确保主控已开启 Worker 模式（设置 → Worker 模式）。\n"
            + "上传使用世纪互联 Graph API 分片上传，下载支持断点续传。");
        info.setTextSize(12);
        info.setTextColor(Color.GRAY);
        info.setPadding(dp(12), dp(16), dp(12), 0);
        info.setLineSpacing(dp(4), 1f);
        root.addView(info);

        scroll.addView(root);
        setContentView(scroll);
    }

    // ── Actions ───────────────────────────────────────────
    private void saveServer() {
        String input = serverInput.getText().toString().trim();
        if (input.isEmpty()) {
            toast("请输入主控地址");
            return;
        }
        settings.setServerUrl(input);
        toast("已保存: " + settings.getServerUrl());
    }

    private void startWorker() {
        if (!settings.hasServer()) {
            toast("请先设置主控地址");
            return;
        }
        Intent intent = new Intent(this, WorkerService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent);
        } else {
            startService(intent);
        }
        serviceRunning = true;
        startBtn.setEnabled(false);
        stopBtn.setEnabled(true);
        statusText.setText("启动中...");
    }

    private void stopWorker() {
        Intent intent = new Intent(this, WorkerService.class);
        intent.setAction("STOP");
        startService(intent);
        serviceRunning = false;
        startBtn.setEnabled(true);
        stopBtn.setEnabled(false);
        statusText.setText("已停止");
        taskText.setText("当前任务: -");
        progressText.setText("0%");
        speedText.setText("速度: -");
        progressBar.setProgress(0);
    }

    private void refreshUI() {
        WorkerService svc = WorkerService.instance;
        if (svc != null && svc.running.get()) {
            serviceRunning = true;
            startBtn.setEnabled(false);
            stopBtn.setEnabled(true);

            statusText.setText(svc.statusText);
            taskText.setText("当前任务: " + (svc.taskFile.isEmpty() ? "空闲" : svc.taskFile));
            pendingText.setText("待处理: " + svc.pendingCount + " 个任务");

            long done = svc.progressDone;
            long total = svc.progressTotal;
            if (total > 0) {
                int pct = (int)(done * 100 / total);
                progressBar.setProgress(pct);
                progressText.setText(pct + "%");
                speedText.setText("速度: " + fmtSpeed(svc.speedBps) + "  " + fmtSize(done) + " / " + fmtSize(total));
            } else {
                progressBar.setProgress(0);
                progressText.setText("-");
                speedText.setText("速度: -");
            }
        } else {
            serviceRunning = false;
            startBtn.setEnabled(true);
            stopBtn.setEnabled(false);
            if (statusText.getText().toString().equals("启动中...")) {
                statusText.setText("未连接");
            }
        }
    }

    // ── Helpers ───────────────────────────────────────────
    private LinearLayout card() {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(16), dp(12), dp(16), dp(12));
        card.setBackgroundColor(Color.WHITE);
        card.setElevation(dp(2));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, 0, 0, dp(12));
        card.setLayoutParams(lp);
        return card;
    }

    private int dp(int px) {
        return (int)(px * getResources().getDisplayMetrics().density + 0.5f);
    }

    private void toast(String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
    }

    private String fmtSize(long bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return String.format("%.1f KB", bytes / 1024.0);
        if (bytes < 1024L * 1024 * 1024) return String.format("%.1f MB", bytes / (1024.0 * 1024));
        return String.format("%.2f GB", bytes / (1024.0 * 1024 * 1024));
    }

    private String fmtSpeed(long bps) {
        if (bps < 1024) return bps + " B/s";
        if (bps < 1024 * 1024) return String.format("%.1f KB/s", bps / 1024.0);
        return String.format("%.1f MB/s", bps / (1024.0 * 1024));
    }
}
