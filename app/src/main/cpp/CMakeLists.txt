# the native halves of audio: pass (the direct usb driver and the aaudio exclusive output) and 3d sims (the room), each its own small library with no third-party code
cmake_minimum_required(VERSION 3.22.1)
project(mochypass LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(mochypass SHARED usb_pass.cpp exclusive_pass.cpp store_guard.cpp)
if(DEFINED STORE_GUARD_DIR)
    target_include_directories(mochypass PRIVATE "${STORE_GUARD_DIR}")
    target_compile_definitions(mochypass PRIVATE HAS_STORE_GUARD_DATA=1)
endif()
target_compile_options(mochypass PRIVATE -O2 -Wall -fvisibility=hidden)
# aaudio is opened at runtime, so only the log and the loader are linked; that keeps the library loadable on android 7
target_link_libraries(mochypass log dl)
# 16 kb pages on android 15 phones need the segments aligned to them
target_link_options(mochypass PRIVATE "-Wl,-z,max-page-size=16384")

add_library(mochystage SHARED stage/splitter.cpp stage/hrtf.cpp stage/tail.cpp stage/engine.cpp stage/stage_jni.cpp)
# o3 lets the compiler vectorise the ear filters, the biggest cost of the room
target_compile_options(mochystage PRIVATE -O3 -ffp-contract=fast -Wall -fvisibility=hidden)
target_link_options(mochystage PRIVATE "-Wl,-z,max-page-size=16384")

# Only the explicit local private build links the separately supplied SDK.
option(VOID_NATIVE_RPC "Authorized private RPC test" OFF)
if(VOID_NATIVE_RPC)
    find_package(discord_partner_sdk REQUIRED CONFIG)
    add_library(void_music_rpc SHARED void_music_rpc.cpp)
    set_property(TARGET void_music_rpc PROPERTY CXX_STANDARD 20)
    target_link_libraries(void_music_rpc PRIVATE discord_partner_sdk::discord_partner_sdk)
    target_link_options(void_music_rpc PRIVATE "-Wl,-z,max-page-size=16384")
endif()
