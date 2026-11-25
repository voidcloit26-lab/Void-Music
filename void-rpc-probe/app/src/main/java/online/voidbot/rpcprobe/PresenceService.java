package online.voidbot.rpcprobe;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.os.*;
import android.media.MediaMetadata;
import android.media.browse.MediaBrowser;
import android.media.session.MediaController;
import android.media.session.PlaybackState;
import android.net.Uri;
import java.nio.charset.StandardCharsets;

public final class PresenceService extends Service {
    static { System.loadLibrary("void_rpc_probe"); }
    private native void initNative();
    private native void publishNative();
    private native void publishTrackNative(byte[] title, byte[] artist, byte[] artwork,
                                          long startSec, long endSec, int provider);
    private native void clearNative();
    private native String tickNative();


    public static final String START = "online.voidbot.rpcprobe.START";
    public static final String TEST = "online.voidbot.rpcprobe.TEST";
    public static final String STOP = "online.voidbot.rpcprobe.STOP";
    private static final String CHANNEL = "void-presence";
    private static volatile String summary = "Not sharing";
    public static String summary() { return summary; }
    private static final String[] PACKAGES = {"online.voidbot.music.fast", "online.voidbot.music", "online.voidbot.music.debug"};
    private static final String MUSIC_SERVICE = "com.mochyy.mochymusic.playback.MusicService";
    private final Handler handler = new Handler(Looper.getMainLooper());
    private MediaBrowser browser;
    private MediaController controller;
    private boolean running, initialized, published, shareArtwork, diagnostic;
    private int provider, generation, retries;
    private long lastSent, lastStart, lastEnd, lastPoll;
    private String lastKey = "", trackStatus = "", nativeStatus = "";
    private final MediaController.Callback mediaCallback = new MediaController.Callback() {
        @Override public void onSessionDestroyed() { stopSelf(); }
    };
    private final Runnable pump = new Runnable() {
        @Override public void run() {
            if (!running) return;
            try {
                nativeStatus = tickNative();
                long now = SystemClock.elapsedRealtime();
                if (!diagnostic && controller != null && now - lastPoll >= 1000) {
                    lastPoll = now; pollTrack();
                }
                summary = trackStatus + "\n" + nativeStatus;
                handler.postDelayed(this, 250);
            } catch (RuntimeException | LinkageError e) { stopSelf(); }
        }
    };
    @Override public void onCreate() {
        super.onCreate();
        getSystemService(NotificationManager.class).createNotificationChannel(
            new NotificationChannel(CHANNEL, "VOID music activity", NotificationManager.IMPORTANCE_LOW));
    }
    private Notification notification() {
        PendingIntent open = PendingIntent.getActivity(this, 1, new Intent(this, ProbeActivity.class), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent stop = PendingIntent.getService(this, 2, new Intent(this, PresenceService.class).setAction(STOP), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(this, CHANNEL).setSmallIcon(android.R.drawable.ic_media_play)
            .setContentTitle("VOID Presence").setContentText("Discord music activity sharing enabled")
            .setContentIntent(open).setOngoing(true).setOnlyAlertOnce(true)
            .addAction(new Notification.Action.Builder(android.R.drawable.ic_menu_close_clear_cancel, "Stop", stop).build()).build();
    }
    @Override public int onStartCommand(Intent i, int flags, int id) {
        String action = i == null ? null : i.getAction();
        if (!START.equals(action) && !TEST.equals(action)) { stopSelf(); return START_NOT_STICKY; }
        try {
            if (Build.VERSION.SDK_INT >= 34) startForeground(541, notification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
            else startForeground(541, notification());
            handler.removeCallbacks(pump);
            disconnect();
            if (!initialized) { initNative(); initialized = true; }
            running = true; diagnostic = TEST.equals(action);
            provider = Math.max(0, Math.min(3, i.getIntExtra("provider", 0)));
            shareArtwork = i.getBooleanExtra("artwork", false);
            if (diagnostic) { trackStatus = "Fixed diagnostic activity"; publishNative(); published = true; }
            else connect(PACKAGES[Math.max(0, Math.min(2, i.getIntExtra("version", 0)))]);
            handler.post(pump);
        } catch (RuntimeException | LinkageError e) { summary = "RPC initialization failed"; stopSelf(); }
        return START_NOT_STICKY;
    }
    private void connect(String pkg) {
        final int request = ++generation;
        trackStatus = "Connecting to " + pkg;
        browser = new MediaBrowser(this, new ComponentName(pkg, MUSIC_SERVICE), new MediaBrowser.ConnectionCallback() {
            @Override public void onConnected() {
                if (!running || request != generation || browser == null) return;
                try {
                    controller = new MediaController(PresenceService.this, browser.getSessionToken());
                    if (!pkg.equals(controller.getPackageName())) { stopSelf(); return; }
                    controller.registerCallback(mediaCallback, handler);
                    trackStatus = "Connected — waiting for music";
                } catch (RuntimeException e) { stopSelf(); }
            }
            @Override public void onConnectionFailed() { if (request == generation) stopSelf(); }
            @Override public void onConnectionSuspended() { if (request == generation) stopSelf(); }
        }, null);
        browser.connect();
    }
    private void clearPublished() {
        if (initialized && published) clearNative();
        published = false; lastKey = ""; lastStart = lastEnd = lastSent = 0; retries = 0;
    }
    private void disconnect() {
        ++generation;
        if (controller != null) { controller.unregisterCallback(mediaCallback); controller = null; }
        if (browser != null) { browser.disconnect(); browser = null; }
        clearPublished();
    }
    private void pollTrack() {
        MediaMetadata meta = controller.getMetadata();
        PlaybackState state = controller.getPlaybackState();
        if (meta == null || state == null || state.getState() != PlaybackState.STATE_PLAYING) {
            clearPublished(); trackStatus = "No playing track — activity cleared"; return;
        }
        String title = safeText(meta.getString(MediaMetadata.METADATA_KEY_TITLE), "Unknown track");
        String artist = safeText(meta.getString(MediaMetadata.METADATA_KEY_ARTIST), "Unknown artist");
        String art = shareArtwork ? publicArtwork(meta) : "";
        long duration = meta.getLong(MediaMetadata.METADATA_KEY_DURATION), position = state.getPosition();
        float speed = state.getPlaybackSpeed();
        long update = state.getLastPositionUpdateTime(), start = 0, end = 0;
        if (duration > 0 && duration <= 86400000L && position >= 0 && speed > 0.1f && speed <= 4f) {
            if (update > 0) position += (long)(Math.max(0, SystemClock.elapsedRealtime() - update) * speed);
            position = Math.max(0, Math.min(position, duration));
            long now = System.currentTimeMillis() / 1000;
            start = now - (long)(position / (speed * 1000)); end = start + (long)(duration / (speed * 1000));
            if (end <= now) { clearPublished(); trackStatus = "Waiting for next track"; return; }
        }
        String key = title + "|" + artist + "|" + art + "|" + provider;
        long elapsed = SystemClock.elapsedRealtime();
        boolean trackChanged = !key.equals(lastKey);
        boolean changed = trackChanged || Math.abs(start - lastStart) > 3 || Math.abs(end - lastEnd) > 3;
        boolean failed = nativeStatus.startsWith("SDK rejected") || (nativeStatus.startsWith("Waiting") && elapsed - lastSent >= 15000);
        if (trackChanged) retries = 0;
        boolean retry = failed && retries < 3 && elapsed - lastSent >= (15000L << retries);
        if (!published || (changed && elapsed - lastSent >= 5000) || retry) {
            if (retry) retries++;
            publishTrackNative(utf8(title), utf8(artist), utf8(art), start, end, provider);
            lastSent = elapsed; lastKey = key; lastStart = start; lastEnd = end; published = true;
        }
        trackStatus = "Current track: " + title + " — " + artist;
    }
    private static byte[] utf8(String s) { return s.getBytes(StandardCharsets.UTF_8); }
    private static String safeText(String raw, String fallback) {
        if (raw == null || raw.trim().isEmpty()) return fallback;
        String clean = raw.replaceAll("[\\p{Cc}]", " ").trim();
        StringBuilder result = new StringBuilder();
        int bytes = 0;
        for (int i = 0; i < clean.length();) {
            int cp = clean.codePointAt(i);
            String unit = new String(Character.toChars(cp));
            int n = utf8(unit).length;
            if (bytes + n > 120) break;
            result.append(unit); bytes += n; i += Character.charCount(cp);
        }
        return result.length() == 0 ? fallback : result.toString();
    }
    private static String publicArtwork(MediaMetadata m) {
        for (String key : new String[]{MediaMetadata.METADATA_KEY_ART_URI, MediaMetadata.METADATA_KEY_ALBUM_ART_URI, MediaMetadata.METADATA_KEY_DISPLAY_ICON_URI}) {
            String raw = m.getString(key);
            if (raw == null || raw.length() > 512) continue;
            Uri uri = Uri.parse(raw);
            String host = uri.getHost();
            if (!"https".equals(uri.getScheme()) || host == null || uri.getUserInfo() != null
                    || uri.getPort() != -1 || uri.getQuery() != null || uri.getFragment() != null) continue;
            if (host.equals("i.ytimg.com") || host.equals("lh3.googleusercontent.com")
                || host.equals("i.scdn.co") || host.matches("is[1-5]-ssl\\.mzstatic\\.com")) return raw;
        }
        return "";
    }


    @Override public IBinder onBind(Intent intent) { return null; }
    @Override public void onTaskRemoved(Intent root) { stopSelf(); super.onTaskRemoved(root); }
    @Override public void onDestroy() {
        running = false; handler.removeCallbacks(pump);
        try { disconnect(); if (initialized) tickNative(); } catch (RuntimeException | LinkageError ignored) {}
        stopForeground(STOP_FOREGROUND_REMOVE); summary = "Sharing stopped"; super.onDestroy();
    }
}
