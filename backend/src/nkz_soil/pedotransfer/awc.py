def awc_from_horizons(field_capacity: float, wilting_point: float) -> float:
    """Available water capacity = field capacity - wilting point."""
    return round(field_capacity - wilting_point, 3)
