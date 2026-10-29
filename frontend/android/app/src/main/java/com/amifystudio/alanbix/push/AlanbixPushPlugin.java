package com.amifystudio.alanbix.push;

import android.Manifest;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import androidx.core.content.ContextCompat;

import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import org.json.JSONObject;

@CapacitorPlugin(
    name = "AlanbixPush",
    permissions = {
        @Permission(
            strings = { Manifest.permission.POST_NOTIFICATIONS },
            alias = "notifications"
        )
    }
)
public class AlanbixPushPlugin extends Plugin {

    public static final String PREFS_NAME = "alanbix_push_prefs";
    public static final String KEY_SERVER_URL = "server_url";
    public static final String KEY_DEVICE_TOKEN = "device_token";
    public static final String KEY_LAN_NAME = "lan_name";
    public static final String KEY_BACKGROUND_ENABLED = "background_enabled";
    public static final String KEY_PENDING_LINK = "pending_deep_link";

    @PluginMethod
    public void start(PluginCall call) {
        String serverUrl = call.getString("serverUrl");
        String deviceToken = call.getString("deviceToken");
        String lanName = call.getString("lanName", "Alanbix LAN");
        JSObject prefs = call.getObject("preferences");

        if (serverUrl == null || serverUrl.isEmpty() || deviceToken == null || deviceToken.isEmpty()) {
            call.reject("serverUrl et deviceToken sont obligatoires");
            return;
        }

        Context context = getContext();
        SharedPreferences.Editor editor = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).edit();
        editor.putString(KEY_SERVER_URL, serverUrl);
        editor.putString(KEY_DEVICE_TOKEN, deviceToken);
        editor.putString(KEY_LAN_NAME, lanName);
        editor.putBoolean(KEY_BACKGROUND_ENABLED, true);

        if (prefs != null) {
            savePreferencesToEditor(prefs, editor);
        }
        editor.apply();

        // Démarrage du service d'arrière-plan
        Intent intent = new Intent(context, AlanbixPushService.class);
        intent.setAction(AlanbixPushService.ACTION_START);
        try {
            ContextCompat.startForegroundService(context, intent);
            JSObject res = new JSObject();
            res.put("status", "started");
            call.resolve(res);
        } catch (Exception e) {
            call.reject("Impossible de démarrer le service d'arrière-plan: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void stop(PluginCall call) {
        Context context = getContext();
        SharedPreferences.Editor editor = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).edit();
        editor.putBoolean(KEY_BACKGROUND_ENABLED, false);
        editor.apply();

        Intent intent = new Intent(context, AlanbixPushService.class);
        intent.setAction(AlanbixPushService.ACTION_STOP);
        try {
            context.startService(intent);
        } catch (Exception ignored) {}

        JSObject res = new JSObject();
        res.put("status", "stopped");
        call.resolve(res);
    }

    @PluginMethod
    public void getStatus(PluginCall call) {
        Context context = getContext();
        SharedPreferences sp = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);

        boolean isRunning = AlanbixPushService.isRunning;
        boolean isConnected = AlanbixPushService.isConnected;
        String permState = getNotificationPermissionString();

