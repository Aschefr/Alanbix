package com.amifystudio.alanbix.push;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.Log;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;

import com.amifystudio.alanbix.MainActivity;
import com.amifystudio.alanbix.R;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.net.URLEncoder;
import java.util.Calendar;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;

public class AlanbixPushService extends Service {

    private static final String TAG = "AlanbixPushService";

    public static final String ACTION_START = "com.amifystudio.alanbix.action.START";
    public static final String ACTION_STOP = "com.amifystudio.alanbix.action.STOP";
    public static final String ACTION_UPDATE_PREFS = "com.amifystudio.alanbix.action.UPDATE_PREFS";

    public static final String CHANNEL_FOREGROUND = "alanbix_fg_service";
    public static final String CHANNEL_MATCHES = "alanbix_matches";
    public static final String CHANNEL_MESSAGES = "alanbix_messages";
    public static final String CHANNEL_TEAMS = "alanbix_teams";
    public static final String CHANNEL_ANNOUNCEMENTS = "alanbix_announcements";
    public static final String CHANNEL_GENERAL = "alanbix_general";
    public static final String CHANNEL_TOURNAMENTS = "alanbix_tournaments";

    private static final int NOTIF_ID_FOREGROUND = 1001;
    private static final AtomicInteger notifIdSeq = new AtomicInteger(2000);

    public static volatile boolean isRunning = false;
    public static volatile boolean isConnected = false;

    private static final String KEY_LAST_EVENT_ISO = "last_event_iso";
    private final Set<String> seenEventIds = Collections.synchronizedSet(
            Collections.newSetFromMap(new LinkedHashMap<String, Boolean>(256, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(Map.Entry<String, Boolean> eldest) {
                    return size() > 200;
                }
            })
    );

    private OkHttpClient httpClient;
    private WebSocket webSocket;
    private Handler mainHandler;
    private Runnable reconnectRunnable;
    private int reconnectAttempts = 0;
    private ConnectivityManager connectivityManager;
    private ConnectivityManager.NetworkCallback networkCallback;

    @Override
    public void onCreate() {
        super.onCreate();
        isRunning = true;
        mainHandler = new Handler(Looper.getMainLooper());

        createNotificationChannels();
        startForeground(NOTIF_ID_FOREGROUND, buildForegroundNotification("Initialisation de la connexion..."));

        initHttpClient();
        registerNetworkCallback();
        Log.i(TAG, "AlanbixPushService initialisé.");
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent != null ? intent.getAction() : null;

        if (ACTION_STOP.equals(action)) {
            Log.i(TAG, "Arrêt du service d'arrière-plan demandé.");
            SharedPreferences.Editor editor = getSharedPreferences(AlanbixPushPlugin.PREFS_NAME, MODE_PRIVATE).edit();
            editor.putBoolean(AlanbixPushPlugin.KEY_BACKGROUND_ENABLED, false);
            editor.apply();
            disconnectWebSocket();
            stopForeground(true);
            stopSelf();
            return START_NOT_STICKY;
        }

        SharedPreferences sp = getSharedPreferences(AlanbixPushPlugin.PREFS_NAME, MODE_PRIVATE);
        boolean backgroundEnabled = sp.getBoolean(AlanbixPushPlugin.KEY_BACKGROUND_ENABLED, true);
        if (!backgroundEnabled) {
            Log.i(TAG, "Veille d'arrière-plan désactivée par l'utilisateur.");
            disconnectWebSocket();
            stopForeground(true);
            stopSelf();
            return START_NOT_STICKY;
        }

        // Toujours renouveler la notification au premier plan pour respecter les prérequis Android
        String lanName = sp.getString(AlanbixPushPlugin.KEY_LAN_NAME, "Alanbix LAN");
        String statusText = isConnected ? "Connecté à " + lanName : "Connexion en cours...";
        startForeground(NOTIF_ID_FOREGROUND, buildForegroundNotification(statusText));

        if (ACTION_UPDATE_PREFS.equals(action)) {
            Log.d(TAG, "Préférences de notification mises à jour.");
        } else {
            connectWebSocket();
        }

        return START_STICKY;
    }

