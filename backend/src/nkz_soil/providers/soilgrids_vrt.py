"""Point reads from the SoilGrids WebDAV mosaics without opening the mosaic.

Each SoilGrids layer is published as a VRT (~6 MB of XML) that stitches about
13,000 Cloud-Optimized GeoTIFF tiles. Opening the VRT through GDAL downloads and
parses all of it on every read, which for a full profile (8 properties x 5
depths) is ~240 MB and enough CPU to starve the worker.

Instead, each VRT is parsed once per process into a compact tile index; a point
read then resolves its tile and opens only that tile.
"""

from __future__ import annotations

import re
import threading
from array import array
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

_GEOTRANSFORM = re.compile(r"<GeoTransform>([^<]+)</GeoTransform>")
_SRS = re.compile(r"<SRS[^>]*>([^<]+)</SRS>")
_SOURCE = re.compile(r"<(?:Complex|Simple)Source>(.*?)</(?:Complex|Simple)Source>", re.DOTALL)
_FILENAME = re.compile(r"<SourceFilename[^>]*>([^<]+)</SourceFilename>")
_RECT = r'<{tag} xOff="([-\d.]+)" yOff="([-\d.]+)" xSize="([-\d.]+)" ySize="([-\d.]+)"'
_SRC_RECT = re.compile(_RECT.format(tag="SrcRect"))
_DST_RECT = re.compile(_RECT.format(tag="DstRect"))

_FETCH_TIMEOUT_S = 120.0


@dataclass(frozen=True)
class TileSource:
    url: str
    src: tuple[float, float, float, float]  # xOff, yOff, xSize, ySize in the tile
    dst: tuple[float, float, float, float]  # same, in the mosaic


class TileIndex:
    """Tile rectangles of one mosaic, stored compactly (~13k tiles per VRT)."""

    def __init__(self, crs_wkt: str, geotransform: tuple[float, ...],
                 sources: tuple[TileSource, ...] | list[TileSource]):
        self.crs_wkt = crs_wkt
        self.geotransform = tuple(geotransform)
        self._urls = [s.url for s in sources]
        self._src = array("d", [v for s in sources for v in s.src])
        self._dst = array("d", [v for s in sources for v in s.dst])

    def __len__(self) -> int:
        return len(self._urls)

    def pixel(self, x: float, y: float) -> tuple[int, int]:
        """Mosaic (col, row) of a point given in the mosaic CRS."""
        x0, dx, _, y0, _, dy = self.geotransform
        return int((x - x0) // dx), int((y - y0) // dy)

    def locate(self, col: int, row: int) -> tuple[str, int, int] | None:
        """(tile url, col, row inside the tile) for a mosaic pixel, or None."""
        d, s = self._dst, self._src
        for i in range(len(self._urls)):
            k = 4 * i
            dx0, dy0, dw, dh = d[k], d[k + 1], d[k + 2], d[k + 3]
            if dx0 <= col < dx0 + dw and dy0 <= row < dy0 + dh:
                tcol = int(s[k] + (col - dx0) * s[k + 2] / dw)
                trow = int(s[k + 1] + (row - dy0) * s[k + 3] / dh)
                return self._urls[i], tcol, trow
        return None


def parse_vrt(text: str, vrt_url: str) -> TileIndex:
    gt = _GEOTRANSFORM.search(text)
    srs = _SRS.search(text)
    if not gt or not srs:
        raise ValueError(f"not a georeferenced VRT: {vrt_url}")
    geotransform = tuple(float(v) for v in gt.group(1).split(","))
    if len(geotransform) != 6:
        raise ValueError(f"bad GeoTransform in {vrt_url}")
    sources = []
    for block in _SOURCE.finditer(text):
        body = block.group(1)
        name, src, dst = _FILENAME.search(body), _SRC_RECT.search(body), _DST_RECT.search(body)
        if not (name and src and dst):
            continue
        sources.append(TileSource(
            url=urljoin(vrt_url, name.group(1).strip()),
            src=tuple(float(v) for v in src.groups()),
            dst=tuple(float(v) for v in dst.groups()),
        ))
    if not sources:
        raise ValueError(f"VRT has no tile sources: {vrt_url}")
    return TileIndex(_unescape(srs.group(1)), geotransform, sources)


def _unescape(s: str) -> str:
    return s.replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def _fetch_text(url: str) -> str:
    resp = httpx.get(url, timeout=_FETCH_TIMEOUT_S, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


_cache: dict[str, TileIndex] = {}
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def tile_index(vrt_url: str) -> TileIndex:
    """Parsed index of a VRT, downloaded once per process (thread-safe)."""
    cached = _cache.get(vrt_url)
    if cached is not None:
        return cached
    with _locks_guard:
        lock = _locks.setdefault(vrt_url, threading.Lock())
    with lock:
        cached = _cache.get(vrt_url)
        if cached is None:
            cached = parse_vrt(_fetch_text(vrt_url), vrt_url)
            _cache[vrt_url] = cached
        return cached
