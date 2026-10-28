package com.amifystudio.alanbix.push;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.util.Log;

import androidx.core.content.ContextCompat;

public class BootReceiver extends BroadcastReceiver {

    private static final String TAG = "BootReceiver";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent != null ? intent.getAction() : null;
        if (Intent.ACTION_BOOT_COMPLETED.equals(action) || "android.intent.action.QUICKBOOT_POWERON".equals(action)) {
            Log.i(TAG, "Redémarrage du système détecté.");
            SharedPreferences sp = context.getSharedPreferences(AlanbixPushPlugin.PREFS_NAME, Context.MODE_PRIVATE);
            boolean backgroundEnabled = sp.getBoolean(AlanbixPushPlugin.KEY_BACKGROUND_ENABLED, false);
            String serverUrl = sp.getString(AlanbixPushPlugin.KEY_SERVER_URL, "");
            String deviceToken = sp.getString(AlanbixPushPlugin.KEY_DEVICE_TOKEN, "");

            if (backgroundEnabled && !serverUrl.isEmpty() && !deviceToken.isEmpty()) {
                Log.i(TAG, "Relance automatique du service AlanbixPushService après boot.");
                Intent serviceIntent = new Intent(context, AlanbixPushService.class);
                serviceIntent.setAction(AlanbixPushService.ACTION_START);
                try {
                    ContextCompat.startForegroundService(context, serviceIntent);
                } catch (Exception e) {
                    Log.e(TAG, "Échec de relance du service au boot: " + e.getMessage());
                }
            }
        }
    }
}
