# breeze_poc/app_musetalk_livekit_publisher.py
# v0.10 Phase 2 - LiveKit WebRTC SFU publisher (2026-05-25 calcifer)
# (c) 2026 Edward / BeyondPath
#
# Companion to breeze_poc/app_musetalk.py (Phase 1 idle/speaking continuous endpoints).
# This app spawns a Modal worker that joins a LiveKit room as `sophie-renderer`
# and pushes idle frames to a video track.
#
# Mode handling:
#   - mode="idle":     pulls frames from existing musetalk-poc app via Modal Function
#                      reference (avoid duplicate model loading)
#   - mode="speaking": Phase 2 leaves this as fallback (cache hit / sophie-speaking
#                      animation handled by castle backend, not this worker).
#                      Future v0.11+ will add real-time audio chunk publishing.
#
# Deployment:
#   python -m modal deploy breeze_poc/app_musetalk_livekit_publisher.py
#
# LiveKit Python SDK alignment (official docs verified):
#   - livekit.rtc.Room() + room.connect(url, token)
#   - livekit.rtc.VideoSource(width, height) custom source
#   - livekit.rtc.LocalVideoTrack.create_video_track(name, source)
#   - VideoFrame(width, height, VideoBufferType.RGBA, data)
#   - source.capture_frame(frame) called per frame at fps cadence
#
# Modal app name MUST match castle/server/livekit_endpoints.py spawn lookup:
#   modal.Function.from_name("castle-voice-engine-musetalk-livekit-publisher", "publish_to_room")

import modal

# Slim image with livekit-rtc + opencv (for JPEG decode from idle endpoint).
# We do NOT load MuseTalk model here - we call the existing musetalk-poc app
# via Modal Function reference to reuse its warm runner.
publisher_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "libgl1", "libglib2.0-0")
    .pip_install(
        "livekit>=0.20,<2.0",          # rtc client
        "livekit-api>=0.7,<2.0",       # for room admin if needed (not strictly required here)
        "opencv-python-headless==4.9.0.80",
        "numpy==1.23.5",
        "modal>=0.65,<2.0",            # to call sibling Modal app
    )
)

app = modal.App("castle-voice-engine-musetalk-livekit-publisher")

# Secret from `livekit-creds` Modal secret (LIVEKIT_API_KEY/SECRET/URL).
LIVEKIT_SECRET = modal.Secret.from_name("livekit-creds")


