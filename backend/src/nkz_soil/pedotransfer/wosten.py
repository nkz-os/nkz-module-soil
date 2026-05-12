def wosten_hypres(sand: float, silt: float, clay: float, organic_carbon: float, bulk_density: float) -> dict:
    """Wosten et al. (1999) HYPRES pedotransfer functions."""
    om = organic_carbon * 1.724
    is_coarse = 0 if sand > 70 else 1
    ksat = 7.755 + 0.0352 * silt + 0.93 * is_coarse - \
           0.967 * bulk_density ** 2 - 0.000484 * clay ** 2 - \
           0.000322 * silt ** 2 + 0.001 * silt * is_coarse - \
           0.0748 * om - 0.643 * (silt / 10) - 0.0139 * sand * is_coarse - \
           0.167 * is_coarse + 0.0298 * is_coarse * sand
    return {"ksat": round(10 ** ksat * 10, 2)}
