package com.sjhl.spmanager;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Date;
import java.util.Locale;

public class MainActivity extends Activity {
    private static final int REQUEST_PICK_FILE = 301;
    private static final int BLUE = Color.rgb(22, 119, 255);
    private static final int BG = Color.rgb(245, 247, 250);
    private static final int MUTED = Color.rgb(100, 116, 139);
    private static final int TEXT = Color.rgb(15, 23, 42);
    private static final int RED = Color.rgb(220, 38, 38);
    private static final int GREEN = Color.rgb(22, 163, 74);

    private LocalStore store;
    private LinearLayout content;
    private TextView title;
    private TextView notice;
    private String activeTab = "dashboard";
    private String selectedSpProfileId = "";
    private String selectedPan115AccountId = "";
    private String spCurrentPath = "";
    private String pan115CurrentCid = "0";
    private String pan115CurrentPath = "";
    private String pan115SearchKeyword = "";
    private final ArrayList<String> pan115CidStack = new ArrayList<>();
    private final ArrayList<String> pan115PathStack = new ArrayList<>();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        store = new LocalStore(this);
        requestNotificationPermission();
        buildShell();
        showDashboard();
        autoStartTransferServiceIfNeeded();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_PICK_FILE || resultCode != RESULT_OK || data == null || data.getData() == null) {
            return;
        }
        Uri uri = data.getData();
        int flags = data.getFlags() & Intent.FLAG_GRANT_READ_URI_PERMISSION;
        try {
            getContentResolver().takePersistableUriPermission(uri, flags);
        } catch (Exception ignored) {
        }
        showLocalTaskDialog(uri, queryDisplayName(uri), querySize(uri));
    }

    private void buildShell() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(BG);
        setContentView(root);

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(dp(14), dp(10), dp(10), dp(10));
        header.setBackgroundColor(Color.WHITE);
        root.addView(header, new LinearLayout.LayoutParams(-1, dp(60)));

        TextView logo = label("☑", 26, TEXT, true);
        header.addView(logo, new LinearLayout.LayoutParams(dp(44), -1));
        title = label("工作台", 20, TEXT, true);
        header.addView(title, new LinearLayout.LayoutParams(0, -1, 1));
        Button refresh = smallButton("刷新");
        refresh.setOnClickListener(v -> refreshActive());
        header.addView(refresh);

        notice = label("", 14, RED, false);
        notice.setPadding(dp(14), dp(8), dp(14), dp(8));
        notice.setVisibility(View.GONE);
        root.addView(notice, new LinearLayout.LayoutParams(-1, -2));

        ScrollView scroll = new ScrollView(this);
        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(12), dp(12), dp(12), dp(18));
        scroll.addView(content);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));

        LinearLayout nav = new LinearLayout(this);
        nav.setOrientation(LinearLayout.HORIZONTAL);
        nav.setPadding(dp(8), dp(8), dp(8), dp(8));
        nav.setBackgroundColor(Color.WHITE);
        root.addView(nav, new LinearLayout.LayoutParams(-1, dp(72)));
        addNav(nav, "工作台", this::showDashboard);
        addNav(nav, "文件", this::showSpFiles);
        addNav(nav, "115", this::showPan115Browse);
        addNav(nav, "同步", this::showSyncJobs);
        addNav(nav, "传输", this::showTransfers);
        addNav(nav, "设置", this::showSettings);
    }

    private void addNav(LinearLayout nav, String text, Runnable action) {
        Button button = new Button(this);
        button.setText(text);
        button.setAllCaps(false);
        button.setTextSize(14);
        button.setOnClickListener(v -> action.run());
        nav.addView(button, new LinearLayout.LayoutParams(0, -1, 1));
    }

    private void showDashboard() {
        activeTab = "dashboard";
        title.setText("工作台");
        content.removeAllViews();
        JSONObject state = store.state();
        JSONArray profiles = state.optJSONArray("profiles");
        JSONArray accounts = state.optJSONArray("pan115Accounts");
        JSONArray pools = state.optJSONArray("capacityPools");
        JSONArray tasks = state.optJSONArray("tasks");

        long used = 0L;
        int enabledProfiles = 0;
        if (profiles != null) {
            for (int i = 0; i < profiles.length(); i++) {
                JSONObject profile = profiles.optJSONObject(i);
                if (profile != null && profile.optBoolean("capacityEnabled", true)) {
                    enabledProfiles++;
                    used += profile.optLong("quotaUsed");
                }
            }
        }

        int queued = 0;
        int running = 0;
        int failed = 0;
        int done = 0;
        long speed = 0L;
        long todayBytes = 0L;
        int todayFiles = 0;
        if (tasks != null) {
            for (int i = 0; i < tasks.length(); i++) {
                JSONObject task = tasks.optJSONObject(i);
                if (task == null) {
                    continue;
                }
                String status = task.optString("status");
                if ("queued".equals(status)) queued++;
                if ("running".equals(status)) running++;
                if ("failed".equals(status)) failed++;
                if ("done".equals(status)) done++;
                speed += task.optLong("speed");
                if ("done".equals(status) && isToday(task.optLong("finishedAt", task.optLong("updatedAt")))) {
                    todayFiles++;
                    todayBytes += task.optLong("size");
                }
            }
        }

        LinearLayout row1 = row();
        row1.addView(metric("容量池", safeLength(pools) + " 个"));
        row1.addView(metric("SP", enabledProfiles + " 个"));
        content.addView(row1);
        LinearLayout row2 = row();
        row2.addView(metric("传输任务", running + " 上传 / " + queued + " 等待 / " + failed + " 失败"));
        row2.addView(metric("已用容量", formatBytes(used)));
        content.addView(row2);
        content.addView(cardText("总上传速率", formatSpeed(speed)));
        content.addView(cardText("今日上传", formatBytes(todayBytes) + " · " + todayFiles + " 个文件"));
        content.addView(cardText("本机配置", safeLength(accounts) + " 个 115 账号，" + done + " 个已完成任务"));

        LinearLayout actions = row();
        Button local = primaryButton("上传本地文件");
        local.setOnClickListener(v -> openFilePicker());
        Button pan115 = smallButton("新增 115 任务");
        pan115.setOnClickListener(v -> showPan115TaskDialog());
        actions.addView(local);
        actions.addView(pan115);
        content.addView(actions);

        LinearLayout serviceActions = row();
        Button start = primaryButton("启动传输服务");
        start.setOnClickListener(v -> startTransferService());
        Button stop = smallButton("停止服务");
        stop.setOnClickListener(v -> stopTransferService());
        serviceActions.addView(start);
        serviceActions.addView(stop);
        content.addView(serviceActions);
    }

    private void showSpFiles() {
        activeTab = "sp-files";
        title.setText("SP 文件");
        content.removeAllViews();
        Selection profiles = profileSelection();
        if (profiles.ids.isEmpty()) {
            content.addView(cardText("未配置 SP", "请先到设置里添加 SharePoint"));
            return;
        }
        if (selectedSpProfileId.isEmpty()) {
            selectedSpProfileId = profiles.selectedId();
        } else {
            profiles.select(selectedSpProfileId);
        }

        LinearLayout top = card();
        top.addView(label("选择 SP", 13, TEXT, true));
        top.addView(profiles.spinner);
        EditText path = input("路径，留空为根目录");
        path.setText(spCurrentPath);
        Button open = primaryButton("打开");
        open.setOnClickListener(v -> {
            selectedSpProfileId = profiles.selectedId();
            spCurrentPath = path.getText().toString().trim();
            loadSpChildren(selectedSpProfileId, spCurrentPath);
        });
        LinearLayout actions = row();
        Button root = smallButton("根目录");
        root.setOnClickListener(v -> {
            selectedSpProfileId = profiles.selectedId();
            spCurrentPath = "";
            showSpFiles();
        });
        Button parent = smallButton("上级");
        parent.setOnClickListener(v -> {
            selectedSpProfileId = profiles.selectedId();
            spCurrentPath = parentPath(spCurrentPath);
            showSpFiles();
        });
        Button folder = smallButton("新建文件夹");
        folder.setOnClickListener(v -> {
            selectedSpProfileId = profiles.selectedId();
            showCreateSpFolderDialog(selectedSpProfileId, spCurrentPath);
        });
        Button scan = smallButton("扫描全部指纹");
        scan.setOnClickListener(v -> scanAllSharePoints());
        Button fingerprints = smallButton("查看指纹");
        fingerprints.setOnClickListener(v -> showFingerprints());
        actions.addView(root);
        actions.addView(parent);
        actions.addView(folder);
        actions.addView(scan);
        actions.addView(fingerprints);
        top.addView(path);
        top.addView(open);
        top.addView(actions);
        content.addView(top);
        loadSpChildren(selectedSpProfileId, spCurrentPath);
    }

    private void loadSpChildren(String profileId, String path) {
        content.addView(cardText("加载中", "正在读取 SP 目录..."));
        runBackground(() -> {
            JSONObject profile = profileById(profileId);
            if (profile == null) {
                throw new IllegalStateException("SP 配置不存在");
            }
            return new GraphUploader().listChildren(profile, path);
        }, result -> {
            removeLoadingCards();
            org.json.JSONArray items = (org.json.JSONArray) result;
            if (items.length() == 0) {
                content.addView(cardText("空目录", "当前目录没有文件"));
                return;
            }
            for (int i = 0; i < items.length(); i++) {
                JSONObject item = items.optJSONObject(i);
                if (item != null) {
                    content.addView(spItemCard(profileId, item));
                }
            }
        });
    }

    private View spItemCard(String profileId, JSONObject item) {
        LinearLayout card = card();
        boolean folder = "folder".equals(item.optString("type"));
        card.addView(label((folder ? "D  " : "F  ") + item.optString("name"), 15, folder ? BLUE : TEXT, true));
        card.addView(label(formatBytes(item.optLong("size")) + " · " + item.optString("path"), 12, MUTED, false));
        LinearLayout actions = row();
        if (folder) {
            Button open = smallButton("打开");
            open.setOnClickListener(v -> {
                spCurrentPath = item.optString("path");
                showSpFiles();
            });
            actions.addView(open);
        }
        Button rename = smallButton("重命名");
        rename.setOnClickListener(v -> showRenameSpItemDialog(profileId, item));
        actions.addView(rename);
        Button delete = smallButton("删除");
        delete.setTextColor(RED);
        delete.setOnClickListener(v -> runBackground(() -> {
            JSONObject profile = profileById(profileId);
            new GraphUploader().deleteItem(profile, item.optString("id"));
            return true;
        }, ignored -> {
            showNotice("SP 文件已删除", false);
            showSpFiles();
        }));
        actions.addView(delete);
        card.addView(actions);
        return card;
    }

    private void showRenameSpItemDialog(String profileId, JSONObject item) {
        EditText name = input("新名称");
        name.setText(item.optString("name"));
        new AlertDialog.Builder(this)
                .setTitle("重命名 SP 文件")
                .setView(name)
                .setPositiveButton("保存", (dialog, which) -> runBackground(() -> {
                    JSONObject profile = profileById(profileId);
                    new GraphUploader().renameItem(profile, item.optString("id"), name.getText().toString());
                    return true;
                }, ignored -> {
                    showNotice("SP 文件已重命名", false);
                    showSpFiles();
                }))
                .setNegativeButton("取消", null)
                .show();
    }

    private void showPan115Browse() {
        activeTab = "pan115";
        title.setText("115 浏览");
        content.removeAllViews();
        Selection accounts = accountSelection();
        if (accounts.ids.isEmpty()) {
            content.addView(cardText("未配置 115", "请先到设置里添加 115 Cookie 或 Open Token"));
            return;
        }
        if (selectedPan115AccountId.isEmpty()) {
            selectedPan115AccountId = accounts.selectedId();
        } else {
            accounts.select(selectedPan115AccountId);
        }
        LinearLayout top = card();
        top.addView(label("115 账号", 13, TEXT, true));
        top.addView(accounts.spinner);
        top.addView(cardText("当前路径", pan115CurrentPath.isEmpty() ? "/" : pan115CurrentPath));
        EditText search = input("搜索文件");
        search.setText(pan115SearchKeyword);
        LinearLayout actions = row();
        Button switchAccount = smallButton("切换账号");
        switchAccount.setOnClickListener(v -> {
            selectedPan115AccountId = accounts.selectedId();
            pan115CurrentCid = "0";
            pan115CurrentPath = "";
            pan115SearchKeyword = "";
            pan115CidStack.clear();
            pan115PathStack.clear();
            showPan115Browse();
        });
        Button root = smallButton("根目录");
        root.setOnClickListener(v -> {
            selectedPan115AccountId = accounts.selectedId();
            pan115CurrentCid = "0";
            pan115CurrentPath = "";
            pan115SearchKeyword = "";
            pan115CidStack.clear();
            pan115PathStack.clear();
            showPan115Browse();
        });
        Button parent = smallButton("上级");
        parent.setOnClickListener(v -> {
            selectedPan115AccountId = accounts.selectedId();
            if (!pan115CidStack.isEmpty()) {
                int last = pan115CidStack.size() - 1;
                pan115CurrentCid = pan115CidStack.remove(last);
                pan115CurrentPath = pan115PathStack.remove(last);
            } else {
                pan115CurrentCid = "0";
                pan115CurrentPath = "";
            }
            showPan115Browse();
        });
        Button folder = smallButton("新建文件夹");
        folder.setOnClickListener(v -> {
            selectedPan115AccountId = accounts.selectedId();
            showCreate115FolderDialog(selectedPan115AccountId, pan115CurrentCid);
        });
        Button sync = primaryButton("同步此目录");
        sync.setOnClickListener(v -> {
            selectedPan115AccountId = accounts.selectedId();
            showCreateSyncFrom115Dialog(selectedPan115AccountId, pan115CurrentCid, pan115CurrentPath);
        });
        Button searchBtn = smallButton("搜索");
        searchBtn.setOnClickListener(v -> {
            selectedPan115AccountId = accounts.selectedId();
            pan115SearchKeyword = search.getText().toString().trim();
            if (pan115SearchKeyword.isEmpty()) {
                showPan115Browse();
            } else {
                loadPan115Search(selectedPan115AccountId, pan115CurrentCid, pan115SearchKeyword);
            }
        });
        Button clearSearch = smallButton("清空");
        clearSearch.setOnClickListener(v -> {
            selectedPan115AccountId = accounts.selectedId();
            pan115SearchKeyword = "";
            showPan115Browse();
        });
        actions.addView(switchAccount);
        actions.addView(root);
        actions.addView(parent);
        actions.addView(folder);
        actions.addView(sync);
        actions.addView(searchBtn);
        actions.addView(clearSearch);
        top.addView(actions);
        top.addView(search);
        content.addView(top);
        if (pan115SearchKeyword.isEmpty()) {
            loadPan115Children(selectedPan115AccountId, pan115CurrentCid);
        } else {
            loadPan115Search(selectedPan115AccountId, pan115CurrentCid, pan115SearchKeyword);
        }
    }

    private void loadPan115Children(String accountId, String cid) {
        content.addView(cardText("加载中", "正在读取 115 目录..."));
        runBackground(() -> {
            JSONObject state = store.state();
            JSONObject account = store.findPan115Account(state, accountId);
            if (account == null) {
                throw new IllegalStateException("115 账号不存在");
            }
            Pan115OpenClient.JSONArrayResult result = new Pan115OpenClient().listDir(account, cid);
            store.updatePan115Tokens(accountId, result.accessToken, result.refreshToken);
            return result.items;
        }, result -> {
            removeLoadingCards();
            org.json.JSONArray items = (org.json.JSONArray) result;
            if (items.length() == 0) {
                content.addView(cardText("空目录", "当前 115 目录为空"));
                return;
            }
            for (int i = 0; i < items.length(); i++) {
                JSONObject item = items.optJSONObject(i);
                if (item != null) {
                    content.addView(pan115ItemCard(item));
                }
            }
        });
    }

    private void loadPan115Search(String accountId, String cid, String keyword) {
        content.addView(cardText("加载中", "正在搜索 115 文件..."));
        runBackground(() -> {
            JSONObject state = store.state();
            JSONObject account = store.findPan115Account(state, accountId);
            if (account == null) {
                throw new IllegalStateException("115 账号不存在");
            }
            Pan115OpenClient.JSONArrayResult result = new Pan115OpenClient().searchFiles(account, keyword, cid);
            store.updatePan115Tokens(accountId, result.accessToken, result.refreshToken);
            return result.items;
        }, result -> {
            removeLoadingCards();
            org.json.JSONArray items = (org.json.JSONArray) result;
            if (items.length() == 0) {
                content.addView(cardText("无结果", "没有找到匹配的文件"));
                return;
            }
            for (int i = 0; i < items.length(); i++) {
                JSONObject item = items.optJSONObject(i);
                if (item != null) {
                    content.addView(pan115ItemCard(item));
                }
            }
        });
    }

    private View pan115ItemCard(JSONObject item) {
        LinearLayout card = card();
        boolean folder = item.optBoolean("isDir");
        card.addView(label((folder ? "D  " : "F  ") + item.optString("name"), 15, folder ? BLUE : TEXT, true));
        card.addView(label(formatBytes(item.optLong("size")) + " · " + item.optString("pickCode"), 12, MUTED, false));
        LinearLayout actions = row();
        if (folder) {
            Button open = smallButton("打开");
            open.setOnClickListener(v -> {
                pan115CidStack.add(pan115CurrentCid);
                pan115PathStack.add(pan115CurrentPath);
                pan115CurrentCid = item.optString("cid");
                pan115CurrentPath = joinPath(pan115CurrentPath, item.optString("name"));
                pan115SearchKeyword = "";
                showPan115Browse();
            });
            actions.addView(open);
            Button sync = smallButton("同步");
            sync.setOnClickListener(v -> showCreateSyncFrom115Dialog(
                    selectedPan115AccountId,
                    item.optString("cid"),
                    joinPath(pan115CurrentPath, item.optString("name"))
            ));
            actions.addView(sync);
            Button importTasks = smallButton("导入任务");
            importTasks.setOnClickListener(v -> showImportPan115FolderDialog(item));
            actions.addView(importTasks);
        } else {
            Button transfer = smallButton("加入传输");
            transfer.setOnClickListener(v -> showPan115TaskFromItemDialog(item));
            actions.addView(transfer);
        }
        Button rename = smallButton("重命名");
        rename.setOnClickListener(v -> showRenamePan115ItemDialog(item));
        Button delete = smallButton("删除");
        delete.setTextColor(RED);
        delete.setOnClickListener(v -> deletePan115Item(item));
        actions.addView(rename);
        actions.addView(delete);
        card.addView(actions);
        return card;
    }

    private void showRenamePan115ItemDialog(JSONObject item) {
        EditText name = input("新名称");
        name.setText(item.optString("name"));
        new AlertDialog.Builder(this)
                .setTitle("重命名 115 文件")
                .setView(name)
                .setPositiveButton("保存", (dialog, which) -> runBackground(() -> {
                    JSONObject account = store.findPan115Account(store.state(), selectedPan115AccountId);
                    JSONObject result = new Pan115OpenClient().renameFile(account, item.optString("fid"), name.getText().toString());
                    store.updatePan115Tokens(selectedPan115AccountId, result.optString("accessToken"), result.optString("refreshToken"));
                    return true;
                }, ignored -> {
                    showNotice("115 文件已重命名", false);
                    showPan115Browse();
                }))
                .setNegativeButton("取消", null)
                .show();
    }

    private void deletePan115Item(JSONObject item) {
        new AlertDialog.Builder(this)
                .setTitle("删除 115 文件")
                .setMessage("确认删除 " + item.optString("name") + " ?")
                .setPositiveButton("删除", (dialog, which) -> runBackground(() -> {
                    JSONObject account = store.findPan115Account(store.state(), selectedPan115AccountId);
                    String parentId = item.optBoolean("isDir") ? pan115CurrentCid : item.optString("cid", "0");
                    JSONObject result = new Pan115OpenClient().deleteFiles(account, item.optString("fid"), parentId);
                    store.updatePan115Tokens(selectedPan115AccountId, result.optString("accessToken"), result.optString("refreshToken"));
                    return true;
                }, ignored -> {
                    showNotice("115 文件已删除", false);
                    showPan115Browse();
                }))
                .setNegativeButton("取消", null)
                .show();
    }

    private void showSyncJobs() {
        activeTab = "sync";
        title.setText("同步");
        content.removeAllViews();
        Button add = primaryButton("新增 115 同步");
        add.setOnClickListener(v -> showCreateSyncFrom115Dialog("", pan115CurrentCid, pan115CurrentPath));
        content.addView(add, matchWrap());

        JSONArray jobs = store.state().optJSONArray("syncJobs");
        if (jobs == null || jobs.length() == 0) {
            content.addView(cardText("暂无同步作业", "可以在 115 浏览页选择目录创建同步"));
        } else {
            for (int i = jobs.length() - 1; i >= 0; i--) {
                JSONObject job = jobs.optJSONObject(i);
                if (job != null) {
                    content.addView(syncJobCard(job));
                }
            }
        }
        content.addView(label("最近日志", 16, TEXT, true));
        JSONArray logs = store.state().optJSONArray("logs");
        for (int i = logs == null ? -1 : logs.length() - 1; i >= 0 && i >= (logs.length() - 20); i--) {
            JSONObject log = logs.optJSONObject(i);
            if (log != null) {
                content.addView(cardText(log.optString("type"), new java.text.SimpleDateFormat("HH:mm:ss", Locale.CHINA).format(new java.util.Date(log.optLong("time"))) + "  " + log.optString("message")));
            }
        }
    }

    private View syncJobCard(JSONObject job) {
        LinearLayout card = card();
        card.addView(label(job.optString("name"), 15, TEXT, true));
        card.addView(label("115: " + job.optString("sourcePath", "/") + " -> " + job.optString("targetDir"), 12, MUTED, false));
        card.addView(label(job.optInt("intervalMinutes") > 0 ? "每 " + job.optInt("intervalMinutes") + " 分钟执行" : "未启用定时", 12, MUTED, false));
        String err = job.optString("lastError");
        if (!err.isEmpty()) {
            card.addView(label(err, 12, RED, false));
        }
        LinearLayout actions = row();
        Button run = primaryButton("立即扫描");
        run.setOnClickListener(v -> runSyncJob(job));
        Button delete = smallButton("删除");
        delete.setTextColor(RED);
        delete.setOnClickListener(v -> {
            try {
                store.deleteSyncJob(job.optString("id"));
                showSyncJobs();
            } catch (Exception error) {
                showNotice(error.getMessage(), true);
            }
        });
        actions.addView(run);
        actions.addView(delete);
        card.addView(actions);
        return card;
    }

    private void showTransfers() {
        activeTab = "transfers";
        title.setText("传输");
        content.removeAllViews();

        LinearLayout actions = row();
        Button start = primaryButton("启动");
        start.setOnClickListener(v -> startTransferService());
        Button local = smallButton("本地文件");
        local.setOnClickListener(v -> openFilePicker());
        Button pan115 = smallButton("115");
        pan115.setOnClickListener(v -> showPan115TaskDialog());
        actions.addView(start);
        actions.addView(local);
        actions.addView(pan115);
        content.addView(actions);

        JSONArray tasks = store.state().optJSONArray("tasks");
        if (tasks == null || tasks.length() == 0) {
            content.addView(cardText("暂无任务", "可以添加本地文件或 115 Open 任务"));
            return;
        }
        for (int i = tasks.length() - 1; i >= 0; i--) {
            JSONObject task = tasks.optJSONObject(i);
            if (task != null) {
                content.addView(taskCard(task));
            }
        }
    }

    private void showPools() {
        activeTab = "pools";
        title.setText("容量池");
        content.removeAllViews();
        LinearLayout create = card();
        create.addView(label("新增容量池", 16, TEXT, true));
        EditText name = input("例如：追更池");
        Button add = primaryButton("新增");
        add.setOnClickListener(v -> {
            try {
                store.addPool(name.getText().toString());
                showNotice("容量池已创建", false);
                showPools();
            } catch (Exception error) {
                showNotice(error.getMessage(), true);
            }
        });
        create.addView(name, matchWrap());
        create.addView(add, matchWrap());
        content.addView(create);

        JSONObject state = store.state();
        JSONArray pools = state.optJSONArray("capacityPools");
        JSONArray profiles = state.optJSONArray("profiles");
        for (int i = 0; pools != null && i < pools.length(); i++) {
            JSONObject pool = pools.optJSONObject(i);
            if (pool != null) {
                content.addView(poolCard(pool, profiles));
            }
        }
    }

    private void showTenants() {
        activeTab = "tenants";
        title.setText("租户连接");
        content.removeAllViews();

        Selection pools = poolSelection();
        LinearLayout create = card();
        create.addView(label("新增租户连接", 16, TEXT, true));
        EditText name = input("名称，例如 世纪互联租户");
        EditText tenantId = input("Tenant ID");
        EditText clientId = input("Client ID");
        EditText clientSecret = input("Client Secret");
        EditText refreshToken = input("Refresh Token，可留空");
        EditText rootPath = input("默认 Root Path");
        EditText docsOnly = input("仅导入文档库 true/false");
        docsOnly.setText("true");
        create.addView(name);
        create.addView(tenantId);
        create.addView(clientId);
        create.addView(clientSecret);
        create.addView(refreshToken);
        create.addView(rootPath);
        create.addView(docsOnly);
        create.addView(label("目标容量池", 13, TEXT, true));
        create.addView(pools.spinner);
        Button add = primaryButton("保存连接");
        add.setOnClickListener(v -> {
            try {
                store.addTenantConnection(
                        name.getText().toString(),
                        "client_credentials",
                        "cn",
                        tenantId.getText().toString(),
                        clientId.getText().toString(),
                        clientSecret.getText().toString(),
                        refreshToken.getText().toString(),
                        rootPath.getText().toString(),
                        !"false".equalsIgnoreCase(docsOnly.getText().toString().trim())
                );
                showNotice("租户连接已保存", false);
                showTenants();
            } catch (Exception error) {
                showNotice(error.getMessage(), true);
            }
        });
        create.addView(add, matchWrap());
        content.addView(create);

        JSONArray connections = store.state().optJSONArray("tenantConnections");
        if (connections == null || connections.length() == 0) {
            content.addView(cardText("暂无租户连接", "先添加连接，再执行发现或按站点挂载"));
            return;
        }
        for (int i = 0; i < connections.length(); i++) {
            JSONObject connection = connections.optJSONObject(i);
            if (connection != null) {
                content.addView(tenantConnectionCard(connection, pools.selectedId()));
            }
        }

        LinearLayout mount = card();
        mount.addView(label("按站点 URL 挂载 SP", 16, TEXT, true));
        Selection connectionSelection = tenantSelection();
        EditText siteUrl = input("站点 URL，例如 https://tenant.sharepoint.cn/sites/media");
        EditText libraryName = input("文档库名称，可留空自动匹配");
        EditText mountRoot = input("Root Path");
        EditText mountDocsOnly = input("仅导入文档库 true/false");
        mountDocsOnly.setText("true");
        mount.addView(label("租户连接", 13, TEXT, true));
        mount.addView(connectionSelection.spinner);
        mount.addView(siteUrl);
        mount.addView(libraryName);
        mount.addView(mountRoot);
        mount.addView(mountDocsOnly);
        Button mountBtn = primaryButton("挂载并导入");
        mountBtn.setOnClickListener(v -> runBackground(() -> {
            JSONObject state = store.state();
            JSONObject connection = store.findTenantConnection(state, connectionSelection.selectedId());
            if (connection == null) {
                throw new IllegalStateException("未找到租户连接");
            }
            GraphUploader uploader = new GraphUploader();
            JSONArray drives = uploader.mountSharePointSite(connection, siteUrl.getText().toString(), libraryName.getText().toString(), !"false".equalsIgnoreCase(mountDocsOnly.getText().toString().trim()));
            int added = importTenantDrives(connection, drives, pools.selectedId(), mountRoot.getText().toString().trim());
            return added;
        }, result -> {
            showNotice("站点挂载完成，新导入 " + result + " 个 SP", false);
            showSettings();
        }));
        mount.addView(mountBtn, matchWrap());
        content.addView(mount);
    }

    private View tenantConnectionCard(JSONObject connection, String poolId) {
        LinearLayout card = card();
        card.addView(label(connection.optString("name"), 15, TEXT, true));
        card.addView(label(connection.optString("tenantId"), 12, MUTED, false));
        card.addView(label("Root " + emptyAsRoot(connection.optString("defaultRootPath")) + " · 文档库 " + (connection.optBoolean("importDocumentsOnly", true) ? "仅导入" : "全部"), 12, MUTED, false));
        LinearLayout actions = row();
        Button discover = smallButton("发现并导入");
        discover.setOnClickListener(v -> runBackground(() -> {
            JSONObject state = store.state();
            JSONObject current = store.findTenantConnection(state, connection.optString("id"));
            if (current == null) {
                throw new IllegalStateException("未找到租户连接");
            }
            GraphUploader uploader = new GraphUploader();
            JSONArray drives = uploader.discoverSharePointDrives(current, "*", current.optBoolean("importDocumentsOnly", true));
            return importTenantDrives(current, drives, poolId, current.optString("defaultRootPath", ""));
        }, result -> {
            showNotice("发现并导入完成，新导入 " + result + " 个 SP", false);
            showTenants();
        }));
        Button remove = smallButton("删除");
        remove.setTextColor(RED);
        remove.setOnClickListener(v -> {
            try {
                store.removeTenantConnection(connection.optString("id"));
                showNotice("租户连接已删除", false);
                showTenants();
            } catch (Exception error) {
                showNotice(error.getMessage(), true);
            }
        });
        actions.addView(discover);
        actions.addView(remove);
        card.addView(actions);
        return card;
    }

    private int importTenantDrives(JSONObject connection, JSONArray drives, String poolId, String rootPath) throws Exception {
        int added = 0;
        JSONObject state = store.state();
        for (int i = 0; drives != null && i < drives.length(); i++) {
            JSONObject drive = drives.optJSONObject(i);
            if (drive == null) {
                continue;
            }
            String driveId = drive.optString("driveId");
            if (driveId.isEmpty()) {
                continue;
            }
            if (store.findSharePointProfileByDriveId(state, driveId) != null) {
                continue;
            }
            String profileName = drive.optString("siteName");
            String driveName = drive.optString("driveName");
            if (!driveName.isEmpty()) {
                profileName = profileName.isEmpty() ? driveName : profileName + " / " + driveName;
            }
            JSONObject profile = store.addSharePointProfile(
                    profileName,
                    connection.optString("tenantId"),
                    connection.optString("clientId"),
                    connection.optString("clientSecret"),
                    driveId,
                    rootPath == null || rootPath.trim().isEmpty() ? connection.optString("defaultRootPath", "") : rootPath,
                    poolId
            );
            store.updateProfileQuota(profile.optString("id"), drive.optLong("quotaTotal"), drive.optLong("quotaUsed"), drive.optLong("quotaRemaining"));
            added++;
            state = store.state();
        }
        return added;
    }

    private Selection tenantSelection() {
        JSONObject state = store.state();
        JSONArray connections = state.optJSONArray("tenantConnections");
        ArrayList<String> ids = new ArrayList<>();
        ArrayList<String> labels = new ArrayList<>();
        for (int i = 0; connections != null && i < connections.length(); i++) {
            JSONObject connection = connections.optJSONObject(i);
            if (connection != null) {
                ids.add(connection.optString("id"));
                labels.add(connection.optString("name"));
            }
        }
        if (ids.isEmpty()) {
            ids.add("");
            labels.add("暂无租户连接");
        }
        return new Selection(spinner(labels), ids);
    }

    private void showFingerprints() {
        activeTab = "fingerprints";
        title.setText("指纹");
        content.removeAllViews();
        JSONArray fingerprints = store.state().optJSONArray("fingerprints");
        java.util.HashSet<String> profileIds = new java.util.HashSet<>();
        long totalBytes = 0L;
        long latest = 0L;
        for (int i = 0; fingerprints != null && i < fingerprints.length(); i++) {
            JSONObject fp = fingerprints.optJSONObject(i);
            if (fp == null) {
                continue;
            }
            String profileId = fp.optString("profileId");
            if (!profileId.isEmpty()) {
                profileIds.add(profileId);
            }
            totalBytes += Math.max(0L, fp.optLong("size"));
            latest = Math.max(latest, fp.optLong("scannedAt"));
        }

        LinearLayout summary = row();
        summary.addView(metric("指纹总数", String.valueOf(safeLength(fingerprints))));
        summary.addView(metric("覆盖 SP", profileIds.size() + " 个"));
        content.addView(summary);
        LinearLayout summary2 = row();
        summary2.addView(metric("文件大小", formatBytes(totalBytes)));
        summary2.addView(metric("最近扫描", latest <= 0L ? "未扫描" : formatDateTime(latest)));
        content.addView(summary2);

        LinearLayout actions = row();
        Button scanAll = primaryButton("扫描全部 SP");
        scanAll.setOnClickListener(v -> scanAllSharePoints());
        Button dedupe = smallButton("查看重复");
        dedupe.setOnClickListener(v -> showDedupe());
        Button clear = smallButton("清空指纹");
        clear.setTextColor(RED);
        clear.setOnClickListener(v -> {
            try {
                store.clearFingerprints();
                showNotice("指纹已清空", false);
                showFingerprints();
            } catch (Exception error) {
                showNotice(error.getMessage(), true);
            }
        });
        actions.addView(scanAll);
        actions.addView(dedupe);
        actions.addView(clear);
        content.addView(actions);

        if (fingerprints == null || fingerprints.length() == 0) {
            content.addView(cardText("暂无指纹", "点击扫描全部 SP 后会在这里显示已扫描文件。"));
            return;
        }

        int shown = 0;
        int limit = 300;
        for (int i = fingerprints.length() - 1; i >= 0 && shown < limit; i--) {
            JSONObject fp = fingerprints.optJSONObject(i);
            if (fp == null) {
                continue;
            }
            JSONObject profile = profileById(fp.optString("profileId"));
            String profileName = profile == null ? fp.optString("profileId") : profile.optString("name");
            String path = fp.optString("path");
            LinearLayout card = card();
            card.addView(label(fp.optString("name", "未命名文件"), 15, TEXT, true));
            card.addView(label(profileName + " · " + (path == null || path.trim().isEmpty() ? "/" : path), 12, MUTED, false));
            card.addView(label(formatBytes(fp.optLong("size")) + " · " + formatDateTime(fp.optLong("scannedAt")), 12, MUTED, false));
            content.addView(card);
            shown++;
        }
        if (fingerprints.length() > limit) {
            content.addView(cardText("仅显示最近 " + limit + " 条", "当前共有 " + fingerprints.length() + " 条指纹，去重仍会使用全部指纹。"));
        }
    }

    private void showDedupe() {
        activeTab = "dedupe";
        title.setText("去重");
        content.removeAllViews();
        JSONArray fingerprints = store.state().optJSONArray("fingerprints");
        java.util.LinkedHashMap<String, java.util.ArrayList<JSONObject>> groups = new java.util.LinkedHashMap<>();
        for (int i = 0; fingerprints != null && i < fingerprints.length(); i++) {
            JSONObject fp = fingerprints.optJSONObject(i);
            if (fp == null) {
                continue;
            }
            String key = fp.optString("name").trim().toLowerCase(Locale.ROOT) + "|" + fp.optLong("size");
            groups.computeIfAbsent(key, k -> new java.util.ArrayList<>()).add(fp);
        }
        int duplicateGroups = 0;
        int duplicateFiles = 0;
        for (java.util.ArrayList<JSONObject> group : groups.values()) {
            if (group.size() > 1) {
                duplicateGroups++;
                duplicateFiles += group.size();
            }
        }
        LinearLayout summary = row();
        summary.addView(metric("指纹总数", String.valueOf(safeLength(fingerprints))));
        summary.addView(metric("重复组", String.valueOf(duplicateGroups)));
        content.addView(summary);
        LinearLayout summary2 = row();
        summary2.addView(metric("重复文件", String.valueOf(duplicateFiles)));
        summary2.addView(metric("去重指纹", String.valueOf(groups.size())));
        content.addView(summary2);

        LinearLayout actions = row();
        Button clear = smallButton("清空指纹");
        clear.setTextColor(RED);
        clear.setOnClickListener(v -> {
            try {
                store.clearFingerprints();
                showNotice("指纹已清空", false);
                showDedupe();
            } catch (Exception error) {
                showNotice(error.getMessage(), true);
            }
        });
        Button refresh = primaryButton("查看全部");
        refresh.setOnClickListener(v -> showFingerprints());
        actions.addView(clear);
        actions.addView(refresh);
        content.addView(actions);

        boolean hasDuplicate = false;
        for (java.util.ArrayList<JSONObject> group : groups.values()) {
            if (group.size() <= 1) {
                continue;
            }
            hasDuplicate = true;
            LinearLayout card = card();
            JSONObject first = group.get(0);
            card.addView(label(first.optString("name", "重复文件"), 15, TEXT, true));
            card.addView(label("同组 " + group.size() + " 个 · 大小 " + formatBytes(first.optLong("size")), 12, MUTED, false));
            for (JSONObject fp : group) {
                JSONObject profile = profileById(fp.optString("profileId"));
                String profileName = profile == null ? fp.optString("profileId") : profile.optString("name");
                card.addView(label(profileName + " · " + fp.optString("path"), 12, MUTED, false));
            }
            content.addView(card);
        }
        if (!hasDuplicate) {
            content.addView(cardText("暂无重复", "当前指纹中没有找到重复文件"));
        }
    }

    private void showLogs() {
        activeTab = "logs";
        title.setText("日志");
        content.removeAllViews();
        LinearLayout actions = row();
        Button clear = smallButton("清空日志");
        clear.setTextColor(RED);
        clear.setOnClickListener(v -> {
            try {
                store.clearLogs();
                showNotice("日志已清空", false);
                showLogs();
            } catch (Exception error) {
                showNotice(error.getMessage(), true);
            }
        });
        Button back = primaryButton("返回设置");
        back.setOnClickListener(v -> showSettings());
        actions.addView(clear);
        actions.addView(back);
        content.addView(actions);
        JSONArray logs = store.state().optJSONArray("logs");
        if (logs == null || logs.length() == 0) {
            content.addView(cardText("暂无日志", "当前没有日志记录"));
            return;
        }
        for (int i = logs.length() - 1; i >= 0; i--) {
            JSONObject log = logs.optJSONObject(i);
            if (log != null) {
                String time = new java.text.SimpleDateFormat("HH:mm:ss", Locale.CHINA).format(new java.util.Date(log.optLong("time")));
                content.addView(cardText(log.optString("type"), time + "  " + log.optString("message")));
            }
        }
    }

    private void showSettings() {
        activeTab = "settings";
        title.setText("设置");
        content.removeAllViews();

        content.addView(cardText("运行模式", "当前 Android App 完全使用手机本地配置和前台服务，不需要填写电脑服务器地址。"));

        LinearLayout actions = row();
        Button addSp = primaryButton("添加 SP");
        addSp.setOnClickListener(v -> showSharePointDialog());
        Button add115 = smallButton("添加 115");
        add115.setOnClickListener(v -> showPan115AccountDialog());
        Button pools = smallButton("容量池");
        pools.setOnClickListener(v -> showPools());
        Button tenants = smallButton("租户");
        tenants.setOnClickListener(v -> showTenants());
        Button transferSettings = smallButton("传输控制");
        transferSettings.setOnClickListener(v -> showTransferSettingsDialog());
        Button fingerprints = smallButton("指纹");
        fingerprints.setOnClickListener(v -> showFingerprints());
        Button dedupe = smallButton("去重");
        dedupe.setOnClickListener(v -> showDedupe());
        Button logs = smallButton("日志");
        logs.setOnClickListener(v -> showLogs());
        actions.addView(addSp);
        actions.addView(add115);
        actions.addView(pools);
        actions.addView(tenants);
        content.addView(actions);

        LinearLayout toolActions = row();
        toolActions.addView(transferSettings);
        toolActions.addView(fingerprints);
        toolActions.addView(dedupe);
        toolActions.addView(logs);
        content.addView(toolActions);

        JSONObject state = store.state();
        JSONArray profiles = state.optJSONArray("profiles");
        content.addView(label("SP 配置", 16, TEXT, true));
        if (profiles == null || profiles.length() == 0) {
            content.addView(cardText("未添加 SP", "需要 Tenant ID、Client ID、Client Secret 和 Drive ID"));
        } else {
            for (int i = 0; i < profiles.length(); i++) {
                JSONObject profile = profiles.optJSONObject(i);
                if (profile != null) {
                    content.addView(profileCard(profile));
                }
            }
        }

        JSONArray accounts = state.optJSONArray("pan115Accounts");
        content.addView(label("115 Open 账号", 16, TEXT, true));
        if (accounts == null || accounts.length() == 0) {
            content.addView(cardText("未添加 115 账号", "手机端直传优先使用 Open accessToken / refreshToken"));
        } else {
            for (int i = 0; i < accounts.length(); i++) {
                JSONObject account = accounts.optJSONObject(i);
                if (account != null) {
                    content.addView(accountCard(account));
                }
            }
        }
    }

    private View taskCard(JSONObject task) {
        LinearLayout card = card();
        card.addView(label(task.optString("name", "未命名任务"), 15, TEXT, true));
        String phase = task.optString("phase");
        String phaseText = phase == null || phase.trim().isEmpty() ? statusLabel(task.optString("status")) : phase;
        card.addView(label(sourceLabel(task.optString("sourceType")) + " · " + phaseText + " · " + task.optString("targetDir"), 12, MUTED, false));
        long size = task.optLong("size");
        long uploaded = task.optLong("uploaded");
        int percent = size > 0 ? (int) Math.min(100, uploaded * 100L / size) : 0;
        ProgressBar progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        progress.setProgress(percent);
        card.addView(progress, matchWrap());
        card.addView(label(percent + "% · " + formatBytes(uploaded) + " / " + formatBytes(size) + " · " + formatSpeed(task.optLong("speed")), 12, BLUE, false));
        String error = task.optString("lastError");
        if (!error.isEmpty()) {
            card.addView(label(error, 12, RED, false));
        }
        LinearLayout actions = row();
        Button retry = smallButton("重试");
        retry.setEnabled("failed".equals(task.optString("status")));
        retry.setOnClickListener(v -> {
            try {
                store.retryTask(task.optString("id"));
                ensureTransferServiceRunning();
                showTransfers();
            } catch (Exception error1) {
                showNotice(error1.getMessage(), true);
            }
        });
        Button delete = smallButton("删除");
        delete.setTextColor(RED);
        delete.setOnClickListener(v -> {
            try {
                store.deleteTask(task.optString("id"));
                showTransfers();
            } catch (Exception error1) {
                showNotice(error1.getMessage(), true);
            }
        });
        actions.addView(retry);
        actions.addView(delete);
        card.addView(actions);
        return card;
    }

    private View poolCard(JSONObject pool, JSONArray profiles) {
        int assigned = 0;
        int enabled = 0;
        long used = 0L;
        long total = 0L;
        for (int i = 0; profiles != null && i < profiles.length(); i++) {
            JSONObject profile = profiles.optJSONObject(i);
            if (profile != null && pool.optString("id").equals(profile.optString("capacityPoolId", "default"))) {
                assigned++;
                if (profile.optBoolean("capacityEnabled", true)) {
                    enabled++;
                    used += profile.optLong("quotaUsed");
                    total += profile.optLong("quotaTotal");
                }
            }
        }
        LinearLayout card = card();
        card.addView(label(pool.optString("name"), 16, TEXT, true));
        card.addView(label("关联 SP " + assigned + " 个 · 启用 " + enabled + " 个", 13, MUTED, false));
        card.addView(label("已用 " + formatBytes(used) + " · 剩余 " + formatBytes(Math.max(0L, total - used)) + " · 总量 " + formatBytes(total), 13, MUTED, false));
        LinearLayout actions = row();
        Button rename = smallButton("重命名");
        rename.setOnClickListener(v -> showRenamePoolDialog(pool));
        actions.addView(rename);
        if (!"default".equals(pool.optString("id"))) {
            Button delete = smallButton("删除空容量池");
            delete.setTextColor(RED);
            delete.setOnClickListener(v -> {
                try {
                    store.removePool(pool.optString("id"));
                    showPools();
                } catch (Exception error) {
                    showNotice(error.getMessage(), true);
                }
            });
            actions.addView(delete);
        }
        card.addView(actions);
        return card;
    }

    private View profileCard(JSONObject profile) {
        LinearLayout card = card();
        boolean enabled = profile.optBoolean("capacityEnabled", true);
        card.addView(label(profile.optString("name"), 15, TEXT, true));
        card.addView(label((enabled ? "已启用自动容量池" : "未启用自动容量池") + " · 容量池 " + poolName(profile.optString("capacityPoolId", "default")), 12, enabled ? GREEN : MUTED, false));
        card.addView(label("Drive ID " + (profile.optString("driveId").trim().isEmpty() ? "未配置" : shorten(profile.optString("driveId"))), 12, profile.optString("driveId").trim().isEmpty() ? RED : MUTED, false));
        card.addView(label("Root " + emptyAsRoot(profile.optString("rootPath")) + " · 已用 " + formatBytes(profile.optLong("quotaUsed")) + " · 剩余 " + formatBytes(profile.optLong("quotaRemaining")), 12, MUTED, false));
        LinearLayout actions = row();
        Button files = smallButton("文件");
        files.setOnClickListener(v -> {
            selectedSpProfileId = profile.optString("id");
            spCurrentPath = "";
            showSpFiles();
        });
        Button scan = smallButton("扫描");
        scan.setOnClickListener(v -> scanSharePoint(profile.optString("id")));
        Button move = smallButton("容量池");
        move.setOnClickListener(v -> showMoveProfilePoolDialog(profile));
        Button toggle = smallButton(enabled ? "停用" : "启用");
        toggle.setOnClickListener(v -> {
            try {
                boolean nextEnabled = !profile.optBoolean("capacityEnabled", true);
                store.toggleSharePointProfileEnabled(profile.optString("id"), nextEnabled);
                showNotice(nextEnabled ? "SP 已加入自动容量池" : "SP 已从自动容量池停用", false);
                showSettings();
            } catch (Exception error) {
                showNotice(error.getMessage(), true);
            }
        });
        Button delete = smallButton("删除 SP");
        delete.setTextColor(RED);
        delete.setOnClickListener(v -> {
            try {
                store.removeSharePointProfile(profile.optString("id"));
                showSettings();
            } catch (Exception error) {
                showNotice(error.getMessage(), true);
            }
        });
        actions.addView(files);
        actions.addView(scan);
        actions.addView(move);
        actions.addView(toggle);
        actions.addView(delete);
        card.addView(actions);
        Button deleteWide = smallButton("删除此 SP");
        deleteWide.setTextColor(RED);
        deleteWide.setOnClickListener(v -> {
            try {
                store.removeSharePointProfile(profile.optString("id"));
                showNotice("SP 已删除", false);
                showSettings();
            } catch (Exception error) {
                showNotice(error.getMessage(), true);
            }
        });
        card.addView(deleteWide, matchWrap());
        return card;
    }

    private View accountCard(JSONObject account) {
        LinearLayout card = card();
        card.addView(label(account.optString("name"), 15, TEXT, true));
        String tokenState = account.optString("accessToken").isEmpty()
                ? (account.optString("cookie").isEmpty() ? "未配置 Open Token" : "已保存 Cookie，任务执行时可自动获取 Open Token")
                : "Open Token 已配置";
        card.addView(label(tokenState, 12, MUTED, false));
        LinearLayout actions = row();
        Button browse = smallButton("浏览");
        browse.setOnClickListener(v -> {
            selectedPan115AccountId = account.optString("id");
            pan115CurrentCid = "0";
            pan115CurrentPath = "";
            pan115CidStack.clear();
            pan115PathStack.clear();
            showPan115Browse();
        });
        Button token = smallButton("获取 Token");
        token.setEnabled(!account.optString("cookie").isEmpty());
        token.setOnClickListener(v -> runBackground(() -> {
            if (account.optString("cookie").isEmpty()) {
                throw new IllegalStateException("该账号没有保存 Cookie");
            }
            Pan115OpenClient.CloudDriveToken result = new Pan115OpenClient().authorizeCloudDrive(account.optString("cookie"));
            store.updatePan115Tokens(account.optString("id"), result.accessToken, result.refreshToken);
            return true;
        }, ignored -> {
            showNotice("115 Open Token 已重新获取", false);
            showSettings();
        }));
        Button delete = smallButton("删除 115");
        delete.setTextColor(RED);
        delete.setOnClickListener(v -> {
            try {
                store.removePan115Account(account.optString("id"));
                showSettings();
            } catch (Exception error) {
                showNotice(error.getMessage(), true);
            }
        });
        actions.addView(browse);
        actions.addView(token);
        actions.addView(delete);
        card.addView(actions);
        return card;
    }

    private void showRenamePoolDialog(JSONObject pool) {
        EditText name = input("容量池名称");
        name.setText(pool.optString("name"));
        new AlertDialog.Builder(this)
                .setTitle("重命名容量池")
                .setView(name)
                .setPositiveButton("保存", (dialog, which) -> {
                    try {
                        store.renamePool(pool.optString("id"), name.getText().toString());
                        showNotice("容量池已重命名", false);
                        showPools();
                    } catch (Exception error) {
                        showNotice(error.getMessage(), true);
                    }
                })
                .setNegativeButton("取消", null)
                .show();
    }

    private void showMoveProfilePoolDialog(JSONObject profile) {
        Selection pools = poolSelection();
        pools.select(profile.optString("capacityPoolId", "default"));
        LinearLayout form = dialogForm();
        form.addView(label(profile.optString("name"), 13, TEXT, true));
        form.addView(label("目标容量池", 13, TEXT, true));
        form.addView(pools.spinner);
        new AlertDialog.Builder(this)
                .setTitle("切换 SP 容量池")
                .setView(form)
                .setPositiveButton("保存", (dialog, which) -> {
                    try {
                        store.moveSharePointProfilePool(profile.optString("id"), pools.selectedId());
                        showNotice("SP 容量池已更新", false);
                        showSettings();
                    } catch (Exception error) {
                        showNotice(error.getMessage(), true);
                    }
                })
                .setNegativeButton("取消", null)
                .show();
    }

    private void showLocalTaskDialog(Uri uri, String name, long size) {
        Selection pools = poolSelection();
        LinearLayout form = dialogForm();
        TextView file = label(name + " · " + formatBytes(size), 13, MUTED, false);
        EditText target = input("目标目录，留空为 SP 根目录");
        form.addView(file);
        form.addView(label("目标容量池", 13, TEXT, true));
        form.addView(pools.spinner);
        form.addView(target);
        new AlertDialog.Builder(this)
                .setTitle("新增本地上传任务")
                .setView(form)
                .setPositiveButton("添加", (dialog, which) -> {
                    try {
                        if (size < 0) {
                            showNotice("无法读取本地文件大小，暂不能添加该文件", true);
                            return;
                        }
                        store.addTask(name, "local-uri", uri.toString(), target.getText().toString(), pools.selectedId(), "", size);
                        ensureTransferServiceRunning();
                        showNotice("本地上传任务已添加", false);
                        showTransfers();
                    } catch (Exception error) {
                        showNotice(error.getMessage(), true);
                    }
                })
                .setNegativeButton("取消", null)
                .show();
    }

    private void showPan115TaskDialog() {
        Selection accounts = accountSelection();
        if (accounts.ids.isEmpty()) {
            showNotice("请先在设置里添加 115 Open 账号", true);
            return;
        }
        Selection pools = poolSelection();
        LinearLayout form = dialogForm();
        EditText pickCode = input("115 pickCode");
        EditText fileName = input("文件名，可留空使用 115 返回名称");
        EditText target = input("目标目录，留空为 SP 根目录");
        form.addView(label("115 账号", 13, TEXT, true));
        form.addView(accounts.spinner);
        form.addView(pickCode);
        form.addView(fileName);
        form.addView(label("目标容量池", 13, TEXT, true));
        form.addView(pools.spinner);
        form.addView(target);
        new AlertDialog.Builder(this)
                .setTitle("新增 115 Open 任务")
                .setView(form)
                .setPositiveButton("添加", (dialog, which) -> {
                    try {
                        String name = fileName.getText().toString().trim();
                        if (name.isEmpty()) {
                            name = pickCode.getText().toString().trim();
                        }
                        store.addTask(name, "pan115-open", pickCode.getText().toString(), target.getText().toString(), pools.selectedId(), accounts.selectedId(), 0L);
                        ensureTransferServiceRunning();
                        showNotice("115 任务已添加", false);
                        showTransfers();
                    } catch (Exception error) {
                        showNotice(error.getMessage(), true);
                    }
                })
                .setNegativeButton("取消", null)
                .show();
    }

    private void showPan115TaskFromItemDialog(JSONObject item) {
        Selection accounts = accountSelection();
        Selection pools = poolSelection();
        LinearLayout form = dialogForm();
        EditText target = input("目标目录，留空为 SP 根目录");
        form.addView(label(item.optString("name") + " · " + formatBytes(item.optLong("size")), 13, MUTED, false));
        form.addView(label("115 账号", 13, TEXT, true));
        form.addView(accounts.spinner);
        form.addView(label("目标容量池", 13, TEXT, true));
        form.addView(pools.spinner);
        form.addView(target);
        new AlertDialog.Builder(this)
                .setTitle("加入传输队列")
                .setView(form)
                .setPositiveButton("添加", (dialog, which) -> {
                    try {
                        store.addTaskWithMeta(
                                item.optString("name"),
                                "pan115-open",
                                item.optString("pickCode"),
                                target.getText().toString(),
                                pools.selectedId(),
                                accounts.selectedId(),
                                item.optLong("size"),
                                item.optString("sha1"),
                                item.optString("name")
                        );
                        ensureTransferServiceRunning();
                        showNotice("任务已添加", false);
                        showTransfers();
                    } catch (Exception error) {
                        showNotice(error.getMessage(), true);
                    }
                })
                .setNegativeButton("取消", null)
                .show();
    }

    private void showImportPan115FolderDialog(JSONObject item) {
        Selection pools = poolSelection();
        LinearLayout form = dialogForm();
        String folderPath = joinPath(pan115CurrentPath, item.optString("name"));
        EditText target = input("目标目录，留空为 SP 根目录");
        target.setText(folderPath);
        form.addView(label("115 文件夹: " + (folderPath.isEmpty() ? "/" : folderPath), 13, MUTED, false));
        form.addView(label("目标容量池", 13, TEXT, true));
        form.addView(pools.spinner);
        form.addView(target);
        new AlertDialog.Builder(this)
                .setTitle("导入文件夹任务")
                .setView(form)
                .setPositiveButton("导入", (dialog, which) -> runBackground(() -> {
                    JSONObject state = store.state();
                    JSONObject account = store.findPan115Account(state, selectedPan115AccountId);
                    if (account == null) {
                        throw new IllegalStateException("没有找到 115 账号");
                    }
                    Pan115OpenClient.JSONArrayResult files = new Pan115OpenClient().listFilesRecursive(account, item.optString("cid"));
                    store.updatePan115Tokens(selectedPan115AccountId, files.accessToken, files.refreshToken);
                    return store.addTasksFromPan115Files(
                            files.items,
                            target.getText().toString(),
                            pools.selectedId(),
                            selectedPan115AccountId
                    );
                }, result -> {
                    if (((Integer) result) > 0) {
                        ensureTransferServiceRunning();
                    }
                    showNotice("已导入 " + result + " 个传输任务", false);
                    showTransfers();
                }))
                .setNegativeButton("取消", null)
                .show();
    }

    private void showCreateSpFolderDialog(String profileId, String currentPath) {
        EditText name = input("文件夹名称");
        new AlertDialog.Builder(this)
                .setTitle("新建 SP 文件夹")
                .setView(name)
                .setPositiveButton("新建", (dialog, which) -> runBackground(() -> {
                    JSONObject profile = profileById(profileId);
                    new GraphUploader().createFolder(profile, currentPath, name.getText().toString());
                    return true;
                }, ignored -> {
                    showNotice("SP 文件夹已创建", false);
                    showSpFiles();
                }))
                .setNegativeButton("取消", null)
                .show();
    }

    private void showCreate115FolderDialog(String accountId, String cid) {
        EditText name = input("文件夹名称");
        new AlertDialog.Builder(this)
                .setTitle("新建 115 文件夹")
                .setView(name)
                .setPositiveButton("新建", (dialog, which) -> runBackground(() -> {
                    JSONObject account = store.findPan115Account(store.state(), accountId);
                    JSONObject result = new Pan115OpenClient().createFolder(account, cid, name.getText().toString());
                    store.updatePan115Tokens(accountId, result.optString("accessToken"), result.optString("refreshToken"));
                    return true;
                }, ignored -> {
                    showNotice("115 文件夹已创建", false);
                    showPan115Browse();
                }))
                .setNegativeButton("取消", null)
                .show();
    }

    private void showCreateSyncFrom115Dialog(String accountId, String cid, String sourcePath) {
        Selection accounts = accountSelection();
        Selection pools = poolSelection();
        if (!accountId.isEmpty()) {
            accounts.select(accountId);
        }
        LinearLayout form = dialogForm();
        EditText name = input("同步名称");
        name.setText(sourcePath == null || sourcePath.isEmpty() ? "115 根目录" : sourcePath);
        EditText target = input("目标目录");
        EditText interval = input("定时间隔分钟，0 表示手动");
        interval.setInputType(InputType.TYPE_CLASS_NUMBER);
        form.addView(name);
        form.addView(label("115 账号", 13, TEXT, true));
        form.addView(accounts.spinner);
        form.addView(label("目标容量池", 13, TEXT, true));
        form.addView(pools.spinner);
        form.addView(target);
        form.addView(interval);
        new AlertDialog.Builder(this)
                .setTitle("新增同步作业")
                .setView(form)
                .setPositiveButton("保存", (dialog, which) -> {
                    try {
                        int minutes = parseInt(interval.getText().toString(), 0);
                        store.addSyncJob(
                                name.getText().toString(),
                                accounts.selectedId(),
                                cid == null || cid.isEmpty() ? "0" : cid,
                                sourcePath == null ? "" : sourcePath,
                                pools.selectedId(),
                                target.getText().toString(),
                                minutes
                        );
                        ensureTransferServiceRunning();
                        showNotice("同步作业已创建", false);
                        showSyncJobs();
                    } catch (Exception error) {
                        showNotice(error.getMessage(), true);
                    }
                })
                .setNegativeButton("取消", null)
                .show();
    }

    private void runSyncJob(JSONObject job) {
        runBackground(() -> {
            JSONObject state = store.state();
            JSONObject account = store.findPan115Account(state, job.optString("pan115AccountId"));
            if (account == null) {
                throw new IllegalStateException("没有找到 115 账号");
            }
            Pan115OpenClient.JSONArrayResult files = new Pan115OpenClient().listFilesRecursive(account, job.optString("sourceCid", "0"));
            store.updatePan115Tokens(account.optString("id"), files.accessToken, files.refreshToken);
            int added = store.addTasksFromPan115Files(files.items, job.optString("targetDir"), job.optString("targetPoolId", "default"), account.optString("id"));
            store.markSyncJobRun(job.optString("id"), added, "");
            return added;
        }, result -> {
            if (((Integer) result) > 0) {
                ensureTransferServiceRunning();
            }
            showNotice("同步扫描完成，新增 " + result + " 个任务", false);
            showSyncJobs();
        });
    }

    private void scanSharePoint(String profileId) {
        runBackground(() -> {
            JSONObject profile = profileById(profileId);
            if (profile == null) {
                throw new IllegalStateException("SP 配置不存在");
            }
            org.json.JSONArray files = new GraphUploader().scanTree(profile, "");
            store.rebuildFingerprints(profileId, files);
            JSONObject drive = new GraphUploader().driveInfo(profile);
            JSONObject quota = drive.optJSONObject("quota");
            if (quota != null) {
                store.updateProfileQuota(profileId, quota.optLong("total"), quota.optLong("used"), quota.optLong("remaining"));
            }
            return files.length();
        }, result -> {
            showNotice("SP 扫描完成，文件数 " + result, false);
            showSpFiles();
        });
    }

    private void scanAllSharePoints() {
        showNotice("正在扫描全部已启用 SP，请保持应用在前台...", false);
        runBackground(() -> {
            JSONObject state = store.state();
            JSONArray profiles = state.optJSONArray("profiles");
            GraphUploader graph = new GraphUploader();
            int scannedProfiles = 0;
            int totalFiles = 0;
            for (int i = 0; profiles != null && i < profiles.length(); i++) {
                JSONObject profile = profiles.optJSONObject(i);
                if (profile == null || !profile.optBoolean("capacityEnabled", true)) {
                    continue;
                }
                if (profile.optString("driveId").trim().isEmpty()) {
                    continue;
                }
                JSONArray files = graph.scanTree(profile, "");
                store.rebuildFingerprints(profile.optString("id"), files);
                JSONObject drive = graph.driveInfo(profile);
                JSONObject quota = drive.optJSONObject("quota");
                if (quota != null) {
                    store.updateProfileQuota(profile.optString("id"), quota.optLong("total"), quota.optLong("used"), quota.optLong("remaining"));
                }
                scannedProfiles++;
                totalFiles += files.length();
            }
            if (scannedProfiles == 0) {
                throw new IllegalStateException("没有可扫描的已启用 SP");
            }
            JSONObject result = new JSONObject();
            result.put("profiles", scannedProfiles);
            result.put("files", totalFiles);
            return result;
        }, result -> {
            JSONObject summary = (JSONObject) result;
            showNotice("扫描完成：SP " + summary.optInt("profiles") + " 个，文件 " + summary.optInt("files") + " 个", false);
            showFingerprints();
        });
    }

    private void showSharePointDialog() {
        Selection pools = poolSelection();
        LinearLayout form = dialogForm();
        EditText name = input("名称，例如 od1");
        EditText tenantId = input("Tenant ID");
        EditText clientId = input("Client ID");
        EditText clientSecret = input("Client Secret");
        EditText siteUrl = input("站点链接，Drive ID 留空时自动获取");
        EditText libraryName = input("文档库名称，留空默认文档");
        EditText driveId = input("Drive ID，可留空自动获取");
        EditText rootPath = input("Root Path，可留空");
        clientSecret.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        form.addView(name);
        form.addView(tenantId);
        form.addView(clientId);
        form.addView(clientSecret);
        form.addView(siteUrl);
        form.addView(libraryName);
        form.addView(driveId);
        form.addView(rootPath);
        form.addView(label("容量池", 13, TEXT, true));
        form.addView(pools.spinner);
        new AlertDialog.Builder(this)
                .setTitle("添加 SharePoint")
                .setView(form)
                .setPositiveButton("保存", (dialog, which) -> {
                    try {
                        String manualDriveId = driveId.getText().toString().trim();
                        if (manualDriveId.isEmpty()) {
                            autoAddSharePoint(name, tenantId, clientId, clientSecret, siteUrl, libraryName, rootPath, pools);
                            return;
                        }
                        store.addSharePointProfile(
                                name.getText().toString(),
                                tenantId.getText().toString(),
                                clientId.getText().toString(),
                                clientSecret.getText().toString(),
                                manualDriveId,
                                rootPath.getText().toString(),
                                pools.selectedId()
                        );
                        showNotice("SP 已保存", false);
                        showSettings();
                    } catch (Exception error) {
                        showNotice(error.getMessage(), true);
                    }
                })
                .setNegativeButton("取消", null)
                .show();
    }

    private void autoAddSharePoint(
            EditText name,
            EditText tenantId,
            EditText clientId,
            EditText clientSecret,
            EditText siteUrl,
            EditText libraryName,
            EditText rootPath,
            Selection pools
    ) {
        showNotice("正在自动获取 SP Drive ID...", false);
        runBackground(() -> {
            JSONObject connection = new JSONObject();
            connection.put("name", name.getText().toString());
            connection.put("tenantId", tenantId.getText().toString());
            connection.put("clientId", clientId.getText().toString());
            connection.put("clientSecret", clientSecret.getText().toString());
            connection.put("graphBaseUrl", "https://microsoftgraph.chinacloudapi.cn/v1.0");
            connection.put("authBaseUrl", "https://login.partner.microsoftonline.cn");

            JSONArray drives = new GraphUploader().mountSharePointSite(
                    connection,
                    siteUrl.getText().toString(),
                    libraryName.getText().toString(),
                    true
            );
            if (drives == null || drives.length() == 0) {
                throw new IllegalStateException("没有找到可用文档库");
            }
            JSONObject drive = drives.getJSONObject(0);
            String foundDriveId = drive.optString("driveId");
            if (foundDriveId.trim().isEmpty()) {
                throw new IllegalStateException("自动获取 Drive ID 失败");
            }
            if (store.findSharePointProfileByDriveId(store.state(), foundDriveId) != null) {
                throw new IllegalStateException("这个 SP Drive ID 已存在");
            }

            String profileName = name.getText().toString().trim();
            if (profileName.isEmpty()) {
                String siteName = drive.optString("siteName");
                String driveName = drive.optString("driveName");
                profileName = siteName.isEmpty() ? driveName : siteName + (driveName.isEmpty() ? "" : " / " + driveName);
            }
            JSONObject profile = store.addSharePointProfile(
                    profileName,
                    tenantId.getText().toString(),
                    clientId.getText().toString(),
                    clientSecret.getText().toString(),
                    foundDriveId,
                    rootPath.getText().toString(),
                    pools.selectedId()
            );
            store.updateProfileQuota(
                    profile.optString("id"),
                    drive.optLong("quotaTotal"),
                    drive.optLong("quotaUsed"),
                    drive.optLong("quotaRemaining")
            );
            return profile.optString("name");
        }, result -> {
            showNotice("SP 已自动添加: " + result, false);
            showSettings();
        });
    }

    private void showPan115AccountDialog() {
        LinearLayout form = dialogForm();
        EditText name = input("账号名称");
        EditText accessToken = input("Open accessToken");
        EditText refreshToken = input("Open refreshToken");
        EditText cookie = input("Cookie，用于自动获取 Open Token");
        form.addView(name);
        form.addView(cookie);
        form.addView(accessToken);
        form.addView(refreshToken);
        form.addView(label("只填 Cookie 也可以保存，App 会自动授权 CloudDrive 获取 Open Token；也可以手动填 Open Token。", 12, MUTED, false));
        new AlertDialog.Builder(this)
                .setTitle("添加 115 账号")
                .setView(form)
                .setPositiveButton("保存", (dialog, which) -> {
                    try {
                        String accountName = name.getText().toString();
                        String rawCookie = cookie.getText().toString();
                        String at = accessToken.getText().toString();
                        String rt = refreshToken.getText().toString();
                        if ((at.trim().isEmpty() || rt.trim().isEmpty()) && !rawCookie.trim().isEmpty()) {
                            showNotice("正在用 Cookie 自动获取 115 Open Token...", false);
                            new Thread(() -> {
                                try {
                                    Pan115OpenClient.CloudDriveToken token = new Pan115OpenClient().authorizeCloudDrive(rawCookie);
                                    runOnUiThread(() -> {
                                        try {
                                            store.addPan115Account(accountName, rawCookie, token.accessToken, token.refreshToken);
                                            showNotice("115 Open Token 已自动获取并保存", false);
                                            showSettings();
                                        } catch (Exception error) {
                                            showNotice(error.getMessage(), true);
                                        }
                                    });
                                } catch (Exception error) {
                                    runOnUiThread(() -> {
                                        try {
                                            store.addPan115Account(accountName, rawCookie, "", "");
                                            showNotice("115 自动授权失败，已先保存 Cookie，任务执行时会重试: " + error.getMessage(), true);
                                            showSettings();
                                        } catch (Exception saveError) {
                                            showNotice(saveError.getMessage(), true);
                                        }
                                    });
                                }
                            }, "pan115-auto-token").start();
                        } else {
                            store.addPan115Account(accountName, rawCookie, at, rt);
                            showNotice("115 账号已保存", false);
                            showSettings();
                        }
                    } catch (Exception error) {
                        showNotice(error.getMessage(), true);
                    }
                })
                .setNegativeButton("取消", null)
                .show();
    }

    private void showTransferSettingsDialog() {
        JSONObject settings = store.state().optJSONObject("settings");
        LinearLayout form = dialogForm();
        EditText concurrency = input("并发上传数 1-4");
        concurrency.setInputType(InputType.TYPE_CLASS_NUMBER);
        concurrency.setText(String.valueOf(settings == null ? 4 : settings.optInt("transferConcurrency", 4)));
        EditText dailyGb = input("每日上传限制 GB，0 表示不限");
        dailyGb.setInputType(InputType.TYPE_CLASS_NUMBER);
        long limit = settings == null ? 0L : settings.optLong("dailyUploadLimitBytes");
        dailyGb.setText(String.valueOf(limit <= 0 ? 0 : limit / 1024L / 1024L / 1024L));
        form.addView(concurrency);
        form.addView(dailyGb);
        new AlertDialog.Builder(this)
                .setTitle("传输控制")
                .setView(form)
                .setPositiveButton("保存", (dialog, which) -> {
                    try {
                        int c = parseInt(concurrency.getText().toString(), 4);
                        long gb = Math.max(0, parseInt(dailyGb.getText().toString(), 0));
                        store.updateSettings(gb * 1024L * 1024L * 1024L, c);
                        showNotice("传输设置已保存", false);
                        showSettings();
                    } catch (Exception error) {
                        showNotice(error.getMessage(), true);
                    }
                })
                .setNegativeButton("取消", null)
                .show();
    }

    private void openFilePicker() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        startActivityForResult(intent, REQUEST_PICK_FILE);
    }

    private void startTransferService() {
        ensureTransferServiceRunning();
        showNotice("传输服务已启动", false);
    }

    private void ensureTransferServiceRunning() {
        Intent intent = new Intent(this, TransferService.class);
        intent.setAction(TransferService.ACTION_START);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent);
        } else {
            startService(intent);
        }
    }

    private void autoStartTransferServiceIfNeeded() {
        if (!hasPendingTransferWork()) {
            return;
        }
        ensureTransferServiceRunning();
    }

    private boolean hasPendingTransferWork() {
        JSONArray tasks = store.state().optJSONArray("tasks");
        for (int i = 0; tasks != null && i < tasks.length(); i++) {
            JSONObject task = tasks.optJSONObject(i);
            if (task == null) {
                continue;
            }
            String status = task.optString("status");
            if ("queued".equals(status) || "running".equals(status)) {
                return true;
            }
        }
        return false;
    }

    private void stopTransferService() {
        Intent intent = new Intent(this, TransferService.class);
        intent.setAction(TransferService.ACTION_STOP);
        startService(intent);
        showNotice("传输服务已停止", false);
    }

    private Selection poolSelection() {
        JSONObject state = store.state();
        JSONArray pools = state.optJSONArray("capacityPools");
        ArrayList<String> ids = new ArrayList<>();
        ArrayList<String> labels = new ArrayList<>();
        for (int i = 0; pools != null && i < pools.length(); i++) {
            JSONObject pool = pools.optJSONObject(i);
            if (pool != null) {
                ids.add(pool.optString("id"));
                labels.add(pool.optString("name"));
            }
        }
        if (ids.isEmpty()) {
            ids.add("default");
            labels.add("默认容量池");
        }
        return new Selection(spinner(labels), ids);
    }

    private Selection profileSelection() {
        JSONObject state = store.state();
        JSONArray profiles = state.optJSONArray("profiles");
        ArrayList<String> ids = new ArrayList<>();
        ArrayList<String> labels = new ArrayList<>();
        for (int i = 0; profiles != null && i < profiles.length(); i++) {
            JSONObject profile = profiles.optJSONObject(i);
            if (profile != null) {
                ids.add(profile.optString("id"));
                labels.add(profile.optString("name"));
            }
        }
        return new Selection(spinner(labels), ids);
    }

    private Selection accountSelection() {
        JSONObject state = store.state();
        JSONArray accounts = state.optJSONArray("pan115Accounts");
        ArrayList<String> ids = new ArrayList<>();
        ArrayList<String> labels = new ArrayList<>();
        for (int i = 0; accounts != null && i < accounts.length(); i++) {
            JSONObject account = accounts.optJSONObject(i);
            if (account != null) {
                ids.add(account.optString("id"));
                labels.add(account.optString("name"));
            }
        }
        return new Selection(spinner(labels), ids);
    }

    private JSONObject profileById(String profileId) {
        JSONArray profiles = store.state().optJSONArray("profiles");
        for (int i = 0; profiles != null && i < profiles.length(); i++) {
            JSONObject profile = profiles.optJSONObject(i);
            if (profile != null && profileId.equals(profile.optString("id"))) {
                return profile;
            }
        }
        return null;
    }

    private String poolName(String poolId) {
        JSONArray pools = store.state().optJSONArray("capacityPools");
        for (int i = 0; pools != null && i < pools.length(); i++) {
            JSONObject pool = pools.optJSONObject(i);
            if (pool != null && pool.optString("id").equals(poolId)) {
                return pool.optString("name", "默认容量池");
            }
        }
        return "默认容量池";
    }

    private Spinner spinner(ArrayList<String> labels) {
        Spinner spinner = new Spinner(this);
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, labels);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinner.setAdapter(adapter);
        return spinner;
    }

    private void refreshActive() {
        if ("dashboard".equals(activeTab)) showDashboard();
        else if ("sp-files".equals(activeTab)) showSpFiles();
        else if ("pan115".equals(activeTab)) showPan115Browse();
        else if ("sync".equals(activeTab)) showSyncJobs();
        else if ("transfers".equals(activeTab)) showTransfers();
        else if ("pools".equals(activeTab)) showPools();
        else if ("tenants".equals(activeTab)) showTenants();
        else if ("fingerprints".equals(activeTab)) showFingerprints();
        else if ("dedupe".equals(activeTab)) showDedupe();
        else if ("logs".equals(activeTab)) showLogs();
        else showSettings();
    }

    private void runBackground(BackgroundTask task, ResultCallback callback) {
        new Thread(() -> {
            try {
                Object result = task.run();
                runOnUiThread(() -> callback.onResult(result));
            } catch (Exception error) {
                runOnUiThread(() -> showNotice(error.getMessage() == null ? String.valueOf(error) : error.getMessage(), true));
            }
        }, "sjhl-ui-task").start();
    }

    private void removeLoadingCards() {
        for (int i = content.getChildCount() - 1; i >= 0; i--) {
            View child = content.getChildAt(i);
            if (child instanceof LinearLayout) {
                LinearLayout layout = (LinearLayout) child;
                if (layout.getChildCount() > 0 && layout.getChildAt(0) instanceof TextView) {
                    String text = String.valueOf(((TextView) layout.getChildAt(0)).getText());
                    if ("加载中".equals(text)) {
                        content.removeViewAt(i);
                    }
                }
            }
        }
    }

    private LinearLayout row() {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(0, 0, 0, dp(8));
        return row;
    }

    private LinearLayout card() {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(12), dp(12), dp(12), dp(12));
        card.setBackgroundColor(Color.WHITE);
        LinearLayout.LayoutParams params = matchWrap();
        params.setMargins(0, 0, 0, dp(10));
        card.setLayoutParams(params);
        return card;
    }

    private LinearLayout dialogForm() {
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(dp(8), dp(4), dp(8), dp(4));
        return form;
    }

    private View metric(String name, String value) {
        LinearLayout card = card();
        card.setGravity(Gravity.CENTER);
        card.addView(label(name, 12, MUTED, false));
        card.addView(label(value, 18, TEXT, true));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -2, 1);
        params.setMargins(dp(4), 0, dp(4), 0);
        card.setLayoutParams(params);
        return card;
    }

    private View cardText(String name, String value) {
        LinearLayout card = card();
        card.addView(label(name, 14, TEXT, true));
        card.addView(label(value, 14, MUTED, false));
        return card;
    }

    private TextView label(String text, int sp, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(text == null ? "" : text);
        view.setTextSize(sp);
        view.setTextColor(color);
        view.setGravity(Gravity.CENTER_VERTICAL);
        view.setPadding(dp(2), dp(4), dp(2), dp(4));
        if (bold) {
            view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        }
        return view;
    }

    private EditText input(String hint) {
        EditText input = new EditText(this);
        input.setHint(hint);
        input.setSingleLine(true);
        input.setTextSize(15);
        input.setInputType(InputType.TYPE_CLASS_TEXT);
        return input;
    }

    private Button primaryButton(String text) {
        Button button = smallButton(text);
        button.setTextColor(Color.WHITE);
        button.setBackgroundColor(BLUE);
        return button;
    }

    private Button smallButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextSize(14);
        button.setAllCaps(false);
        return button;
    }

    private LinearLayout.LayoutParams matchWrap() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.setMargins(0, 0, 0, dp(10));
        return params;
    }

    private void showNotice(String message, boolean error) {
        if (message == null || message.isEmpty()) {
            notice.setVisibility(View.GONE);
            return;
        }
        notice.setText(message);
        notice.setTextColor(error ? RED : GREEN);
        notice.setVisibility(View.VISIBLE);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private int safeLength(JSONArray array) {
        return array == null ? 0 : array.length();
    }

    private String queryDisplayName(Uri uri) {
        try (Cursor cursor = getContentResolver().query(uri, null, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (index >= 0) {
                    return cursor.getString(index);
                }
            }
        } catch (Exception ignored) {
        }
        return uri.getLastPathSegment() == null ? "本地文件" : uri.getLastPathSegment();
    }

    private long querySize(Uri uri) {
        try (Cursor cursor = getContentResolver().query(uri, null, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int index = cursor.getColumnIndex(OpenableColumns.SIZE);
                if (index >= 0) {
                    return cursor.getLong(index);
                }
            }
        } catch (Exception ignored) {
        }
        return -1L;
    }

    private boolean isToday(long time) {
        if (time <= 0) {
            return false;
        }
        Calendar a = Calendar.getInstance();
        Calendar b = Calendar.getInstance();
        b.setTimeInMillis(time);
        return a.get(Calendar.YEAR) == b.get(Calendar.YEAR) && a.get(Calendar.DAY_OF_YEAR) == b.get(Calendar.DAY_OF_YEAR);
    }

    private String sourceLabel(String type) {
        if ("local-uri".equals(type)) return "本地文件";
        if ("pan115-open".equals(type)) return "115 Open";
        return type;
    }

    private String statusLabel(String status) {
        if ("queued".equals(status)) return "等待";
        if ("running".equals(status)) return "上传中";
        if ("failed".equals(status)) return "失败";
        if ("done".equals(status)) return "完成";
        return status;
    }

    private String formatSpeed(long bytesPerSecond) {
        return formatBytes(bytesPerSecond) + "/s";
    }

    private String formatDateTime(long time) {
        if (time <= 0L) {
            return "未知时间";
        }
        return new SimpleDateFormat("MM-dd HH:mm", Locale.CHINA).format(new Date(time));
    }

    private String formatBytes(long bytes) {
        if (bytes < 0) {
            return "未知";
        }
        if (bytes == 0) {
            return "0 B";
        }
        String[] units = {"B", "KB", "MB", "GB", "TB"};
        double value = bytes;
        int index = 0;
        while (value >= 1024 && index < units.length - 1) {
            value /= 1024;
            index++;
        }
        return String.format(Locale.CHINA, index >= 3 ? "%.2f %s" : "%.0f %s", value, units[index]);
    }

    private String shorten(String value) {
        if (value == null || value.length() <= 16) {
            return value == null ? "" : value;
        }
        return value.substring(0, 8) + "..." + value.substring(value.length() - 6);
    }

    private String emptyAsRoot(String value) {
        return value == null || value.trim().isEmpty() ? "/" : value;
    }

    private String parentPath(String path) {
        String clean = path == null ? "" : path.replace("\\", "/").trim();
        while (clean.endsWith("/")) {
            clean = clean.substring(0, clean.length() - 1);
        }
        int index = clean.lastIndexOf('/');
        return index <= 0 ? "" : clean.substring(0, index);
    }

    private String joinPath(String left, String right) {
        String a = left == null ? "" : left.replace("\\", "/").trim();
        String b = right == null ? "" : right.replace("\\", "/").trim();
        while (a.endsWith("/")) a = a.substring(0, a.length() - 1);
        while (b.startsWith("/")) b = b.substring(1);
        if (a.isEmpty()) return b;
        if (b.isEmpty()) return a;
        return a + "/" + b;
    }

    private int parseInt(String value, int fallback) {
        try {
            return Integer.parseInt(value == null ? "" : value.trim());
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 10);
        }
    }

    private interface BackgroundTask {
        Object run() throws Exception;
    }

    private interface ResultCallback {
        void onResult(Object result);
    }

    private static final class Selection {
        final Spinner spinner;
        final ArrayList<String> ids;

        Selection(Spinner spinner, ArrayList<String> ids) {
            this.spinner = spinner;
            this.ids = ids;
        }

        String selectedId() {
            if (ids.isEmpty()) {
                return "";
            }
            int index = Math.max(0, spinner.getSelectedItemPosition());
            if (index >= ids.size()) {
                index = 0;
            }
            return ids.get(index);
        }

        void select(String id) {
            for (int i = 0; i < ids.size(); i++) {
                if (ids.get(i).equals(id)) {
                    spinner.setSelection(i);
                    return;
                }
            }
        }
    }
}
