package online.voidbot.rpcprobe;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import com.discord.socialsdk.DiscordSocialSdkInit;

public final class ProbeActivity extends Activity {
    static { System.loadLibrary("void_rpc_probe"); }
    private native void initNative();
    private native void publishNative();
    private native void clearNative();
    private native String tickNative();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView status;
    private final Runnable pump = new Runnable() {
        @Override public void run() {
            status.setText(tickNative());
            handler.postDelayed(this, 100);
        }
    };
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        DiscordSocialSdkInit.setEngineActivity(this);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(32, 48, 32, 32);
        TextView title = new TextView(this);
        title.setText("VOID Rich Presence — local test only");
        title.setTextSize(22);
        layout.addView(title);
        status = new TextView(this);
        status.setText("Not started");
        layout.addView(status);
        Button publish = new Button(this);
        publish.setText("Publish test activity");
        publish.setOnClickListener(v -> publishNative());
        layout.addView(publish);
        Button clear = new Button(this);
        clear.setText("Clear test activity");
        clear.setOnClickListener(v -> clearNative());
        layout.addView(clear);
        setContentView(layout);
        initNative();
    }
    @Override protected void onStart() {
        super.onStart();
        handler.post(pump);
    }
    @Override protected void onStop() {
        clearNative();
        tickNative();
        handler.removeCallbacks(pump);
        super.onStop();
    }
}
