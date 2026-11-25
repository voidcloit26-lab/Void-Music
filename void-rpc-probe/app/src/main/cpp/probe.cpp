#include <jni.h>
#include <memory>
#include <string>
#include <ctime>
#include <cstdint>
#define DISCORDPP_IMPLEMENTATION
#include "discordpp.h"

namespace {
std::shared_ptr<discordpp::Client> client;
std::string status = "Not initialized";
unsigned generation = 0;
constexpr uint64_t APP_ID = 1553388915300245594ULL;

std::string bytes(JNIEnv* env, jbyteArray array) {
    if (!array) return {};
    auto size = env->GetArrayLength(array);
    if (size <= 0 || size > 512) return {};
    std::string s(static_cast<size_t>(size), '\0');
    env->GetByteArrayRegion(array, 0, size, reinterpret_cast<jbyte*>(s.data()));
    return s;
}
std::string encode(const std::string& s) {
    const char* hex = "0123456789ABCDEF";
    std::string out;
    for (unsigned char c : s) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
            (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' || c == '~') out += char(c);
        else { out += '%'; out += hex[c >> 4]; out += hex[c & 15]; }
    }
    return out;
}
void publish(std::string title, std::string artist, std::string art,
             uint64_t start, uint64_t end, int provider) {
    if (!client) return;
    const auto request = ++generation;
    discordpp::Activity activity;
    activity.SetName("VOID Music");
    activity.SetType(discordpp::ActivityTypes::Listening);
    activity.SetDetails(title);
    activity.SetState(artist);
    discordpp::ActivityAssets assets;
    assets.SetLargeImage(art.empty() ? "void_music" : art);
    assets.SetLargeText("VOID Music");
    if (!art.empty()) assets.SetSmallImage("void_music");
    activity.SetAssets(assets);
    if (start > 0) {
        discordpp::ActivityTimestamps timestamps;
        timestamps.SetStart(start * 1000ULL);
        if (end > start) timestamps.SetEnd(end * 1000ULL);
        activity.SetTimestamps(timestamps);
    }
    std::string query = encode(title + " " + artist);
    const char* labels[] = {"Open YouTube Music", "Open Spotify", "Open Apple Music", "Open TIDAL"};
    const char* links[] = {"https://music.youtube.com/search?q=", "https://open.spotify.com/search/", "https://music.apple.com/search?term=", "https://listen.tidal.com/search?q="};
    if (provider < 0 || provider > 3) provider = 0;
    discordpp::ActivityButton first;
    first.SetLabel(labels[provider]);
    first.SetUrl(std::string(links[provider]) + query);
    activity.AddButton(first);
    discordpp::ActivityButton community;
    community.SetLabel("Join MARS Community");
    community.SetUrl("https://discord.gg/marscm");
    activity.AddButton(community);
    status = "Waiting for Discord response";
    client->UpdateRichPresence(std::move(activity), [request](discordpp::ClientResult result) {
        if (request != generation) return;
        status = result.Successful() ? "SDK accepted update; verify profile on another account" : "SDK rejected update (type " + std::to_string(static_cast<int>(result.Type())) + ")";
    });
}
}
extern "C" JNIEXPORT void JNICALL
Java_online_voidbot_rpcprobe_PresenceService_initNative(JNIEnv*, jobject) {
    if (!client) {
        client = std::make_shared<discordpp::Client>();
        client->SetApplicationId(APP_ID);
        client->SetEngineManagedAudioSession(true);
        status = "Ready for local RPC test";
    }
}
extern "C" JNIEXPORT void JNICALL
Java_online_voidbot_rpcprobe_PresenceService_publishNative(JNIEnv*, jobject) {
    publish("Rich Presence test", "VOID Music - test activity", "", static_cast<uint64_t>(std::time(nullptr)), 0, 0);
}
extern "C" JNIEXPORT void JNICALL
Java_online_voidbot_rpcprobe_PresenceService_publishTrackNative(JNIEnv* env, jobject,
    jbyteArray title, jbyteArray artist, jbyteArray art, jlong start, jlong end, jint provider) {
    publish(bytes(env, title), bytes(env, artist), bytes(env, art),
            start > 0 ? static_cast<uint64_t>(start) : 0,
            end > 0 ? static_cast<uint64_t>(end) : 0, provider);
}
extern "C" JNIEXPORT void JNICALL
Java_online_voidbot_rpcprobe_PresenceService_clearNative(JNIEnv*, jobject) {
    ++generation;
    if (client) client->ClearRichPresence();
    status = "Clear requested";
}
extern "C" JNIEXPORT jstring JNICALL
Java_online_voidbot_rpcprobe_PresenceService_tickNative(JNIEnv* env, jobject) {
    if (client) discordpp::RunCallbacks();
    return env->NewStringUTF(status.c_str());
}
