package com.sjhl.spmanager;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.Locale;

final class MobileDatabase extends SQLiteOpenHelper {
    private static final String DB_NAME = "sjhl_mobile.db";
    private static final int DB_VERSION = 1;
    private static final String[] COLLECTIONS = new String[]{
            "capacityPools",
            "profiles",
            "pan115Accounts",
            "tenantConnections",
            "tasks",
            "syncJobs",
            "fingerprints",
            "logs"
    };

    MobileDatabase(Context context) {
        super(context, DB_NAME, null, DB_VERSION);
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)");
        db.execSQL("CREATE TABLE IF NOT EXISTS objects (" +
                "type TEXT NOT NULL, " +
                "id TEXT NOT NULL, " +
                "json TEXT NOT NULL, " +
                "name_key TEXT DEFAULT '', " +
                "size INTEGER DEFAULT 0, " +
                "status TEXT DEFAULT '', " +
                "sort_key INTEGER DEFAULT 0, " +
                "updated_at INTEGER NOT NULL, " +
                "PRIMARY KEY(type, id))");
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_objects_type_sort ON objects(type, sort_key)");
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_objects_name_size ON objects(type, name_key, size)");
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_objects_status ON objects(type, status)");
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
    }

    synchronized JSONObject loadState() throws JSONException {
        SQLiteDatabase db = getReadableDatabase();
        JSONObject state = new JSONObject();
        for (String collection : COLLECTIONS) {
            state.put(collection, loadCollection(db, collection));
        }
        String settings = metadata("settings");
        state.put("settings", settings == null || settings.isEmpty() ? new JSONObject() : new JSONObject(settings));
        return state;
    }

    synchronized void saveState(JSONObject state) throws JSONException {
        SQLiteDatabase db = getWritableDatabase();
        db.beginTransaction();
        try {
            for (String collection : COLLECTIONS) {
                saveCollection(db, collection, state.optJSONArray(collection));
            }
            JSONObject settings = state.optJSONObject("settings");
            putMetadata(db, "settings", settings == null ? "{}" : settings.toString());
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }

    synchronized boolean hasAnyData() {
        SQLiteDatabase db = getReadableDatabase();
        try (Cursor cursor = db.rawQuery("SELECT 1 FROM objects LIMIT 1", null)) {
            if (cursor.moveToFirst()) {
                return true;
            }
        }
        String settings = metadata("settings");
        return settings != null && !settings.isEmpty();
    }

    synchronized boolean isMigrated() {
        return "1".equals(metadata("shared_prefs_migrated"));
    }

    synchronized void markMigrated() {
        SQLiteDatabase db = getWritableDatabase();
        putMetadata(db, "shared_prefs_migrated", "1");
    }

    synchronized boolean hasNameSize(String collection, String name, long size) {
        String key = normalizeName(name);
        if (key.isEmpty()) {
            return false;
        }
        SQLiteDatabase db = getReadableDatabase();
        try (Cursor cursor = db.rawQuery(
                "SELECT 1 FROM objects WHERE type = ? AND name_key = ? AND size = ? LIMIT 1",
                new String[]{collection, key, String.valueOf(Math.max(0L, size))}
        )) {
            return cursor.moveToFirst();
        }
    }

    private JSONArray loadCollection(SQLiteDatabase db, String collection) throws JSONException {
        JSONArray result = new JSONArray();
        try (Cursor cursor = db.rawQuery(
                "SELECT json FROM objects WHERE type = ? ORDER BY sort_key ASC, updated_at ASC",
                new String[]{collection}
        )) {
            while (cursor.moveToNext()) {
                result.put(new JSONObject(cursor.getString(0)));
            }
        }
        return result;
    }

    private void saveCollection(SQLiteDatabase db, String collection, JSONArray items) throws JSONException {
        db.delete("objects", "type = ?", new String[]{collection});
        long now = System.currentTimeMillis();
        for (int i = 0; items != null && i < items.length(); i++) {
            JSONObject item = items.optJSONObject(i);
            if (item == null) {
                continue;
            }
            String id = item.optString("id");
            if (id.isEmpty()) {
                id = java.util.UUID.randomUUID().toString();
                item.put("id", id);
            }
            ContentValues values = new ContentValues();
            values.put("type", collection);
            values.put("id", id);
            values.put("json", item.toString());
            values.put("name_key", normalizeName(item.optString("name")));
            values.put("size", item.optLong("size"));
            values.put("status", item.optString("status"));
            values.put("sort_key", sortKey(collection, item, now + i));
            values.put("updated_at", now);
            db.insertWithOnConflict("objects", null, values, SQLiteDatabase.CONFLICT_REPLACE);
        }
    }

    private long sortKey(String collection, JSONObject item, long fallback) {
        if ("logs".equals(collection)) {
            return item.optLong("time", fallback);
        }
        if ("fingerprints".equals(collection)) {
            return item.optLong("scannedAt", fallback);
        }
        return item.optLong("createdAt", item.optLong("updatedAt", fallback));
    }

    private String metadata(String key) {
        SQLiteDatabase db = getReadableDatabase();
        try (Cursor cursor = db.rawQuery("SELECT value FROM metadata WHERE key = ? LIMIT 1", new String[]{key})) {
            return cursor.moveToFirst() ? cursor.getString(0) : "";
        }
    }

    private void putMetadata(SQLiteDatabase db, String key, String value) {
        ContentValues values = new ContentValues();
        values.put("key", key);
        values.put("value", value == null ? "" : value);
        db.insertWithOnConflict("metadata", null, values, SQLiteDatabase.CONFLICT_REPLACE);
    }

    static String normalizeName(String value) {
        return value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
    }
}