    private void initHttpClient() {
        httpClient = new OkHttpClient.Builder()
                .pingInterval(20, TimeUnit.SECONDS)
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(0, TimeUnit.MILLISECONDS) // Indéfini pour WebSocket
                .retryOnConnectionFailure(true)
                .build();
    }

    private synchronized void connectWebSocket() {
        if (webSocket != null) {
            try {
                webSocket.close(1000, "Reconnexion");
            } catch (Exception ignored) {}
            webSocket = null;
        }

        SharedPreferences sp = getSharedPreferences(AlanbixPushPlugin.PREFS_NAME, MODE_PRIVATE);
        String serverUrl = sp.getString(AlanbixPushPlugin.KEY_SERVER_URL, "");
        String deviceToken = sp.getString(AlanbixPushPlugin.KEY_DEVICE_TOKEN, "");
        final String lanName = sp.getString(AlanbixPushPlugin.KEY_LAN_NAME, "Alanbix LAN");

        if (serverUrl.isEmpty() || deviceToken.isEmpty()) {
            Log.w(TAG, "URL de serveur ou jeton d'appareil manquant.");
            updateForegroundNotification("En attente de configuration...");
            return;
        }

        String wsUrl = buildWsUrl(serverUrl, deviceToken);
        Log.i(TAG, "Tentative de connexion WebSocket vers " + wsUrl);

        Request request = new Request.Builder()
                .url(wsUrl)
                .build();

        webSocket = httpClient.newWebSocket(request, new WebSocketListener() {
            @Override
            public void onOpen(WebSocket ws, Response response) {
                isConnected = true;
                reconnectAttempts = 0;
                Log.i(TAG, "WebSocket connecté avec succès !");
                updateForegroundNotification("Connecté à " + lanName);
                fetchMissedNotifications(serverUrl, deviceToken);
            }

            @Override
            public void onMessage(WebSocket ws, String text) {
                try {
                    JSONObject data = new JSONObject(text);
                    String type = data.optString("type");

                    if ("push".equals(type)) {
                        handlePushEvent(data);
                    } else if ("ping".equals(type)) {
                        JSONObject pong = new JSONObject();
                        pong.put("type", "pong");
                        pong.put("timestamp", data.optLong("timestamp", System.currentTimeMillis()));
                        ws.send(pong.toString());
                    }
                } catch (Exception e) {
                    Log.e(TAG, "Erreur lors du traitement du message: " + e.getMessage());
                }
            }

            @Override
            public void onClosed(WebSocket ws, int code, String reason) {
                isConnected = false;
                Log.w(TAG, "WebSocket fermé: " + code + " / " + reason);
                updateForegroundNotification("Reconnexion à " + lanName + "...");
                scheduleReconnect();
            }

            @Override
            public void onFailure(WebSocket ws, Throwable t, @Nullable Response response) {
                isConnected = false;
                Log.w(TAG, "Échec du WebSocket: " + t.getMessage());
                updateForegroundNotification("En attente de connexion à " + lanName + "...");
                scheduleReconnect();
            }
        });
    }

    private synchronized void disconnectWebSocket() {
        if (reconnectRunnable != null) {
            mainHandler.removeCallbacks(reconnectRunnable);
            reconnectRunnable = null;
        }
        if (webSocket != null) {
            try {
                webSocket.close(1000, "Service arrêté");
            } catch (Exception ignored) {}
            webSocket = null;
        }
        isConnected = false;
    }

    private void scheduleReconnect() {
        if (reconnectRunnable != null) {
            mainHandler.removeCallbacks(reconnectRunnable);
        }

        // Backoff exponentiel : 2s, 4s, 8s, 16s, max 30s
        long delay = Math.min(30000, 2000L * (1L << Math.min(reconnectAttempts++, 4)));
        Log.d(TAG, "Nouvelle tentative de reconnexion dans " + (delay / 1000) + "s (essai #" + reconnectAttempts + ")");

        reconnectRunnable = this::connectWebSocket;
        mainHandler.postDelayed(reconnectRunnable, delay);
    }

