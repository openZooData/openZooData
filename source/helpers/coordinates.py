import re


def is_valid_slug(value):
    """Validiert Zoo-Slug gegen erlaubte Zeichen."""
    return bool(re.match(r"^[a-z0-9_-]+$", value or ""))


def round_coordinates(lat, lon):
    """Rundet GPS-Koordinaten auf 4 Dezimalstellen (~11m Genauigkeit).
    DSGVO: Verhindert Rückschluss auf exakte Person/Position.
    Wirft ValueError bei ungültigen Koordinaten."""
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        raise ValueError(f"Ungültige Koordinaten: lat={lat}, lon={lon}")
    if not (-90 <= lat_f <= 90) or not (-180 <= lon_f <= 180):
        raise ValueError(f"Koordinaten außerhalb des gültigen Bereichs: lat={lat_f}, lon={lon_f}")
    return round(lat_f, 4), round(lon_f, 4)
