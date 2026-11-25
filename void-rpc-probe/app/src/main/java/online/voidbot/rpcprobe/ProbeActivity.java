package online.voidbot.rpcprobe;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.content.ComponentName;
import android.media.MediaMetadata;
import android.media.browse.MediaBrowser;
import android.media.session.MediaController;
import android.media.session.PlaybackState;
import android.net.Uri;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.LinearLayout;
import android.widget.Spinner;
import android.widget.TextView;
import com.discord.socialsdk.DiscordSocialSdkInit;
import java.nio.charset.StandardCharsets;

public final class ProbeActivity extends Activity {
    static { System.loadLibrary("void_rpc_probe"); }
    private native void initNative();
    private native void publishNative();
    private native void publishTrackNative(byte[] title, byte[] artist, byte[] artwork,
                                          long startSec, long endSec, int provider);
    private native void clearNative();
    private native String tickNative();

    private static final String[] PACKAGES = {
        "online.voidbot.music.fast", "online.voidbot.music", "online.voidbot.music.debug"
    };
    private static final String MUSIC_SERVICE = "com.mochyy.mochymusic.playback.MusicService";
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView status, musicStatus;
    private Spinner version, provider;
    private CheckBox shareArtwork;
    private MediaBrowser browser;
    private MediaController controller;
    private boolean syncEnabled, foreground, published;
    private long lastSent, lastStart, lastEnd;
    private String lastKey = "";
    private int connectionGeneration;

    private final MediaController.Callback mediaCallback = new MediaController.Callback() {
        @Override public void onSessionDestroyed() { stopSync(); musicStatus.setText("Music session ended"); }
    };

    private final Runnable pump = new Runnable() {
        @Override public void run() {
            if (!foreground) return;
            status.setText(tickNative());
            if (syncEnabled && controller != null) pollTrack();
            handler.postDelayed(this, 250);
        }
    };

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        DiscordSocialSdkInit.setEngineActivity(this);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(32, 48, 32, 32);
        TextView title = new TextView(this);
        title.setText("VOID Rich Presence — diagnostic");
        title.setTextSize(22);
        layout.addView(title);
        TextView note = new TextView(this);
        note.setText("Optional: share the current VOID Music title, artist and playback time with Discord. No account token or notification access. Keep this screen open during the test.");
        layout.addView(note);
        status = new TextView(this);
        musicStatus = new TextView(this);
        layout.addView(status);
        layout.addView(musicStatus);