    private String buildWsUrl(String httpUrl, String token) {
        String base = httpUrl.trim();
        if (base.endsWith("/")) {
            base = base.substring(0, base.length() - 1);
        }
        if (base.startsWith("https://")) {
            base = "wss://" + base.substring(8);
        } else if (base.startsWith("http://")) {
            base = "ws://" + base.substring(7);
        } else if (!base.startsWith("ws://") && !base.startsWith("wss://")) {
            base = "ws://" + base;
        }
        return base + "/ws?client=push&token=" + token;
    }

    private void fetchMissedNotifications(String serverUrl, String deviceToken) {
        try {
            SharedPreferences sp = getSharedPreferences(AlanbixPushPlugin.PREFS_NAME, MODE_PRIVATE);
            String since = sp.getString(KEY_LAST_EVENT_ISO, "");
            String base = serverUrl.trim();
            if (base.endsWith("/")) {
                base = base.substring(0, base.length() - 1);
            }
            String url = base + "/notifications/missed";
            if (!since.isEmpty()) {
                url += "?since=" + URLEncoder.encode(since, "UTF-8");
            }
            Request req = new Request.Builder()
                    .url(url)
                    .addHeader("Authorization", "Bearer " + deviceToken)
                    .get()
                    .build();

            httpClient.newCall(req).enqueue(new Callback() {
                @Override
                public void onFailure(Call call, IOException e) {
                    Log.w(TAG, "Échec de récupération des notifications manquées: " + e.getMessage());
                }

                @Override
                public void onResponse(Call call, Response response) throws IOException {
                    try {
                        if (!response.isSuccessful() || response.body() == null) return;
                        String bodyStr = response.body().string();
                        JSONObject json = new JSONObject(bodyStr);
                        JSONArray events = json.optJSONArray("events");
                        if (events != null) {
                            for (int i = 0; i < events.length(); i++) {
                                JSONObject ev = events.optJSONObject(i);
                                if (ev != null) {
                                    handlePushEvent(ev);
                                }
                            }
                        }
                    } catch (Exception e) {
                        Log.w(TAG, "Erreur parsing /notifications/missed: " + e.getMessage());
                    } finally {
                        response.close();
                    }
                }
            });
        } catch (Exception e) {
            Log.w(TAG, "Erreur fetchMissedNotifications: " + e.getMessage());
        }
    }

    private void handlePushEvent(JSONObject push) {
        String eventId = push.optString("id", "");
        if (!eventId.isEmpty() && !seenEventIds.add(eventId)) {
            Log.d(TAG, "Notification ignorée : doublon (" + eventId + ")");
            return;
        }

        SharedPreferences sp = getSharedPreferences(AlanbixPushPlugin.PREFS_NAME, MODE_PRIVATE);
        String createdAt = push.optString("created_at", "");
        if (!createdAt.isEmpty()) {
            sp.edit().putString(KEY_LAST_EVENT_ISO, createdAt).apply();
        }

        JSONObject dataObj = push.optJSONObject("data");
        boolean isTest = dataObj != null && dataObj.optBoolean("is_test", false);

        // Si l'application est au premier plan, la WebView affiche déjà un toast en direct (sauf test explicite)
        if (MainActivity.isForeground && !isTest) {
            Log.d(TAG, "Application au premier plan : notification système ignorée (toast in-app actif).");
            return;
        }

        String category = push.optString("category", "general");
        String title = push.optString("title", "Alanbix");
        String body = push.optString("body", "");
        String link = push.optString("link", "/dashboard/notifications");

        // 1. Vérifier si les notifications sont globalement activées
        if (!sp.getBoolean("enabled", true)) {
            return;
        }

        // 2. Vérifier la plage "Ne pas déranger"
        if (isDndActive(sp)) {
            boolean bypassMatches = sp.getBoolean("dnd_bypass_matches", true);
            boolean bypassAdmin = sp.getBoolean("dnd_bypass_admin", true);

            boolean isMatch = "match_ready".equals(category) || "match_called".equals(category) || "score_dispute".equals(category);
            boolean isAdmin = "admin_message".equals(category) || "announcement".equals(category);

            if (isMatch && bypassMatches) {
                // Autorisé
            } else if (isAdmin && bypassAdmin) {
                // Autorisé
            } else {
                Log.d(TAG, "Notification ignorée : DND actif (" + category + ")");
                return;
            }
        }

        // 3. Vérifier les préférences par catégorie
        if (!isCategoryAllowed(category, sp)) {
            Log.d(TAG, "Notification ignorée : catégorie désactivée (" + category + ")");
            return;
        }

        // 4. Déterminer le canal et l'affichage
        String channelId = getChannelForCategory(category);
        displayNotification(channelId, title, body, link, sp);
    }