@app.function(
    image=publisher_image,
    secrets=[LIVEKIT_SECRET],
    timeout=600,             # 10 min max session - WebRTC keeps room alive
    cpu=2.0,
    memory=2048,
    # No GPU - we read JPEG frames from musetalk-poc and forward to LiveKit
)
async def publish_to_room(room: str, mode: str = "idle", duration_s: float = 300.0, fps: int = 25):
    """Join LiveKit room as sophie-renderer and push idle frames as video track.

    Args:
      room: LiveKit room name (e.g. "sophie-abc12345-1716624000")
      mode: "idle" - pull from musetalk-poc /idle_continuous (default)
            "speaking" - reserved for v0.11+ (currently falls back to idle)
      duration_s: max session length (default 5 min)
      fps: video frame rate (default 25 = match MuseTalk)

    Returns:
      dict {ok, room, frames_published, dt_s, mode, terminated_reason}
    """
    import os
    import time
    import asyncio
    import numpy as np
    import cv2
    from livekit import rtc

    api_key = os.environ.get("LIVEKIT_API_KEY", "").strip()
    api_secret = os.environ.get("LIVEKIT_API_SECRET", "").strip()
    url = os.environ.get("LIVEKIT_URL", "").strip()

    if not (api_key and api_secret and url):
        return {
            "ok": False,
            "detail": "livekit creds missing in publisher Modal secret",
            "missing": {
                "LIVEKIT_API_KEY": not api_key,
                "LIVEKIT_API_SECRET": not api_secret,
                "LIVEKIT_URL": not url,
            },
        }

    # Mint our own access token for sophie-renderer identity (server SDK)
    try:
        from livekit import api as lkapi
    except ImportError as e:
        return {"ok": False, "detail": f"livekit-api import fail: {e}"}

    try:
        grants = lkapi.VideoGrants(
            room_join=True,
            room=room,
            can_publish=True,
            can_subscribe=False,    # renderer only publishes
            can_publish_data=True,
        )
        renderer_token = (
            lkapi.AccessToken(api_key, api_secret)
            .with_identity(f"sophie-renderer-{int(time.time())}")
            .with_name("sophie-renderer")
            .with_grants(grants)
            .with_ttl(int(duration_s) + 60)
            .to_jwt()
        )
    except Exception as e:
        return {"ok": False, "detail": f"renderer token mint fail: {e}"}

    # ----- Connect to room ------------------------------------------------
    rtc_room = rtc.Room()
    try:
        await rtc_room.connect(url, renderer_token)
        print(f"[publisher] connected to room={room} url={url}", flush=True)
    except Exception as e:
        return {"ok": False, "detail": f"room.connect fail: {e}"}

    # ----- Create video source + track + publish --------------------------
    # Frame size - we use 512x512 to match MuseTalk reference output.
    # Real PoC: query musetalk-poc /references for actual size.
    WIDTH, HEIGHT = 512, 512
    source = rtc.VideoSource(WIDTH, HEIGHT)
    track = rtc.LocalVideoTrack.create_video_track("sophie-cam", source)
    publication_options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_CAMERA)

    try:
        publication = await rtc_room.local_participant.publish_track(track, publication_options)
        print(f"[publisher] track published · sid={publication.sid}", flush=True)
    except Exception as e:
        try:
            await rtc_room.disconnect()
        except Exception:
            pass
        return {"ok": False, "detail": f"publish_track fail: {e}"}

    # ----- Pull frames from musetalk-poc /idle_continuous endpoint --------
    # We re-use the existing Phase 1 generator via Modal Function reference
    # to avoid loading MuseTalk model twice. The function yields JPEG bytes
    # at ~25 fps; we decode and push to LiveKit VideoSource.

    frames_published = 0
    t0 = time.time()
    terminated_reason = "duration_reached"

    try:
        idle_runner = modal.Cls.from_name(
            "castle-voice-engine-musetalk-poc",
            "MuseTalkRunner",
        )
        # Modal Cls from_name returns a cls reference; we need an instance method.
        # Pattern: idle_runner().generate_idle_continuous.remote_gen(...)
        runner_instance = idle_runner()
        gen = runner_instance.generate_idle_continuous.remote_gen(
            duration_s=duration_s,
            fps=fps,
            start_ref=None,
            rotate_every_s=8.0,    # rotate idle variant every 8s
        )
    except Exception as e:
        # musetalk-poc not deployed or method missing → fail loud (Edward sees error)
        try:
            await rtc_room.disconnect()
        except Exception:
            pass
        return {
            "ok": False,
            "detail": (
                f"musetalk-poc generator lookup fail: {e}. "
                "Deploy with: python -m modal deploy breeze_poc/app_musetalk.py"
            ),
        }

    frame_interval_s = 1.0 / float(fps)
    next_emit_t = time.time()

    try:
        for item in gen:
            if item.get("error"):
                terminated_reason = f"generator_error: {item.get('error')[:120]}"
                break
            jpg_bytes = item.get("frame", b"")
            if not jpg_bytes:
                continue

            # Decode JPEG -> BGR np array
            arr = np.frombuffer(jpg_bytes, dtype=np.uint8)
            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if bgr is None:
                continue

            # Match VideoSource size (resize if mismatch)
            if bgr.shape[1] != WIDTH or bgr.shape[0] != HEIGHT:
                bgr = cv2.resize(bgr, (WIDTH, HEIGHT))

            # Convert BGR -> RGBA (LiveKit VideoFrame expects RGBA)
            rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGBA)

            # Build VideoFrame
            frame = rtc.VideoFrame(
                width=WIDTH,
                height=HEIGHT,
                type=rtc.VideoBufferType.RGBA,
                data=rgba.tobytes(),
            )
            source.capture_frame(frame)
            frames_published += 1

            # Pace at fps cadence (avoid burst)
            next_emit_t += frame_interval_s
            sleep_s = next_emit_t - time.time()
            if sleep_s > 0:
                await asyncio.sleep(sleep_s)

            # Hard timeout (defensive)
            if (time.time() - t0) >= duration_s:
                terminated_reason = "duration_reached"
                break
    except Exception as e:
        terminated_reason = f"publish_loop_exception: {str(e)[:200]}"
        print(f"[publisher] {terminated_reason}", flush=True)
    finally:
        try:
            await rtc_room.disconnect()
            print("[publisher] disconnected from room", flush=True)
        except Exception:
            pass

    dt = time.time() - t0
    print(f"[publisher] DONE · room={room} frames={frames_published} dt={dt:.1f}s reason={terminated_reason}", flush=True)
    return {
        "ok": True,
        "room": room,
        "mode": mode,
        "frames_published": frames_published,
        "dt_s": round(dt, 2),
        "terminated_reason": terminated_reason,
    }


# ---------------------------------------------------------------------------
# CLI entrypoint for quick local test:
#   python -m modal run breeze_poc/app_musetalk_livekit_publisher.py::test_publish --room=sophie-test
# ---------------------------------------------------------------------------
@app.local_entrypoint()
def test_publish(room: str = "sophie-test-room", duration_s: float = 30.0):
    print(f"[test] spawning publish_to_room(room={room}, duration_s={duration_s})")
    result = publish_to_room.remote(room=room, duration_s=duration_s)
    print(f"[test] result: {result}")
    return result
