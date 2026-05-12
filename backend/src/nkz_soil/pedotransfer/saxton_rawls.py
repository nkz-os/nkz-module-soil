def saxton_rawls_2006(sand: float, clay: float, organic_carbon: float) -> dict:
    """Saxton & Rawls (2006) pedotransfer functions.

    Inputs: sand (%), clay (%), organic_carbon (%)
    Returns: dict with ksat (mm/h), field_capacity (cm3/cm3), wilting_point (cm3/cm3)

    Note: sand and clay are expected as percentages (0-100) and converted
    to mass fractions internally. The regression equations use mass fractions.
    """
    s = sand / 100
    c = clay / 100
    om = (organic_carbon * 1.724) / 100

    theta_1500t = -0.024 * s + 0.487 * c + 0.006 * om + \
                  0.005 * s * om - 0.013 * c * om + \
                  0.068 * s * c + 0.031
    theta_1500 = theta_1500t + 0.14 * theta_1500t - 0.02

    theta_33t = -0.251 * s + 0.195 * c + 0.011 * om + \
                0.006 * s * om - 0.027 * c * om + \
                0.452 * s * c + 0.299
    theta_33 = theta_33t + 1.283 * theta_33t ** 2 - 0.374 * theta_33t - 0.015

    theta_s33t = 0.278 * s + 0.034 * c + 0.022 * om - \
                 0.018 * s * om - 0.027 * c * om - \
                 0.584 * s * c + 0.078
    theta_s33 = theta_s33t + 0.636 * theta_s33t - 0.107

    lam = max(theta_33 - theta_1500, 0.001)
    diff = max(theta_s33 - theta_33, 0.001)
    ksat = 1930 * diff ** (3 - lam)

    return {
        "ksat": round(ksat, 2),
        "field_capacity": round(theta_33, 3),
        "wilting_point": round(theta_1500, 3),
    }