        JSObject res = new JSObject();
        res.put("isRunning", isRunning);
        res.put("isConnected", isConnected);
        res.put("notificationPermission", permState);
        res.put("serverUrl", sp.getString(KEY_SERVER_URL, ""));
        res.put("deviceToken", sp.getString(KEY_DEVICE_TOKEN, ""));
        res.put("lanName", sp.getString(KEY_LAN_NAME, "Alanbix LAN"));
        res.put("backgroundEnabled", sp.getBoolean(KEY_BACKGROUND_ENABLED, false));
        call.resolve(res);
    }

    @PluginMethod
    public void requestNotificationPermission(PluginCall call) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            JSObject res = new JSObject();
            res.put("status", "granted");
            call.resolve(res);
            return;
        }
        if (getPermissionState("notifications") == PermissionState.GRANTED) {
            JSObject res = new JSObject();
            res.put("status", "granted");
            call.resolve(res);
            return;
        }
        requestPermissionForAlias("notifications", call, "notificationsPermCallback");
    }

    @PermissionCallback
    private void notificationsPermCallback(PluginCall call) {
        JSObject res = new JSObject();
        res.put("status", getNotificationPermissionString());
        call.resolve(res);
    }

    private String getNotificationPermissionString() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            return "granted";
        }
        PermissionState state = getPermissionState("notifications");
        if (state == PermissionState.GRANTED) return "granted";
        if (state == PermissionState.DENIED) return "denied";
        return "default";
    }

    @PluginMethod
    public void setPreferences(PluginCall call) {
        JSObject prefs = call.getObject("preferences");
        if (prefs != null) {
            Context context = getContext();
            SharedPreferences.Editor editor = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).edit();
            savePreferencesToEditor(prefs, editor);
            editor.apply();

            // Notifier le service pour qu'il prenne en compte les changements
            Intent intent = new Intent(context, AlanbixPushService.class);
            intent.setAction(AlanbixPushService.ACTION_UPDATE_PREFS);
            try {
                context.startService(intent);
            } catch (Exception ignored) {}
        }
        call.resolve();
    }

    @PluginMethod
    public void getPendingDeepLink(PluginCall call) {
        Context context = getContext();
        SharedPreferences sp = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        String link = sp.getString(KEY_PENDING_LINK, null);

        if (link != null) {
            sp.edit().remove(KEY_PENDING_LINK).apply();
        }

        JSObject res = new JSObject();
        res.put("link", link);
        call.resolve(res);
    }

    @PluginMethod
    public void openBatteryOptimizationSettings(PluginCall call) {
        Context context = getContext();
        try {
            Intent intent = new Intent();
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                intent.setAction(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS);
            } else {
                intent.setAction(Settings.ACTION_SETTINGS);
            }
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
            call.resolve();
        } catch (Exception e) {
            call.reject("Impossible d'ouvrir les réglages de batterie: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void openNotificationSettings(PluginCall call) {
        Context context = getContext();
        try {
            Intent intent = new Intent();
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                intent.setAction(Settings.ACTION_APP_NOTIFICATION_SETTINGS);
                intent.putExtra(Settings.EXTRA_APP_PACKAGE, context.getPackageName());
            } else {
                intent.setAction(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
                intent.setData(Uri.parse("package:" + context.getPackageName()));
            }
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
            call.resolve();
        } catch (Exception e) {
            call.reject("Impossible d'ouvrir les réglages de notifications: " + e.getMessage(), e);
        }
    }

    private void savePreferencesToEditor(JSObject prefs, SharedPreferences.Editor editor) {
        if (prefs.has("enabled")) editor.putBoolean("enabled", prefs.optBoolean("enabled", true));
        if (prefs.has("sound")) editor.putBoolean("sound", prefs.optBoolean("sound", true));
        if (prefs.has("vibration")) editor.putBoolean("vibration", prefs.optBoolean("vibration", true));
        if (prefs.has("lockscreen_preview")) editor.putBoolean("lockscreen_preview", prefs.optBoolean("lockscreen_preview", true));
        if (prefs.has("dnd_enabled")) editor.putBoolean("dnd_enabled", prefs.optBoolean("dnd_enabled", false));
        if (prefs.has("dnd_start")) editor.putString("dnd_start", prefs.optString("dnd_start", "02:00"));
        if (prefs.has("dnd_end")) editor.putString("dnd_end", prefs.optString("dnd_end", "09:00"));
        if (prefs.has("dnd_bypass_matches")) editor.putBoolean("dnd_bypass_matches", prefs.optBoolean("dnd_bypass_matches", true));
        if (prefs.has("dnd_bypass_admin")) editor.putBoolean("dnd_bypass_admin", prefs.optBoolean("dnd_bypass_admin", true));

        try {
            JSONObject cats = prefs.optJSONObject("categories");
            if (cats != null) {
                if (cats.has("match_ready")) editor.putBoolean("cat_match_ready", cats.optBoolean("match_ready", true));
                if (cats.has("private_message")) editor.putBoolean("cat_private_message", cats.optBoolean("private_message", true));
                if (cats.has("team_message")) editor.putBoolean("cat_team_message", cats.optBoolean("team_message", true));
                if (cats.has("public_mention")) editor.putString("cat_public_mention", cats.optString("public_mention", "mentions"));
                if (cats.has("ai_reply")) editor.putBoolean("cat_ai_reply", cats.optBoolean("ai_reply", true));
                if (cats.has("admin_message")) editor.putBoolean("cat_admin_message", cats.optBoolean("admin_message", true));
                if (cats.has("tournaments")) editor.putBoolean("cat_tournaments", cats.optBoolean("tournaments", true));
            }
        } catch (Exception ignored) {}
    }
}
