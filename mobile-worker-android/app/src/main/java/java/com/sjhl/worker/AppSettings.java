package com.sjhl.worker;

import android.content.Context;
import android.content.SharedPreferences;

class AppSettings {
    private static final String PREFS = "sjhl_worker";
    private static final String KEY_SERVER = "server_url";

    private final SharedPreferences prefs;

    AppSettings(Context ctx) {
        prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    String getServerUrl() {
        String url = prefs.getString(KEY_SERVER, "");
        if (!url.isEmpty() && !url.startsWith("http")) {
            url = "http://" + url;
        }
        if (!url.isEmpty() && url.endsWith("/")) {
            url = url.substring(0, url.length() - 1);
        }
        return url;
    }

    void setServerUrl(String url) {
        prefs.edit().putString(KEY_SERVER, url.trim()).apply();
    }

    boolean hasServer() {
        return !getServerUrl().isEmpty();
    }
}
