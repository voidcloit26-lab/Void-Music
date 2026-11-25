// Native local RPC adapter; SDK supplied separately only in an authorized build.
#include <jni.h>
#include <memory>
#include <string>
#include <cstdint>
#define DISCORDPP_IMPLEMENTATION
#include "discordpp.h"

namespace {
std::shared_ptr<discordpp::Client> client;
uint64_t generation = 0;
int status = 0;
constexpr uint64_t APP_ID = 1553388915300245594ULL;

std::string field(JNIEnv* env, jobjectArray fields, int i) {
    auto arr = static_cast<jbyteArray>(env->GetObjectArrayElement(fields, i));
    if (!arr) return {};
    auto size = env->GetArrayLength(arr);
    std::string result;
    if (size > 0 && size <= 1024) {
        result.resize(size);
        env->GetByteArrayRegion(arr, 0, size, reinterpret_cast<jbyte*>(result.data()));
    }
    env->DeleteLocalRef(arr);
    return result;
}
}
extern "C" JNIEXPORT void JNICALL
Java_com_mochyy_mochymusic_discord_NativePresenceBridge_initNative(JNIEnv*, jobject) {
    if (client) return;
    client = std::make_shared<discordpp::Client>();
    client->SetApplicationId(APP_ID);
    client->SetEngineManagedAudioSession(true);
}
extern "C" JNIEXPORT void JNICALL
Java_com_mochyy_mochymusic_discord_NativePresenceBridge_publishNative(
    JNIEnv* env, jobject, jobjectArray fields, jint kind, jlong start, jlong end) {
    if (!client || !fields || env->GetArrayLength(fields) != 11) return;
    const auto request = ++generation;
    discordpp::Activity activity;
    auto name = field(env, fields, 0);
    activity.SetName(name.empty() ? "VOID Music" : name);
    activity.SetType(kind == 0 ? discordpp::ActivityTypes::Playing : discordpp::ActivityTypes::Listening);
    auto details = field(env, fields, 1), state = field(env, fields, 2);
    if (!details.empty()) activity.SetDetails(details);
    if (!state.empty()) activity.SetState(state);
    discordpp::ActivityAssets assets;
    auto large = field(env, fields, 3), largeText = field(env, fields, 4);
    auto small = field(env, fields, 5), smallText = field(env, fields, 6);
    assets.SetLargeImage(large.empty() ? "void_music" : large);
    if (!largeText.empty()) assets.SetLargeText(largeText);
    if (!small.empty()) {
        assets.SetSmallImage(small);
        if (!smallText.empty()) assets.SetSmallText(smallText);
    }
    activity.SetAssets(assets);
    if (start > 0) {
        discordpp::ActivityTimestamps times;
        times.SetStart(static_cast<uint64_t>(start));
        if (end > start) times.SetEnd(static_cast<uint64_t>(end));
        activity.SetTimestamps(times);
    }
    for (int i : {7, 9}) {
        auto label = field(env, fields, i), url = field(env, fields, i+1);
        if (label.empty() || url.empty()) continue;
        discordpp::ActivityButton button;
        button.SetLabel(label);
        button.SetUrl(url);
        activity.AddButton(button);
    }
    status = 1;
    client->UpdateRichPresence(std::move(activity), [request](discordpp::ClientResult result) {
        if (request == generation) status = result.Successful() ? 2 : 3;
    });
}
extern "C" JNIEXPORT void JNICALL
Java_com_mochyy_mochymusic_discord_NativePresenceBridge_clearNative(JNIEnv*, jobject) {
    ++generation;
    if (client) client->ClearRichPresence();
    status = 0;
}
extern "C" JNIEXPORT jint JNICALL
Java_com_mochyy_mochymusic_discord_NativePresenceBridge_tickNative(JNIEnv*, jobject) {
    if (client) discordpp::RunCallbacks();
    return status;
}
