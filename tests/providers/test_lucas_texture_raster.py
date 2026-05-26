from nkz_soil.providers.lucas_texture_raster import _sample_points, LucasTextureRasterProvider


def test_sample_points_includes_centroid_and_interior():
    poly = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}
    pts = _sample_points(poly, n=5)
    assert (0.5, 0.5) in [(round(x, 3), round(y, 3)) for x, y in pts]
    assert len(pts) >= 1


def test_point_geometry_yields_single_sample():
    pt = {"type": "Point", "coordinates": [-1.64, 42.81]}
    pts = _sample_points(pt, n=5)
    assert pts == [(-1.64, 42.81)]


def test_provider_metadata():
    p = LucasTextureRasterProvider()
    assert p.name == "LUCAS-Texture"
    assert p.priority == 22
