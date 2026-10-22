def scs_hydrologic_group(ksat: float, depth_to_restrictive: float | None = None) -> str:
    """NRCS SCS hydrologic soil group based on saturated hydraulic conductivity."""
    if ksat > 36:
        return "A"
    elif ksat > 3.6:
        return "B"
    elif ksat > 0.36:
        return "C"
    return "D"