        version = new Spinner(this);
        version.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item,
            new String[]{"VOID Music Fast", "VOID Music Release", "VOID Music Debug"}));
        layout.addView(version);
        provider = new Spinner(this);
        provider.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item,
            new String[]{"YouTube Music", "Spotify", "Apple Music", "TIDAL"}));
        layout.addView(provider);
        shareArtwork = new CheckBox(this);
        shareArtwork.setText("Share public album artwork URLs");
        shareArtwork.setChecked(false);
        layout.addView(shareArtwork);

        Button start = new Button(this);
        start.setText("Connect and share current song");
        start.setOnClickListener(v -> startSync());
        layout.addView(start);
        Button publish = new Button(this);
        publish.setText("Publish fixed test activity");
        publish.setOnClickListener(v -> { stopSync(); publishNative(); published = true; });
        layout.addView(publish);
        Button clear = new Button(this);
        clear.setText("Stop sharing and clear activity");
        clear.setOnClickListener(v -> { stopSync(); musicStatus.setText("Sharing stopped"); });
        layout.addView(clear);
        setContentView(layout);
        initNative();
        musicStatus.setText("Not sharing music");
    }

    private void startSync() {
        stopSync();
        syncEnabled = true;
        final int generation = ++connectionGeneration;
        final String pkg = PACKAGES[version.getSelectedItemPosition()];
        musicStatus.setText("Connecting to " + pkg);
        browser = new MediaBrowser(this, new ComponentName(pkg, MUSIC_SERVICE),
            new MediaBrowser.ConnectionCallback() {
                @Override public void onConnected() {
                    if (!syncEnabled || generation != connectionGeneration || browser == null) return;
                    try {
                        controller = new MediaController(ProbeActivity.this, browser.getSessionToken());
                        if (!pkg.equals(controller.getPackageName())) {
                            stopSync(); musicStatus.setText("Unexpected media session"); return;
                        }
                        controller.registerCallback(mediaCallback, handler);
                        musicStatus.setText("Connected — waiting for a playing song");
                        pollTrack();
                    } catch (RuntimeException e) { stopSync(); musicStatus.setText("Media session unavailable"); }
                }
                @Override public void onConnectionFailed() {
                    if (generation == connectionGeneration) {
                        stopSync(); musicStatus.setText("Connection failed. Open the matching VOID Music version first.");
                    }
                }
                @Override public void onConnectionSuspended() {
                    if (generation == connectionGeneration) {
                        stopSync(); musicStatus.setText("Music connection suspended");
                    }
                }
            }, null);
        try { browser.connect(); }
        catch (RuntimeException e) { stopSync(); musicStatus.setText("Unable to open music session"); }
    }

    private void stopSync() {
        syncEnabled = false;
        ++connectionGeneration;
        if (controller != null) {
            controller.unregisterCallback(mediaCallback);
            controller = null;
        }
        if (browser != null) {
            browser.disconnect();
            browser = null;
        }
        clearPublished();
    }

    private void clearPublished() {
        if (published) clearNative();
        published = false;
        lastKey = "";
        lastStart = lastEnd = lastSent = 0;
    }

    private void pollTrack() {
        try {
            MediaMetadata meta = controller.getMetadata();
            PlaybackState state = controller.getPlaybackState();
            if (meta == null || state == null || state.getState() != PlaybackState.STATE_PLAYING) {
                clearPublished(); musicStatus.setText("No playing track — activity cleared"); return;
            }
            String title = safeText(meta.getString(MediaMetadata.METADATA_KEY_TITLE), "Unknown track");
            String artist = safeText(meta.getString(MediaMetadata.METADATA_KEY_ARTIST), "Unknown artist");
            String art = shareArtwork.isChecked() ? publicArtwork(meta) : "";
            long duration = meta.getLong(MediaMetadata.METADATA_KEY_DURATION);
            long position = state.getPosition();
            float speed = state.getPlaybackSpeed();
            long update = state.getLastPositionUpdateTime();
            long start = 0, end = 0;
            if (duration > 0 && duration <= 86_400_000L && position >= 0 && speed > 0.1f && speed <= 4f) {
                if (update > 0) position += (long)(Math.max(0, SystemClock.elapsedRealtime() - update) * speed);
                position = Math.max(0, Math.min(position, duration));
                long now = System.currentTimeMillis() / 1000;
                start = now - (long)(position / (speed * 1000));
                end = start + (long)(duration / (speed * 1000));
                if (end <= now) { clearPublished(); return; }
            }
            int destination = provider.getSelectedItemPosition();
            String key = title + "\u0001" + artist + "\u0001" + art + "\u0001" + destination;
            long elapsed = SystemClock.elapsedRealtime();
            boolean changed = !key.equals(lastKey) || Math.abs(start - lastStart) > 3 || Math.abs(end - lastEnd) > 3;
            if (!published || (changed && elapsed - lastSent >= 5000)) {
                publishTrackNative(utf8(title), utf8(artist), utf8(art), start, end, destination);
                lastSent = elapsed; lastKey = key; lastStart = start; lastEnd = end; published = true;
            }
            musicStatus.setText("Sharing: " + title + " — " + artist);
        } catch (RuntimeException e) {
            stopSync(); musicStatus.setText("Music session error; sharing stopped");
        }
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

    @Override protected void onStart() {
        super.onStart(); foreground = true; handler.post(pump);
    }
    @Override protected void onStop() {
        foreground = false; stopSync(); tickNative(); handler.removeCallbacks(pump); super.onStop();
    }
}
