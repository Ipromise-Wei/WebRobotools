"""Compact, browser-safe transport for ROS OccupancyGrid snapshots."""

from __future__ import annotations

from array import array
import base64
import zlib
from typing import Any

from app.models.visualization import MapSnapshot


MAP_DATA_ENCODING = "zlib-base64-int8"


def encode_map_snapshot(snapshot: MapSnapshot) -> dict[str, Any]:
    """Encode signed OccupancyGrid cells without JSON-expanding every cell.

    ROS OccupancyGrid values are signed int8 values in the range -1..100.
    Sending their JSON list costs several bytes per cell and monopolizes the
    FastAPI event loop for large maps. A level-1 zlib stream is fast to create
    and is efficiently decoded by current Chrome via DecompressionStream.
    """
    cells = array("b", snapshot.data).tobytes()
    encoded = base64.b64encode(zlib.compress(cells, level=1)).decode("ascii")
    return {
        "frame_id": snapshot.frame_id,
        "width": snapshot.width,
        "height": snapshot.height,
        "resolution": snapshot.resolution,
        "origin_x": snapshot.origin_x,
        "origin_y": snapshot.origin_y,
        "origin_yaw": snapshot.origin_yaw,
        "data_encoding": MAP_DATA_ENCODING,
        "data": encoded,
        "path": [{"x": point.x, "y": point.y} for point in snapshot.path],
        "revision": snapshot.revision,
        "updated_at": snapshot.updated_at.isoformat(),
    }
