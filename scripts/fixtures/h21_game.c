/* H21 instrumentation of raylib-games Arkanoid, NOT the original game build.
 * Original game: Marc Palau and Ramon Santamaria, zlib/libpng license, 2015.
 * The pinned original is included unchanged. This driver supplies automated
 * paddle/launch input, scales its real gameplay and adds audible collision
 * feedback plus an audio-sample-clock A/V marker. It is a light 2D workload.
 * No capture, network, devices, global preferences or product media clock.
 */
#include "raylib.h"
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <signal.h>
#include <stdarg.h>

static volatile sig_atomic_t stopRequested;
static void request_stop(int signal_number) { (void)signal_number; stopRequested = 1; }
static void game_log(int level, const char *message, va_list arguments) {
    (void)level; vfprintf(stderr, message, arguments); fputc('\n', stderr);
}

static bool H21KeyDown(int key);
static bool H21KeyPressed(int key);
static void H21BeginDrawing(void);
static void H21EndDrawing(void);
static int H21Width(void) { return 800; }
static int H21Height(void) { return 450; }
#define main original_arkanoid_main
#define IsKeyDown H21KeyDown
#define IsKeyPressed H21KeyPressed
#define BeginDrawing H21BeginDrawing
#define EndDrawing H21EndDrawing
#define GetScreenWidth H21Width
#define GetScreenHeight H21Height
#include "arkanoid.c"
#undef main
#undef IsKeyDown
#undef IsKeyPressed
#undef BeginDrawing
#undef EndDrawing
#undef GetScreenWidth
#undef GetScreenHeight

extern int h21_game_cover(void *window, const char *uuid);
static RenderTexture2D gameTexture;
static atomic_uint_fast64_t audioFrames;
static atomic_int collisionRemaining;
static uint64_t drawFrames;
static unsigned collisions, rounds;
static double started;

static void audio_callback(void *buffer, unsigned int frames)
{
    float *out = buffer;
    uint64_t first = atomic_load(&audioFrames);
    for (unsigned int i = 0; i < frames; i++) {
        uint64_t n = first + i;
        bool cue = n % 48000 < 9600;
        int left = atomic_load(&collisionRemaining);
        float collision = left > 0 ? 0.025f * sinf(2 * PI * 523 * n / 48000.0) : 0;
        if (left > 0) atomic_fetch_sub(&collisionRemaining, 1);
        out[i] = (cue ? 0.04f * sinf(2 * PI * 997 * n / 48000.0) : 0) + collision;
    }
    atomic_store(&audioFrames, first + frames);
}

static bool H21KeyDown(int key)
{
    // Bounded, declared gameplay automation. Existing collision/score logic is
    // unchanged; the moving offset avoids endlessly bouncing in one column.
    double target = ball.position.x + 22 * sin(GetTime() * 1.7);
    return (key == KEY_LEFT && player.position.x > target + 3)
        || (key == KEY_RIGHT && player.position.x < target - 3);
}
static bool H21KeyPressed(int key)
{
    return (key == KEY_SPACE && !ball.active) || (key == KEY_ENTER && gameOver);
}
static void H21BeginDrawing(void) { BeginTextureMode(gameTexture); }
static void H21EndDrawing(void)
{
    EndTextureMode();
    BeginDrawing();
    ClearBackground(BLACK);
    float w = GetScreenWidth(), h = GetScreenHeight();
    float scale = fminf(w / 800, (h - 100) / 450);
    DrawTexturePro(gameTexture.texture, (Rectangle){0, 0, 800, -450},
        (Rectangle){(w - 800*scale)/2, 80, 800*scale, 450*scale}, (Vector2){0,0}, 0, WHITE);
    uint64_t audio = atomic_load(&audioFrames);
    bool cue = audio % 48000 < 9600;
    DrawRectangle(0, 0, w, 64, cue ? (Color){20,210,65,255} : (Color){12,12,12,255});
    DrawText("MOTIVE H21 / raylib Arkanoid / automated 2D gameplay + A/V marker", 28, 70, 18, SKYBLUE);
    for (unsigned bit = 0; bit < 16; bit++)
        DrawRectangle(28 + bit*24, 26, 16, 16, (drawFrames >> bit)&1 ? WHITE : BLACK);
    EndDrawing();
    drawFrames++;
}

int main(int argc, char **argv)
{
    if (argc != 5 || strcmp(argv[1], "--display-uuid") || strcmp(argv[3], "--seconds")) return 64;
    char *end = NULL;
    long seconds = strtol(argv[4], &end, 10);
    if (!end || *end || seconds < 1 || seconds > 3900) return 64;
    signal(SIGTERM, request_stop);
    SetTraceLogCallback(game_log);
    SetTraceLogLevel(LOG_WARNING);
    SetConfigFlags(FLAG_WINDOW_UNDECORATED | FLAG_WINDOW_ALWAYS_RUN);
    InitWindow(1280, 720, "Motive H21 owned Arkanoid (modified automated game)");
    if (!IsWindowReady()) return 65;
    if (!h21_game_cover(GetWindowHandle(), argv[2])) { CloseWindow(); return 66; }
    InitAudioDevice();
    if (!IsAudioDeviceReady()) { CloseWindow(); return 67; }
    AudioStream stream = LoadAudioStream(48000, 32, 1);
    if (!IsAudioStreamValid(stream)) { CloseAudioDevice(); CloseWindow(); return 68; }
    SetAudioStreamCallback(stream, audio_callback);
    PlayAudioStream(stream);
    gameTexture = LoadRenderTexture(800,450);
    InitGame();
    SetTargetFPS(60);
    started = GetTime();
    double nextLog = started;
    while (!stopRequested && !WindowShouldClose() && GetTime() - started < seconds) {
        Vector2 prior = ball.speed;
        if (gameOver) rounds++;
        UpdateDrawFrame();
        if ((prior.x != ball.speed.x || prior.y != ball.speed.y) && ball.active) {
            collisions++;
            atomic_store(&collisionRemaining, 2400);
        }
        if (GetTime() >= nextLog) {
            printf("{\"event\":\"game\",\"seconds\":%.6f,\"draw_frames\":%llu,\"audio_frames\":%llu,\"collisions\":%u,\"rounds\":%u,\"ball\":[%.2f,%.2f],\"fps\":%d}\n",
                GetTime()-started, (unsigned long long)drawFrames,
                (unsigned long long)atomic_load(&audioFrames), collisions, rounds,
                ball.position.x, ball.position.y, GetFPS());
            fflush(stdout); nextLog += 1;
        }
    }
    StopAudioStream(stream);
    UnloadAudioStream(stream);
    CloseAudioDevice();
    UnloadRenderTexture(gameTexture);
    CloseWindow();
    return 0;
}
