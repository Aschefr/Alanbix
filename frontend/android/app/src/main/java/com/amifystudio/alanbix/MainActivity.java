package com.amifystudio.alanbix;

import android.content.Intent;
import android.os.Bundle;

import com.amifystudio.alanbix.push.AlanbixPushPlugin;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    public static volatile boolean isForeground = false;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(AlanbixPushPlugin.class);
        super.onCreate(savedInstanceState);
        handleDeepLinkIntent(getIntent());
    }

    @Override
    public void onResume() {
        super.onResume();
        isForeground = true;
    }

    @Override
    public void onPause() {
        super.onPause();
        isForeground = false;
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleDeepLinkIntent(intent);
    }

    private void handleDeepLinkIntent(Intent intent) {
        if (intent == null) return;
        String link = intent.getStringExtra("link");
        if (link != null && !link.isEmpty()) {
            getSharedPreferences(AlanbixPushPlugin.PREFS_NAME, MODE_PRIVATE)
                    .edit()
                    .putString(AlanbixPushPlugin.KEY_PENDING_LINK, link)
                    .apply();

            // Si le bridge est déjà initialisé, dispatcher l'événement vers la WebView
            if (getBridge() != null && getBridge().getWebView() != null) {
                getBridge().getWebView().post(() -> {
                    String script = "window.dispatchEvent(new CustomEvent('alanbixDeepLink', { detail: { link: '" + link + "' } }));";
                    getBridge().getWebView().evaluateJavascript(script, null);
                });
            }
        }
    }
}
