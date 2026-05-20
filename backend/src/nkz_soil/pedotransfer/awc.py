def awc_from_horizons(field_capacity: float, wilting_point: float) -> float:
    """Available water capacity = field capacity - wilting point.

    Returns 0 if PWP >= FC (physically impossible input).
    """
    return round(max(0.0, field_capacity - wilting_point), 3)