    private boolean isCategoryAllowed(String category, SharedPreferences sp) {
        switch (category) {
            case "match_ready":
            case "match_called":
            case "score_dispute":
                return sp.getBoolean("cat_match_ready", true);
            case "private_message":
                return sp.getBoolean("cat_private_message", true);
            case "team_message":
                return sp.getBoolean("cat_team_message", true);
            case "public_mention":
                String mentionPref = sp.getString("cat_public_mention", "mentions");
                return !"none".equals(mentionPref);
            case "ai_reply":
                return sp.getBoolean("cat_ai_reply", true);
            case "admin_message":
            case "announcement":
                return sp.getBoolean("cat_admin_message", true);
            case "tournaments":
            case "tournament_closed":
            case "tournament_started":
                return sp.getBoolean("cat_tournaments", true);
            default:
                return true;
        }
    }

    private boolean isDndActive(SharedPreferences sp) {
        if (!sp.getBoolean("dnd_enabled", false)) return false;

        String startStr = sp.getString("dnd_start", "02:00");
        String endStr = sp.getString("dnd_end", "09:00");

        try {
            String[] sParts = startStr.split(":");
            String[] eParts = endStr.split(":");
            int sMin = Integer.parseInt(sParts[0]) * 60 + Integer.parseInt(sParts[1]);
            int eMin = Integer.parseInt(eParts[0]) * 60 + Integer.parseInt(eParts[1]);

            Calendar now = Calendar.getInstance();
            int curMin = now.get(Calendar.HOUR_OF_DAY) * 60 + now.get(Calendar.MINUTE);

            if (sMin <= eMin) {
                return curMin >= sMin && curMin < eMin;
            } else {
                return curMin >= sMin || curMin < eMin;
            }
        } catch (Exception e) {
            return false;
        }
    }

    private String getChannelForCategory(String category) {
        switch (category) {
            case "match_ready":
            case "match_called":
            case "score_dispute":
                return CHANNEL_MATCHES;
            case "private_message":
                return CHANNEL_MESSAGES;
            case "team_message":
                return CHANNEL_TEAMS;
            case "admin_message":
            case "announcement":
                return CHANNEL_ANNOUNCEMENTS;
            case "tournaments":
            case "tournament_closed":
            case "tournament_started":
                return CHANNEL_TOURNAMENTS;
            default:
                return CHANNEL_GENERAL;
        }
    }

    private void displayNotification(String channelId, String title, String body, String link, SharedPreferences sp) {
        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;

        int notifId = notifIdSeq.incrementAndGet();

        // Enregistrer le lien dans SharedPreferences au cas où l'app se lance à froid
        sp.edit().putString(AlanbixPushPlugin.KEY_PENDING_LINK, link).apply();

        Intent intent = new Intent(this, MainActivity.class);
        intent.setAction(Intent.ACTION_VIEW);
        intent.putExtra("link", link);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);

