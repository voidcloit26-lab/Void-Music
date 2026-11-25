package online.voidbot.rpcprobe;

import android.Manifest;
import android.app.Activity;
import android.app.NotificationManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.*;
import com.discord.socialsdk.DiscordSocialSdkInit;

public final class ProbeActivity extends Activity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView status;
    private Spinner version, provider;
    private CheckBox artwork;
    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            status.setText(PresenceService.summary());
            handler.postDelayed(this, 500);
        }
    };
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        DiscordSocialSdkInit.setEngineActivity(this);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(32, 48, 32, 32);
        ScrollView scroll = new ScrollView(this); scroll.addView(layout);
        TextView title = new TextView(this); title.setText("VOID Presence"); title.setTextSize(26); layout.addView(title);
        TextView note = new TextView(this);
        note.setText("Share your current song with the signed-in Discord app. Explicit Start enables background sharing with a Stop notification. No Discord password or token required.");
        layout.addView(note);
        status = new TextView(this); layout.addView(status);
        version = spinner(layout, new String[]{"VOID Music Fast", "VOID Music Release", "VOID Music Debug"});
        provider = spinner(layout, new String[]{"YouTube Music", "Spotify", "Apple Music", "TIDAL"});
        artwork = new CheckBox(this); artwork.setText("Share public album artwork URLs"); artwork.setChecked(false); layout.addView(artwork);
        Button start = new Button(this); start.setText("Start sharing music"); start.setOnClickListener(v -> start(false)); layout.addView(start);
        Button test = new Button(this); test.setText("Publish fixed test activity"); test.setOnClickListener(v -> start(true)); layout.addView(test);
        Button stop = new Button(this); stop.setText("Stop sharing and clear activity");
        stop.setOnClickListener(v -> stopService(new Intent(this, PresenceService.class))); layout.addView(stop);
        setContentView(scroll);
    }
    private Spinner spinner(LinearLayout parent, String[] items) {
        Spinner s = new Spinner(this);
        s.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, items));
        parent.addView(s); return s;
    }
    private void start(boolean diagnostic) {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 41);
            Toast.makeText(this, "Allow notifications, then press Start again.", Toast.LENGTH_LONG).show();
            return;
        }
        NotificationManager manager = getSystemService(NotificationManager.class);
        android.app.NotificationChannel channel = manager.getNotificationChannel("void-presence");
        if (!manager.areNotificationsEnabled() || (channel != null && channel.getImportance() == NotificationManager.IMPORTANCE_NONE)) {
            Toast.makeText(this, "Enable the sharing notification first.", Toast.LENGTH_LONG).show(); return;
        }
        Intent i = new Intent(this, PresenceService.class)
            .setAction(diagnostic ? PresenceService.TEST : PresenceService.START)
            .putExtra("version", version.getSelectedItemPosition())
            .putExtra("provider", provider.getSelectedItemPosition())
            .putExtra("artwork", artwork.isChecked());
        try { startForegroundService(i); }
        catch (RuntimeException e) { Toast.makeText(this, "Unable to start sharing.", Toast.LENGTH_LONG).show(); }
    }
    @Override protected void onStart() { super.onStart(); handler.post(refresh); }
    @Override protected void onStop() { handler.removeCallbacks(refresh); super.onStop(); }
}
