from app.camera_relay import extract_latest_complete_jpeg


def test_camera_relay_discards_backlog_and_keeps_only_newest_jpeg() -> None:
    first = b"\xff\xd8old-frame\xff\xd9"
    newest = b"\xff\xd8newest-frame\xff\xd9"
    partial = b"\xff\xd8next-frame"
    buffer = bytearray(b"noise" + first + newest + partial)

    frame = extract_latest_complete_jpeg(buffer, 1024)

    assert frame == newest
    assert buffer == bytearray(partial)