        PendingIntent pi = PendingIntent.getActivity(
                this,
                notifId,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
        );

        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, channelId)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(new NotificationCompat.BigTextStyle().bigText(body))
                .setAutoCancel(true)
                .setContentIntent(pi)
                .setPriority(NotificationCompat.PRIORITY_HIGH);

        boolean soundEnabled = sp.getBoolean("sound", true);
        boolean vibEnabled = sp.getBoolean("vibration", true);
        boolean lockscreenPreview = sp.getBoolean("lockscreen_preview", true);

        builder.setVisibility(lockscreenPreview ? NotificationCompat.VISIBILITY_PUBLIC : NotificationCompat.VISIBILITY_PRIVATE);

        if (soundEnabled) {
            builder.setDefaults(NotificationCompat.DEFAULT_SOUND);
        }
        if (vibEnabled) {
            builder.setVibrate(new long[]{0, 150, 75, 150});
        }

        nm.notify(notifId, builder.build());
    }

    private Notification buildForegroundNotification(String statusText) {
        Intent intent = new Intent(this, MainActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent pi = PendingIntent.getActivity(
                this,
                0,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
        );

        Intent stopIntent = new Intent(this, AlanbixPushService.class);
        stopIntent.setAction(ACTION_STOP);
        PendingIntent stopPi = PendingIntent.getService(
                this,
                1,
                stopIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0)
        );

        return new NotificationCompat.Builder(this, CHANNEL_FOREGROUND)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle("🎮 Alanbix Companion")
                .setContentText(statusText)
                .setPriority(NotificationCompat.PRIORITY_MIN)
                .setOngoing(true)
                .setContentIntent(pi)
                .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Arrêter la veille", stopPi)
                .build();
    }

    private void updateForegroundNotification(String statusText) {
        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm != null) {
            nm.notify(NOTIF_ID_FOREGROUND, buildForegroundNotification(statusText));
        }
    }

    private void createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm == null) return;

            // 1. Canal permanent du service d'arrière-plan
            NotificationChannel fgChan = new NotificationChannel(
                    CHANNEL_FOREGROUND,
                    "Service d'arrière-plan Alanbix",
                    NotificationManager.IMPORTANCE_LOW
            );
            fgChan.setDescription("Maintient la connexion en direct avec le serveur LAN même écran éteint");
            fgChan.setShowBadge(false);
            nm.createNotificationChannel(fgChan);

            // 2. Canaux pour les événements
            createChannel(nm, CHANNEL_MATCHES, "Matchs & Duels", NotificationManager.IMPORTANCE_HIGH, true);
            createChannel(nm, CHANNEL_MESSAGES, "Messages Privés", NotificationManager.IMPORTANCE_HIGH, true);
            createChannel(nm, CHANNEL_TEAMS, "Messages d'Équipe", NotificationManager.IMPORTANCE_DEFAULT, true);
            createChannel(nm, CHANNEL_ANNOUNCEMENTS, "Annonces & Arbitrage", NotificationManager.IMPORTANCE_HIGH, true);
            createChannel(nm, CHANNEL_GENERAL, "Chat Général & Mentions", NotificationManager.IMPORTANCE_DEFAULT, false);
            createChannel(nm, CHANNEL_TOURNAMENTS, "Tournois", NotificationManager.IMPORTANCE_DEFAULT, false);
        }
    }

    private void createChannel(NotificationManager nm, String id, String name, int importance, boolean vibrate) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel chan = new NotificationChannel(id, name, importance);
            chan.enableVibration(vibrate);
            if (vibrate) {
                chan.setVibrationPattern(new long[]{0, 150, 75, 150});
            }
            nm.createNotificationChannel(chan);
        }
    }

    private void registerNetworkCallback() {
        try {
            connectivityManager = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
            if (connectivityManager != null) {
                NetworkRequest request = new NetworkRequest.Builder()
                        .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
                        .addTransportType(NetworkCapabilities.TRANSPORT_CELLULAR)
                        .addTransportType(NetworkCapabilities.TRANSPORT_ETHERNET)
                        .build();

                networkCallback = new ConnectivityManager.NetworkCallback() {
                    @Override
                    public void onAvailable(Network network) {
                        Log.i(TAG, "Réseau détecté, vérification de la connexion WebSocket...");
                        if (!isConnected) {
                            mainHandler.post(() -> connectWebSocket());
                        }
                    }
                };
                connectivityManager.registerNetworkCallback(request, networkCallback);
            }
        } catch (Exception e) {
            Log.w(TAG, "Impossible d'enregistrer le callback réseau: " + e.getMessage());
        }
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        isRunning = false;
        disconnectWebSocket();
        if (connectivityManager != null && networkCallback != null) {
            try {
                connectivityManager.unregisterNetworkCallback(networkCallback);
            } catch (Exception ignored) {}
        }
        Log.i(TAG, "AlanbixPushService détruit.");
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
