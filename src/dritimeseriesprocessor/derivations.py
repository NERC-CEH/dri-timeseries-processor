import math

import numpy as np


def potential_evapotranspiration(rn, g, ta_min, ta_max, rh_min, rh_max, ws, pa, period):
    """ Calculate potential evaporation from measured variables.

    Only suitable for 1-day or sub-daily time resolutions.

    Steps taken from Penman-Monteith Evapotranspiration (FAO-56 Method)
    https://www.fao.org/4/x0490e/x0490e06.htm#equation

    Some useful step-by-step guides here:
    https://www.agraria.unirc.it/documentazione/materiale_didattico/1462_2016_412_24509.pdf

    Args:
        rn: Net radiation over time period [MJ m-2<time>-1]
        g: Soil heat flux density [MJ m-2<time>-1]
        ta_min: Minimum air temperature over time period [degC]
        ta_max: Maximum air temperature over time period [degC]
        rh_min: Minimum relative humidity over time period [%]
        rh_max: Minimum relative humidity over time period [%]
        ws: Average wind speed at 2m height over time period [ms-1]
        pa: Average atmospheric pressure over time period [kPa]
        period: Time period over which the calculation is valid

    Returns:
        Potential evapotranspiration [mm<time>-1]
    """
    ta_mean = (ta_min + ta_max) / 2
    es_min = saturation_vapour_pressure(ta_min)
    es_max = saturation_vapour_pressure(ta_max)
    es_mean = (es_min + es_max) / 2
    ea = actual_vapour_pressure_from_relative_humidity(rh_max, rh_min, es_max, es_min)
    lv = latent_heat_of_vaporization(ta_mean)

    vpd = vapour_pressure_deficit(es_mean, ea)
    gamma = psychrometric_constant(pa, lv)
    delta = slope_of_vapour_pressure_curve(es_mean, ta_mean)

    reference_crop_type_numerator = 900  # daily... need to think about getting value for period
    reference_crop_type_denominator = 0.34  # daily... need to think about getting value for period

    radiation_term = 0.408 * delta * (rn - g)
    aerodynamic_term = gamma * (reference_crop_type_numerator / (ta_mean + 273)) * ws * vpd
    resistance_term = delta + (gamma * (1 + (reference_crop_type_denominator * ws)))

    return (radiation_term + aerodynamic_term) / resistance_term


def psychrometric_constant(pa, lv):
    """ Calculate psychrometric constant

    Steps taken from FAO-56 method (eq8) https://www.fao.org/4/x0490e/x0490e07.htm#psychrometric%20constant%20(g)

    Args:
        pa: Atmospheric pressure [kPa]
        lv: Latent heat of vaporization [MJ kg-1]

    Returns:
        Psychrometric constant (gamma) [kPa degC-1]
    """
    cp = 1.013 * 10e-3  # Specific heat at constant pressure
    e = 0.622  # Ratio molecular weight of water vapour/dry air
    return (cp * pa) / (e * lv)


def saturation_vapour_pressure(ta):
    """ Calculate saturation vapour pressure from air temperature.

    Steps taken from FAO-56 method (eq11) https://www.fao.org/4/x0490e/x0490e07.htm#calculation%20procedures

    Args:
        ta: Air temperature [degC]

    Returns:
        Saturation vapour pressure (es) [kPa]
    """
    return 0.6108 * np.exp((17.27 * ta) / (ta + 237.3))


def slope_of_vapour_pressure_curve(es_mean, ta):
    """ Calculate slope of vapour pressure curve from measured variables.

    Steps taken from FAO-56 method (eq13) https://www.fao.org/4/x0490e/x0490e07.htm#calculation%20procedures

    Args:
        es_mean: Saturation vapour pressure at mean temperature over time period [kPa]
        ta: Air temperature [degC]

    Returns:
        Slope of vapour pressure curve (delta) [kPa degC-1]
    """
    return (4098 * es_mean) / ((ta + 237.3) ** 2)


def actual_vapour_pressure_from_relative_humidity(rh_max, rh_min, es_max, es_min):
    """ Calculate Actual vapour pressure from relative humidity.

    Steps taken from FAO-56 method (eq17) https://www.fao.org/4/x0490e/x0490e07.htm#calculation%20procedures

    Args:
        rh_max: Maximum relative humidity over time period [%]
        rh_min: Minimum relative humidity over time period [%]
        es_max: Saturation vapour pressure at maximum temperature over time period [kPa]
        es_min: Saturation vapour pressure at minimum temperature over time period [kPa]

    Returns:
        Actual vapour pressure (ea) [kPa]
    """
    return ((es_min * (rh_max / 100)) + (es_max * (rh_min / 100))) / 2


def vapour_pressure_deficit(es, ea):
    """ Calculate vapour pressure deficit.

    Args:
        es: Saturation vapour pressure [kPa]
        ea: Actual vapour pressure [kPa]

    Returns:
        Vapour pressure deficit (vpd) [kPa]
    """
    return es - ea


def wind_speed_height_correction(ws, measured_height):
    """ Correct wind speed to the standard 2m height.

    Steps taken from FAO-56 method (eq47) https://www.fao.org/4/x0490e/x0490e07.htm#wind%20profile%20relationship

    Args:
        ws: Wind speed measured at given height [ms-1]
        measured_height: The height the wind was measured at

    Returns:
        Wind speed corrected to 2m height [ms-1]
    """
    ws_corrected = ws * (4.87 / (math.log((67.8 * measured_height) - 5.42)))
    return ws_corrected


def latent_heat_of_vaporization(ta):
    """ Calculate latent heat of vaporization

    Steps taken from Harrison (1963), referenced by FAO Annex 3 https://www.fao.org/4/x0490e/x0490e0k.htm

    Harrison, L.P. 1963. "Fundamental concepts and definitions relating to humidity."
        In: Wexler, A. and Wildhack, W.A. (eds.) Humidity and Moisture. Vol. 3. Reinhold Publishing Company, New York

    Args:
        ta: Air temperature [degC]

    Returns:
        Latent heat of vaporization (lv) [MJ kg-1]
    """
    return 2.501 - ((2.361 * 10e-3) * ta)
