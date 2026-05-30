package com.sjhl.worker;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TabHost;
import android.widget.TabWidget;
import android.widget.TextView;
import android.widget.Toast;

public class MainActivity extends Activity {
    private AppSettings settings;
    private EditText serverInput;
    private Button startBtn, stopBtn;

    // 下载卡片
    private TextView dlPhaseText, dlFileText, dlProgressText, dlSpeedText, dlAvgText, dlTotalText;
    private ProgressBar dlProgress;
    // 上传卡片
    private TextView ulPhaseText, ulFileText, ulProgressText, ulSpeedText, ulAvgText, ulTotalText;
    private ProgressBar ulProgress;
    // 状态
    private TextView connStatus, pendingCountText, completedCountText;

    private Handler uiHandler;
    private Runnable uiUpdater;

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
        uiUpdater = new Runnable() { @Override public void run() { refreshUI(); uiHandler.postDelayed(this, 1000); } };
        uiHandler.post(uiUpdater);
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (uiUpdater != null) { uiHandler.removeCallbacks(uiUpdater); uiUpdater = null; }
    }

    private void buildUI() {
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(12), dp(16), dp(12), dp(16));
        root.setBackgroundColor(Color.parseColor("#F0F2F5"));

        // ── Title ──
        TextView title = new TextView(this);
        title.setText("SJHL Worker");
        title.setTextSize(22);
        title.setTextColor(Color.parseColor("#1565C0"));
        title.setTypeface(null, Typeface.BOLD);
        title.setGravity(Gravity.CENTER);
        title.setPadding(0, 0, 0, dp(12));
        root.addView(title);

        // ── Server Config ──
        LinearLayout cfgCard = card();
        serverInput = new EditText(this);
        serverInput.setHint("主控地址 如 192.168.1.100:1115");
        serverInput.setTextSize(14);
        serverInput.setSingleLine();
        serverInput.setPadding(dp(8), dp(6), dp(8), dp(6));
        String saved = settings.getServerUrl();
        if (!saved.isEmpty()) serverInput.setText(saved.replace("http://", "").replace("https://", ""));
        cfgCard.addView(serverInput);

        LinearLayout btnRow = new LinearLayout(this);
        btnRow.setOrientation(LinearLayout.HORIZONTAL);
        btnRow.setPadding(0, dp(6), 0, 0);

        Button saveBtn = new Button(this);
        saveBtn.setText("保存");
        saveBtn.setTextColor(Color.WHITE);
        saveBtn.setBackgroundColor(Color.parseColor("#1976D2"));
        saveBtn.setOnClickListener(v -> { settings.setServerUrl(serverInput.getText().toString().trim()); toast("已保存"); });
        btnRow.addView(saveBtn);

        View sp = new View(this); sp.setLayoutParams(new LinearLayout.LayoutParams(dp(8), 1)); btnRow.addView(sp);

        startBtn = new Button(this);
        startBtn.setText("启动");
        startBtn.setTextColor(Color.WHITE);
        startBtn.setBackgroundColor(Color.parseColor("#4CAF50"));
        startBtn.setOnClickListener(v -> startWorker());
        btnRow.addView(startBtn);

        View sp2 = new View(this); sp2.setLayoutParams(new LinearLayout.LayoutParams(dp(8), 1)); btnRow.addView(sp2);

        stopBtn = new Button(this);
        stopBtn.setText("停止");
        stopBtn.setTextColor(Color.WHITE);
        stopBtn.setBackgroundColor(Color.parseColor("#F44336"));
        stopBtn.setEnabled(false);
        stopBtn.setOnClickListener(v -> stopWorker());
        btnRow.addView(stopBtn);

        cfgCard.addView(btnRow);
        root.addView(cfgCard);

        // ── 状态概览 ──
        LinearLayout statBar = new LinearLayout(this);
        statBar.setOrientation(LinearLayout.HORIZONTAL);
        statBar.setPadding(0, dp(4), 0, dp(4));
        statBar.setGravity(Gravity.CENTER_VERTICAL);

        connStatus = statText("未连接", Color.GRAY);
        statBar.addView(connStatus);

        View dot1 = new View(this); dot1.setLayoutParams(new LinearLayout.LayoutParams(dp(12), 1)); statBar.addView(dot1);
        pendingCountText = statText("待处理: -", Color.DKGRAY);
        statBar.addView(pendingCountText);

        View dot2 = new View(this); dot2.setLayoutParams(new LinearLayout.LayoutParams(dp(12), 1)); statBar.addView(dot2);
        completedCountText = statText("已完成: -", Color.DKGRAY);
        statBar.addView(completedCountText);
        root.addView(statBar);

        // ── TabHost: 下载 | 上传 ──
        TabHost tabHost = new TabHost(this);
        tabHost.setLayoutParams(new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        TabWidget tw = new TabWidget(this);
        tw.setId(android.R.id.tabs);
        tabHost.addView(tw);

        LinearLayout tabContent = new LinearLayout(this);
        tabContent.setId(android.R.id.tabcontent);
        tabContent.setOrientation(LinearLayout.VERTICAL);
        tabHost.addView(tabContent);

        tabHost.setup();

        // 下载 Tab
        TabHost.TabSpec dlTab = tabHost.newTabSpec("download");
        dlTab.setIndicator(" 下载 ");
        LinearLayout dlCard = buildProgressCard("download");
        dlTab.setContent(tabId -> dlCard);
        tabHost.addTab(dlTab);

        // 上传 Tab
        TabHost.TabSpec ulTab = tabHost.newTabSpec("upload");
        ulTab.setIndicator(" 上传 ");
        LinearLayout ulCard = buildProgressCard("upload");
        ulTab.setContent(tabId -> ulCard);
        tabHost.addTab(ulTab);

        // Style tabs
        for (int i = 0; i < tw.getChildCount(); i++) {
            View tab = tw.getChildAt(i);
            tab.setPadding(dp(24), dp(8), dp(24), dp(8));
            if (tab instanceof TextView) {
                ((TextView) tab).setTextSize(16);
                ((TextView) tab).setTypeface(null, Typeface.BOLD);
            }
        }

        root.addView(tabHost);

        scroll.addView(root);
        setContentView(scroll);
    }

    private LinearLayout buildProgressCard(String type) {
        boolean isDl = "download".equals(type);
        LinearLayout card = card();
        card.setPadding(dp(12), dp(8), dp(12), dp(8));

        if (isDl) {
            dlPhaseText = titleText("等待中");
            card.addView(dlPhaseText);

            dlFileText = normalText("文件: -");
            card.addView(dlFileText);

            dlProgress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
            dlProgress.setMax(100);
            LinearLayout.LayoutParams pp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(8));
            pp.setMargins(0, dp(6), 0, 0);
            dlProgress.setLayoutParams(pp);
            card.addView(dlProgress);

            dlProgressText = bigText("-");
            card.addView(dlProgressText);

            dlSpeedText = normalText("速度: -");
            card.addView(dlSpeedText);

            dlAvgText = normalText("平均: -");
            card.addView(dlAvgText);

            dlTotalText = normalText("累计: -");
            card.addView(dlTotalText);
        } else {
            ulPhaseText = titleText("等待中");
            card.addView(ulPhaseText);

            ulFileText = normalText("文件: -");
            card.addView(ulFileText);

            ulProgress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
            ulProgress.setMax(100);
            LinearLayout.LayoutParams pp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(8));
            pp.setMargins(0, dp(6), 0, 0);
            ulProgress.setLayoutParams(pp);
            card.addView(ulProgress);

            ulProgressText = bigText("-");
            card.addView(ulProgressText);

            ulSpeedText = normalText("速度: -");
            card.addView(ulSpeedText);

            ulAvgText = normalText("平均: -");
            card.addView(ulAvgText);

            ulTotalText = normalText("累计: -");
            card.addView(ulTotalText);
        }

        return card;
    }

    // ── UI helpers ────────────────────────────────────────
    private TextView titleText(String t) {
        TextView tv = new TextView(this);
        tv.setText(t); tv.setTextSize(15); tv.setTypeface(null, Typeface.BOLD);
        tv.setTextColor(Color.parseColor("#1565C0")); tv.setPadding(0, 0, 0, dp(2));
        return tv;
    }

    private TextView bigText(String t) {
        TextView tv = new TextView(this);
        tv.setText(t); tv.setTextSize(22); tv.setTypeface(null, Typeface.BOLD);
        tv.setTextColor(Color.parseColor("#1976D2")); tv.setGravity(Gravity.CENTER);
        return tv;
    }

    private TextView normalText(String t) {
        TextView tv = new TextView(this);
        tv.setText(t); tv.setTextSize(13); tv.setTextColor(Color.DKGRAY);
        return tv;
    }

    private TextView statText(String t, int color) {
        TextView tv = new TextView(this);
        tv.setText(t); tv.setTextSize(13); tv.setTextColor(color);
        return tv;
    }

    private LinearLayout card() {
        LinearLayout c = new LinearLayout(this);
        c.setOrientation(LinearLayout.VERTICAL);
        c.setPadding(dp(12), dp(10), dp(12), dp(10));
        c.setBackgroundColor(Color.WHITE);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, 0, 0, dp(8));
        c.setLayoutParams(lp);
        return c;
    }

    private int dp(int px) { return (int)(px * getResources().getDisplayMetrics().density + 0.5f); }
    private void toast(String msg) { Toast.makeText(this, msg, Toast.LENGTH_SHORT).show(); }

    // ── Worker control ────────────────────────────────────
    private void startWorker() {
        if (!settings.hasServer()) { toast("请先设置主控地址"); return; }
        Intent intent = new Intent(this, WorkerService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent);
        else startService(intent);
        startBtn.setEnabled(false); stopBtn.setEnabled(true);
    }

    private void stopWorker() {
        Intent intent = new Intent(this, WorkerService.class);
        intent.setAction("STOP"); startService(intent);
        startBtn.setEnabled(true); stopBtn.setEnabled(false);
    }

    // ── UI refresh ────────────────────────────────────────
    private void refreshUI() {
        WorkerService s = WorkerService.instance;
        boolean running = s != null && s.running.get();
        startBtn.setEnabled(!running);
        stopBtn.setEnabled(running);

        if (running) {
            connStatus.setText("运行中");
            connStatus.setTextColor(Color.parseColor("#4CAF50"));
            pendingCountText.setText("待处理: " + s.pendingCount);
            completedCountText.setText("已完成: " + s.completedCount);

            // 下载
            String dlPhase = s.phase.contains("下载") || s.phase.contains("认领") ? s.phase : "等待下载";
            if (s.dlFile.isEmpty() && !s.phase.contains("下载")) dlPhase = "空闲";
            dlPhaseText.setText(dlPhase);
            dlFileText.setText("文件: " + (s.dlFile.isEmpty() ? "-" : s.dlFile));
            if (s.dlTotal > 0) {
                int pct = (int)(s.dlDone * 100 / s.dlTotal);
                dlProgress.setProgress(pct);
                dlProgressText.setText(pct + "%");
                dlSpeedText.setText("速度: " + fmtSpeed(s.dlSpeed));
                dlAvgText.setText("平均: " + fmtSpeed(s.dlAvgSpeed));
            } else {
                dlProgress.setProgress(0);
                dlProgressText.setText("-");
                dlSpeedText.setText("速度: -");
                dlAvgText.setText("平均: -");
            }
            dlTotalText.setText("累计下载: " + fmtSize(s.dlBytes));

            // 上传
            String ulPhase = s.phase.contains("上传") ? s.phase : "等待上传";
            if (s.ulFile.isEmpty() && !s.phase.contains("上传")) ulPhase = "空闲";
            ulPhaseText.setText(ulPhase);
            ulFileText.setText("文件: " + (s.ulFile.isEmpty() ? "-" : s.ulFile));
            if (s.ulTotal > 0) {
                int pct = (int)(s.ulDone * 100 / s.ulTotal);
                ulProgress.setProgress(pct);
                ulProgressText.setText(pct + "%");
                ulSpeedText.setText("速度: " + fmtSpeed(s.ulSpeed));
                ulAvgText.setText("平均: " + fmtSpeed(s.ulAvgSpeed));
            } else {
                ulProgress.setProgress(0);
                ulProgressText.setText("-");
                ulSpeedText.setText("速度: -");
                ulAvgText.setText("平均: -");
            }
            ulTotalText.setText("累计上传: " + fmtSize(s.ulBytes));
        } else {
            connStatus.setText("未连接");
            connStatus.setTextColor(Color.GRAY);
            pendingCountText.setText("待处理: -");
            completedCountText.setText("已完成: -");
            dlPhaseText.setText("等待中"); dlFileText.setText("文件: -");
            dlProgress.setProgress(0); dlProgressText.setText("-");
            dlSpeedText.setText("速度: -"); dlAvgText.setText("平均: -");
            ulPhaseText.setText("等待中"); ulFileText.setText("文件: -");
            ulProgress.setProgress(0); ulProgressText.setText("-");
            ulSpeedText.setText("速度: -"); ulAvgText.setText("平均: -");
        }
    }

    private String fmtSize(long bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1048576) return String.format("%.1f KB", bytes / 1024.0);
        if (bytes < 1073741824L) return String.format("%.1f MB", bytes / 1048576.0);
        return String.format("%.2f GB", bytes / 1073741824.0);
    }

    private String fmtSpeed(long bps) {
        if (bps < 1024) return bps + " B/s";
        if (bps < 1048576) return String.format("%.1f KB/s", bps / 1024.0);
        return String.format("%.1f MB/s", bps / 1048576.0);
    }
}
