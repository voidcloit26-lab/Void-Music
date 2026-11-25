#include <jni.h>
#include <memory>
#include <string>
#include <ctime>
#define DISCORDPP_IMPLEMENTATION
#include "discordpp.h"

// Called only on the Java main thread; no account credentials or network gateway.
namespace {
std::shared_ptr<discordpp::Client> client;
std::string status = "Not initialized";
unsigned generation = 0;
constexpr uint64_t APP_ID = 1553388915300245594ULL;
}
extern "C" JNIEXPORT void JNICALL
Java_online_voidbot_rpcprobe_ProbeActivity_initNative(JNIEnv*, jobject) {
    if (!client) {
        client = std::make_shared<discordpp::Client>();
        client->SetApplicationId(APP_ID);
        status = "Ready for local RPC test";
    }
}
extern "C" JNIEXPORT void JNICALL
Java_online_voidbot_rpcprobe_ProbeActivity_publishNative(JNIEnv*, jobject) {
    if (!client) return;
    const auto request = ++generation;
    discordpp::Activity activity;
    activity.SetName("VOID Music");
    activity.SetType(discordpp::ActivityTypes::Listening);
    activity.SetDetails("Rich Presence test");
    activity.SetState("VOID Music - test activity");
    discordpp::ActivityAssets assets;
    assets.SetLargeImage("void_music");
    assets.SetLargeText("VOID Music");
    activity.SetAssets(assets);
    discordpp::ActivityTimestamps timestamps;
    timestamps.SetStart(static_cast<uint64_t>(std::time(nullptr)));
    activity.SetTimestamps(timestamps);
    discordpp::ActivityButton first;
    first.SetLabel("Open Song");
    first.SetUrl("https://music.youtube.com/");
    activity.AddButton(first);
    discordpp::ActivityButton community;
    community.SetLabel("Join MARS Community");
    community.SetUrl("https://discord.gg/marscm");
    activity.AddButton(community);
    status = "Waiting for Discord response";
    client->UpdateRichPresence(std::move(activity), [request](discordpp::ClientResult result) {
        if (request != generation) return;
        status = result.Successful() ? "SDK accepted update; verify profile on another account" : "SDK rejected update; check Discord and activity sharing";
    });
}
extern "C" JNIEXPORT void JNICALL
Java_online_voidbot_rpcprobe_ProbeActivity_clearNative(JNIEnv*, jobject) {
    ++generation;
    if (client) client->ClearRichPresence();
    status = "Clear requested";
}
extern "C" JNIEXPORT jstring JNICALL
Java_online_voidbot_rpcprobe_ProbeActivity_tickNative(JNIEnv* env, jobject) {
    if (client) discordpp::RunCallbacks();
    return env->NewStringUTF(status.c_str());
}
