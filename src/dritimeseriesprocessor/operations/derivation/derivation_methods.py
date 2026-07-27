import logging
from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import ClassVar

import polars as pl
import time_stream as ts
from time_stream.operation import Operation

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.eddypro.eddypro_pipeline import EddyProPipeline
from dritimeseriesprocessor.operations.eddypro.eddypro_runner import EddyProRunner
from dritimeseriesprocessor.operations.eddypro.flux_despike import despike_df
from dritimeseriesprocessor.routers.data.data_router import DataRouter
from dritimeseriesprocessor.utils.enums import ConfigurationType, ProcessingLevel
from dritimeseriesprocessor.utils.polars_utils import join_time_intervals
from dritimeseriesprocessor.utils.time_stream_utils import merge_multiple_timeframes

logger = logging.getLogger(__name__)


class DerivationMethod(Operation, ABC):
    operation_type = ConfigurationType.DERIVATION
    inputs: ClassVar[tuple]
    config: DataProcessingMethodConfig

    def run(self, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        """Execute the common workflow to carry out a derivation calculation.

        Args:
            config: Configuration parameters including input TimeFrames and output specs

        Returns:
            TimeFrame containing the calculated derived variable
        """

        self.config = config

        # Extract and merge input data
        tf_map = {name: config.params[name] for name in self.inputs}

        # Get column references for calculation
        columns = {name: pl.col(tf.metadata["column_name"]) for name, tf in tf_map.items()}

        # Build data columns for any time-bound deployment attributes (e.g. anemometer sensor height)
        columns, merged_tf = self.merge_inputs(config, tf_map, columns)

        # Perform the calculation (subclass-specific)
        calculation_expr = self.expr(columns).alias(config.params["output_col"])
        result_df = merged_tf.df.with_columns(calculation_expr)

        return (
            ts.TimeFrame(
                df=result_df,
                time_name=merged_tf.time_name,
                resolution=config.params["resolution"],
                periodicity=config.params["periodicity"],
                time_anchor=config.params["time_anchor"],
            )
            .with_metadata({"column_name": config.params["output_col"]})
            .select(config.params["output_col"])
        )

    def merge_inputs(self, config: DataProcessingMethodConfig, tf_map: dict, columns: dict) -> tuple:
        """Merge the input TimeFrames into one, and join in any time-bound attribute columns.

        Assumes all input TimeFrames share a common periodicity, so they can be merged directly with
        `merge_multiple_timeframes`. Subclasses whose inputs have differing periodicities should
        override this method with their own merge/join strategy, calling `join_deployment_attributes`
        themselves if they also need time-bound attribute columns joined in.

        Args:
            config: Configuration parameters including input TimeFrames and output specs
            tf_map: Mapping of input name to its TimeFrame, one entry per name in `inputs`
            columns: Mapping of input name to its Polars column expression, one entry per name in `inputs`

        Returns:
            Tuple of:
                - columns: The input `columns` dict, with an added entry for each time-bound
                  attribute (e.g. anemometer sensor height) found in `config.params`
                - merged_tf: The merged TimeFrame, with any time-bound attribute columns joined in
        """
        merged_tf = merge_multiple_timeframes(list(tf_map.values()))
        return self.join_deployment_attributes(config, columns, merged_tf)

    @staticmethod
    def join_deployment_attributes(config: DataProcessingMethodConfig, columns: dict, merged_tf: ts.TimeFrame) -> tuple:
        """Join any time-bound deployment attribute columns (e.g. anemometer sensor height) onto a TimeFrame.

        Args:
            config: Configuration parameters including input TimeFrames and output specs
            columns: Mapping of input name to its Polars column expression
            merged_tf: The already-merged TimeFrame that deployment attribute columns should be joined onto

        Returns:
            Tuple of:
                - columns: The input `columns` dict, with an added entry for each time-bound
                  attribute (e.g. anemometer sensor height) found in `config.params`
                - merged_tf: The input `merged_tf`, with any time-bound attribute columns joined in
        """
        for param, value in config.params.items():
            if isinstance(value, dict) and value.get(f"{param}.source", "") == "deployment":
                # Join the deployment values to the main DataFrame
                merged_tf = merged_tf.with_df(
                    join_time_intervals(value[f"{param}.value"], merged_tf.df, merged_tf.time_name, param)
                )
                # Make sure the deployment value column is available to any calculation method that needs it
                columns[param] = pl.col(param)
        return columns, merged_tf

    @abstractmethod
    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Define the calculation expression for this derivation.

        Args:
            columns: Dictionary mapping variable names to Polars column expressions

        Returns:
            Polars expression that computes the derived variable
        """
        pass


@DerivationMethod.register
class NetRadiation(DerivationMethod):
    """Calculate net radiation - the difference between the downward and upward total radiation."""

    name = "calculate_rn"
    inputs = ("swin", "swout", "lwin", "lwout")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate net radiation (rn) [W m-2]

        Args:
            columns: Dict with keys of required columns for the calculation
                - swin: Incoming shortwave radiation [W m-2]
                - swout: Outgoing shortwave radiation [W m-2]
                - lwin: Incoming longwave radiation [W m-2]
                - lwout: Outgoing longwave radiation [W m-2]

        Returns:
            Polars expression computing rn
        """
        return columns["swin"] - columns["swout"] + columns["lwin"] - columns["lwout"]


@DerivationMethod.register
class MeanSoilHeatFlux(DerivationMethod):
    """Calculate the mean soil heat flux from inputs from multiple soil heat flux measurements.

    Soil heat flux defines the amount of thermal energy transferred through the soil, in a vertical
    direction, per unit of time.
    """

    name = "calc_mean_g"
    inputs = ("g1", "g2")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate mean soil heat flux (g) [MJ m-2 30min-1]

        Args:
            columns: Dict with keys of required columns for the calculation
                - g1: Soil heat flux measurement 1 [W m-2]
                - g2: Soil heat flux measurement 2 [W m-2]

        Returns:
            Polars expression computing g
        """
        g1 = columns["g1"]
        g2 = columns["g2"]

        return pl.mean_horizontal(g1, g2)


@DerivationMethod.register
class MeanSeaLevelPressure(DerivationMethod):
    """Adjust measured atmospheric pressure to its sea-level equivalent.

    Measured pressure depends on the altitude of the sensor. This converts it to the pressure that
    would be observed at sea level, using the site altitude and air temperature to account for the
    decrease in pressure with height according to the standard atmosphere model.
    """

    name = "calculate_mslp"
    inputs = ("pa", "ta")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate mean sea level pressure (mslp) [hPa]

        See US Standard Atmosphere, eq. 33a: https://ntrs.nasa.gov/api/citations/19770009539/downloads/19770009539.pdf
        See also: https://www.fao.org/4/x0490e/x0490e07.htm

        Args:
            columns: Dict with keys of required columns for the calculation.
                - pa: Atmospheric Pressure [hPa]
                - ta: Air Temperature [Celsius]

        Returns:
            Polars expression computing mslp
        """
        altitude = self.config.params["altitude"]
        pa = columns["pa"]
        ta = columns["ta"]

        return pa * (1 - ((0.0065 * altitude) / (ta + (0.0065 * altitude) + 273.15))).pow(-5.257)


@DerivationMethod.register
class PotentialEvapotranspiration30Min(DerivationMethod):
    """Calculate Potential Evapotranspiration (PET) (30 min).

    PET is the maximum amount of water that could be evapotranspirated in a given climate, given a theoretical
    continuous expanse of vegetation covering the whole ground and a continuous supply of water.
    """

    name = "calculate_pe"
    inputs = ("g", "pa", "rh", "rn", "ta", "ws")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate potential evapotranspiration (pet) [mm day-1]

        Steps taken from Penman-Monteith Evapotranspiration (FAO-56 Method): https://www.fao.org/4/x0490e/x0490e06.htm

        For hourly examples see eq53: https://www.fao.org/4/x0490e/x0490e08.htm
        "With the advent of electronic, automated weather stations, weather data are increasingly reported for
            hourly or shorter periods ... When applying the FAO Penman-Monteith equation on an hourly or shorter
            timescale, the equation and some of the procedures for calculating meteorological data should be
            adjusted for the smaller time step"

        Args:
            columns: Dict with keys of required columns for the calculation.
                - rn:  Net radiation [MJ m-2 30min-1]
                - g: Soil heat flux density [MJ m-2 30min-1]
                - ta:  Air temperature [degC]
                - rh:  Relative humidity [%]
                - ws:  Wind speed at 2m height [ms-1]
                - pa:  Atmospheric pressure [hPa]
                - wind_height: Height of wind sensor [m]

        Returns:
            Polars expression computing PET
        """
        g = columns["g"]
        pa = columns["pa"]
        rh = columns["rh"]
        rn = columns["rn"]
        ta = columns["ta"]
        ws = columns["ws"]
        wind_height = columns["wind_height"]

        es = self.saturation_vapour_pressure(ta)
        ea = self.actual_vapour_pressure(es, rh)
        vpd = es - ea  # Vapour pressure deficit
        delta = self.vapour_pressure_curve_slope(es, ta)
        lv = self.latent_heat_of_vaporization(ta)
        gamma = self.psychrometric_constant(pa, lv)
        ws_2m = self.wind_speed_height_correction(ws, wind_height)

        # Convert RN and G from W/m2 - MJ per 30 min (input provided as W/m2)
        rn_mj = rn * 0.0018
        g_mj = g * 0.0018

        # FAO constants
        # The Numerator and denominator constants for reference type and calculation time step are defined in the
        #   following references:
        #     Allen, R. G., Walter, I. A., Elliot, R. L., Howell, T.A., Itenfisu, D., Jensen, M. E.
        #         and Snyder, R. 2005. The ASCE standardized reference evapotranspiration equation. ASCE and American
        #         Society of Civil Engineers.
        #     FAO-56 Chapter 4 - Determination of ETo - "Hourly time step"
        #         https://www.fao.org/4/x0490e/x0490e08.htm

        # Numerator given as 900 for daily, and 37 for hourly. Here for 30 min data, adjusted to
        #   900 / 48 = 18.75 (rounded to 19)
        reference_crop_type_numerator = 19
        # Denominator is the same between daily and hourly in FAO-56 Chapter 4, eq. 53. Assume same is okay for 30min.
        reference_crop_type_denominator = 0.34

        # PET equation (FAO-56, adapted to 30-minute)
        radiation_term = 0.408 * delta * (rn_mj - g_mj)
        aerodynamic_term = gamma * (reference_crop_type_numerator / (ta + 273)) * ws_2m * vpd
        resistance_term = delta + gamma * (1 + (reference_crop_type_denominator * ws_2m))

        return (radiation_term + aerodynamic_term) / resistance_term

    @staticmethod
    def saturation_vapour_pressure(ta: pl.Expr) -> pl.Expr:
        """Saturation vapour pressure (es) [kPa]

        Steps taken from FAO-56 method (eq11) https://www.fao.org/4/x0490e/x0490e07.htm#calculation%20procedures

        Args:
            ta: Air temperature [degC]

        Returns:
            Polars expression to calculate es
        """
        return 0.6108 * ((17.27 * ta) / (ta + 237.3)).exp()

    @staticmethod
    def actual_vapour_pressure(es: pl.Expr, rh: pl.Expr) -> pl.Expr:
        """Actual vapour pressure (ea) [kPa]

        Steps taken from FAO-56 1-hour method (eq54) https://www.fao.org/4/x0490e/x0490e08.htm

        Args:
            es: Saturation vapour pressure [kPa]
            rh: Relative humidity [%]

        Returns:
            Polars expression to calculate ea
        """
        return es * (rh / 100)

    @staticmethod
    def vapour_pressure_curve_slope(es: pl.Expr, ta: pl.Expr) -> pl.Expr:
        """Slope of vapour pressure curve (delta) [kPa degC-1]

        Steps taken from FAO-56 method (eq13) https://www.fao.org/4/x0490e/x0490e07.htm#calculation%20procedures

        Args:
            es: Saturation vapour pressure [kPa]
            ta: Air temperature [degC]

        Returns:
            Polars expression to calculate delta
        """
        return (4098 * es) / ((ta + 237.3) ** 2)

    @staticmethod
    def latent_heat_of_vaporization(ta: pl.Expr) -> pl.Expr:
        """Latent heat of vaporization (lambda) [MJ kg-1]

        Steps taken from Harrison (1963), referenced by FAO Annex 3 https://www.fao.org/4/x0490e/x0490e0k.htm

        Harrison, L.P. 1963. "Fundamental concepts and definitions relating to humidity."
            In: Wexler, A. & Wildhack, W.A. (eds.) Humidity and Moisture. Vol. 3. Reinhold Publishing Company, New York

        Args:
            ta: Air temperature [degC]

        Returns:
            Polars expression to calculate lambda
        """
        return 2.501 - (2.361e-3 * ta)

    @staticmethod
    def psychrometric_constant(pa: pl.Expr, lv: pl.Expr) -> pl.Expr:
        """Psychrometric constant (gamma) [kPa degC-1]

        Steps taken from FAO-56 method (eq8) https://www.fao.org/4/x0490e/x0490e07.htm#psychrometric%20constant%20(g)

        Args:
            pa: Atmospheric pressure [hPa]
            lv: Latent heat of vaporization [MJ/kg]

        Returns:
            Polars expression to calculate gamma
        """
        cp = 1.013e-3  # Specific heat at constant pressure
        e_ratio = 0.622  # Ratio molecular weight of water vapour/dry air
        return (cp * (pa / 10)) / (e_ratio * lv)

    @staticmethod
    def wind_speed_height_correction(ws: pl.Expr, measured_height: pl.Expr) -> pl.Expr:
        """Convert wind speed to 2m height [ms-1]

        Steps taken from FAO-56 method (eq47) https://www.fao.org/4/x0490e/x0490e07.htm#wind%20profile%20relationship

        Args:
            ws: Wind speed measured at given height [ms-1]
            measured_height: The height the wind was measured at [m]

        Returns:
            Polars expression to calculate wind speed height correction
        """
        return ws * (4.87 / ((67.8 * measured_height) - 5.42).log())


@DerivationMethod.register
class AbsoluteHumidity(DerivationMethod):
    """Calculate absolute humidity (Q) - a measure of the actual amount of water vapor in the air."""

    name = "calculate_q"
    inputs = ("ta", "rh")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate absolute humidity Q [g m-3] (grams per cubic meter)

        Steps to derive Q:

        (1) Saturation vapour pressure [Bolton 1980, eq10: https://doi.org/10.1175/1520-0493(1980)108%3C1046:TCOEPT%3E2.0.CO;2]
            (The vapour pressure when air is fully saturated (RH = 100%))
            Psat = 6.11 exp((17.67 T) / (T + 243.5))

        (2) Actual vapour pressure at any relative humidity (RH):
            Psat = 6.11 exp((17.67 T) / (T + 243.5)) * RH/100

        (3) Apply the ideal gas law:
            PV = nRT, => n = PV/RT
            [where P = Pressure of the gas, V = Volume occupied by the gas, R = universal gas constant, T = Temperature]

            Set V=1 to get density per cubic metre
            n = P / RT


            Multiply by molecular weight of water = 18.02 grams/mol
            Q = 18.02 * P / RT

            Substitute Psat from step 2:

            Q = (18.02 * 6.11 * exp((17.67 T) / (T + 243.5)) * RH/100) / RT

        (4) Plug in the constants
            R = 8.314 J mol-1 K-1
            18.02 / 8.314 = 2.1674

            Q = 6.11 * exp((17.67 T) / (T + 243.5)) * RH * 2.1674 / T

        Args:
            columns: Dict with keys of required columns for the calculation.
            - "ta": air temperature measured in Celsius.
            - "rh": relative humidity, measured as a percentage.

        Returns:
            Polars expression computing absolute humidity, Q
        """
        ta = columns["ta"]
        rh = columns["rh"]

        q1 = ((17.67 * ta) / (ta + 243.5)).exp()
        q2 = 273.15 + ta

        return (6.112 * q1 * rh * 2.1674) / q2


@DerivationMethod.register
class SolarZenith(DerivationMethod):
    """Calculate Solar Zenith - the angle of the sun from the vertical."""

    name = "solar_zenith"
    inputs = ("swin",)

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate angle of the sun from the vertical [radians]

        Taken from https://en.wikipedia.org/wiki/Solar_zenith_angle, with some approximations.

        theta_s is solar zenith in radians:
            0 = overhead
            pi/2 = horizon
            pi = nadir

        cos(theta_s) > 0 means sun above horizon, proxy for daylight hours.

        Uses:
            Site attribute: latitude [degrees]
            NOTE: Also accesses "swin" from config params - only uses this as a placeholder to get datetime values.

        Args:
            columns: Dict with keys of required columns for the calculation.

        Returns:
            Polars expression for solar zenith angle, theta_s in radians.
        """
        latitude = self.config.params["lat"]
        swin_tf = self.config.params["swin"]
        time_name = swin_tf.time_name
        date_times = swin_tf.df[time_name]

        # hour angle [radians]: used solar noon ~ 12:00
        h = (date_times.dt.hour() + date_times.dt.minute() / 60.0 - 12.0) * (pl.lit(15).radians())

        # number of days after beginning of year
        ordinal_days = date_times.dt.ordinal_day()

        # Declination delta (radians)
        axis_tilt = 23.44  # tilt of the Earth, degrees
        delta = -pl.lit(axis_tilt).radians() * (pl.lit((360 / 365) * (ordinal_days + 10.0)).radians()).cos()

        # Convert latitude to radians
        phi = pl.lit(latitude).radians()

        # cos(theta_s)
        cos_theta_s = phi.sin() * delta.sin() + phi.cos() * delta.cos() * h.cos()

        # Return solar zenith angle in radians
        return cos_theta_s.arccos()


@DerivationMethod.register
class Albedo(DerivationMethod):
    """Calculate albedo - the ratio of reflected solar radiation to the total incoming solar radiation."""

    name = "calc_albedo"
    inputs = ("swin", "swout", "solar_zenith")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate albedo [unitless fraction]

        References:
            - https://www.fao.org/4/x0490e/x0490e07.htm
            - https://onlinelibrary.wiley.com/doi/epdf/10.1002/hyp.14048

        This calculation does not account for correction due to site being on a slope.
        This is accounted for in a correction method.

        Args:
            columns: Dict with keys of required columns for the calculation.
                - swin: Shortwave incoming radiation [W m-2]
                - swout: Shortwave outgoing radiation [W m-2]
                - solar_zenith: Solar zenith angle [radians]

        Returns:
            Polars expression for albedo. Value is null at night or where invalid, otherwise between 0 and 1.
        """
        swin = columns["swin"]
        swout = columns["swout"]
        theta_s = columns["solar_zenith"]

        # Albedo
        albedo = pl.when((swin.is_not_null()) & (swin > 0)).then(swout / swin).otherwise(None)

        # Remove nighttime values
        swin_clear = theta_s.cos()
        albedo_day = pl.when(swin_clear > 0).then(albedo).otherwise(None)

        return albedo_day.clip(0.0, 1.0)


@DerivationMethod.register
class NeutronIntensityFactor(DerivationMethod):
    """Calculate incoming neutron count intensity correction factor using a background reference station."""

    name = "calc_factor_inten"
    inputs = ("crns-count",)

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate incoming neutron count intensity correction factor.

        References:
        - "COSMOS: the Cosmic-ray Soil Moisture Observing System" https://hess.copernicus.org/articles/16/4079/2012/
        - "Intensity correction factors for a cosmic ray neutron sensor": https://zenodo.org/records/4569062
        - COSMOS-UK supporting information: https://doi.org/10.5285/2dce161d-2fab-47bb-9fe6-38e7ed1ae18a

        Uses:
            Site attributes:
                - gamma: Scaling factor to adjust for geomagnetic effects
                - ref_c0: Site annotation to account for neutron counts due to site calibration

        Args:
            columns: Dict with keys of required columns for the calculation.
                - crns-count: cosmic ray neutron sensor counts from reference station

        Returns:
            Polars expression for incoming neutron count intensity factor, [units = None]
            Values should be positive.
        """

        ref_c0 = self.config.params["ref_c0"]
        gamma = self.config.params["gamma"]
        crns_count = columns["crns-count"]

        return 1 / (((crns_count / ref_c0) - 1) * gamma + 1)


@DerivationMethod.register
class AbsoluteHumidityFactor(DerivationMethod):
    """Calculate absolute humidity correction factor to neutron counts."""

    name = "calc_factor_q"
    inputs = ("q",)

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate absolute humidity correction factor to neutron counts.

        References:
        - Rosolem, R., W. J. Shuttleworth, M. Zreda, T. E. Franz, X. Zeng, and S. A. Kurc, 2013:
            The Effect of Atmospheric Water Vapor on Neutron Count in the Cosmic-Ray Soil Moisture Observing System.
            J. Hydrometeor., 14, 1659–1671, https://doi.org/10.1175/JHM-D-12-0120.1
        - M. Andreasen, K.H. Jensen, D. Desilets, T.E. Franz, M. Zreda, H.R. Bogena, and M.C. Looms. 2017:
            Status and perspectives on the cosmic-ray neutron method for soil moisture estimation
            and other environmental science applications.
            Vadose Zone J. 16(8). https://doi.org/10.2136/vzj2017.04.0086
        - Bogena et al. (2022): https://doi.org/10.5194/essd-14-1125-2022

        Empirical structure constant = 0.0054

        Uses:
            Site attributes:
                - ref_q0: Site annotation for reference condition of absolute humidity

        Args:
            columns: Dict with keys of required columns for the calculation.
                - q: Absolute humidity [g m-3] (grams per cubic meter)

        Returns:
            Polars expression for absolute humidity factor, [units = None]
        """

        ref_q0 = self.config.params["ref_q0"]
        q = columns["q"]

        return 1 + 0.0054 * (q - ref_q0)


@DerivationMethod.register
class AtmosphericPressureFactor(DerivationMethod):
    """Calculate atmospheric pressure correction factor to neutron counts"""

    name = "calc_factor_PA"
    inputs = ("pa",)

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate atmospheric pressure correction factor to neutron counts.

        References:
        - CRNPy correction factor, Desilets & Zreda, 2003: https://doi.org/10.1016/S0012-821X(02)01088-9
        - Zreda et al. (2012) HESS https://doi.org/10.5194/hess-16-4079-2012
        - Bogena et al. (2022): https://doi.org/10.5194/essd-14-1125-2022

        Uses:
            Site attributes:
                - L: Barometric attenuation length

        Args:
            columns: Dict with keys of required columns for the calculation.
                - pa: Atmospheric pressure [hPa]

        Returns:
            Polars expression for atmospheric pressure factor, [units = None]
        """

        barometric_attenuation_length = self.config.params["l"]
        pa = columns["pa"]
        p0 = 1000  # "Arbitrary reference pressure [hPa]: Zreda et al. (2012) HESS" - set to a constant of 1000.0

        return ((pa - p0) / barometric_attenuation_length).exp()


@DerivationMethod.register
class IsSnowDay(DerivationMethod):
    """Calculate if a given day is a snow day."""

    name = "is_snow_day"
    inputs = ("albedo",)

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate if snow day. True is snow, False if not.

        Simple rules:
            - If today's albedo is None, then is_snow_day is None
            - albedo >= albedo_max_threshold is a proxy for is_snow_day = True
            - albedo < albedo_min_threshold is a proxy for is_snow_day = False

        Normally: albedo_min_threshold = 0.5, albedo_max_threshold = 0.35, see: https://doi.org/10.1002/hyp.14048

        Complex rules:
            - It is more likely that today is (not) a snow day if yesterday was (not).
            - If there was snow the previous day, i.e. the previous day's albedo >= 0.5, then
                the current day is a snow day if the albedo > 0.35.
            - If there was no snow the previous day, i.e. the previous day's albedo < 0.5, then
                the current day is a snow day if the albedo >= 0.5.

        Args:
            columns: Dict with keys of required columns for the calculation.
                - albedo: Albedo - measure of reflection with values between 0 and 1 [unitless fraction]

        Returns:
            Polars expression with boolean values.
        """
        # Use timeframe rather than columns as need to access datetimes as well as values
        albedo = columns["albedo"]
        albedo_min_threshold = self.config.params["albedo_min_threshold"]
        albedo_max_threshold = self.config.params["albedo_max_threshold"]

        albedo_prev = albedo.shift()
        snow = (
            pl.when(albedo_prev.is_null())
            .then(
                pl.when(albedo >= albedo_max_threshold)
                .then(True)
                .when(albedo < albedo_min_threshold)
                .then(False)
                .otherwise(None)
            )
            .when(albedo_prev >= albedo_max_threshold)
            .then(
                pl.when(albedo >= albedo_min_threshold)
                .then(True)
                .when(albedo < albedo_min_threshold)
                .then(False)
                .otherwise(None)
            )
            .otherwise(
                pl.when(albedo >= albedo_max_threshold)
                .then(True)
                .when(albedo < albedo_max_threshold)
                .then(False)
                .otherwise(None)
            )
        )
        return snow


@DerivationMethod.register
class CorrectCounts(DerivationMethod):
    """Calculate corrected neutron counts using correction factors.

    Bogena et al. (2022): https://doi.org/10.5194/essd-14-1125-2022:
    "Variations of the incoming cosmic-ray intensity can have many causes, from galactic and solar disturbances to
    atmospheric and meteorological influences. Most of these anomalies are expected to change proportionally in
    every domain of the neutron energy spectrum and thus can be addressed by applying a set of correction factors."
    """

    name = "correct_counts"
    inputs = ("cts_mod", "cosmosfactor_inten", "cosmosfactor_pa", "cosmosfactor_q")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate corrected neutron counts using correction factors.

        Args:
            columns: Dict with keys of required columns for the calculation.
                - cosmosfactor_inten: correction factor to neutron intensity counts.
                - cosmosfactor_pa: atmospheric pressure correction factor to neutron counts.
                - cosmosfactor_q: absolute humidity correction factor to neutron counts.

        Returns:
            Polars expression of corrected mod counts.
        """
        cts_mod = columns["cts_mod"]
        correction_factors = columns["cosmosfactor_inten"] * columns["cosmosfactor_pa"] * columns["cosmosfactor_q"]
        return cts_mod * correction_factors


@DerivationMethod.register
class VolumetricWaterContent(DerivationMethod):
    """Calculate volumetric water content (VWC) - the total volume of water present in a given volume of soil.

    Represented as a fraction of the soil volume occupied by water (the remainder of the fraction being solid
    particles and air pockets).
    """

    name = "calculate_vwc"
    inputs = ("cts_mod_corr",)

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate volumetric water content (VWC) from corrected neutron counts and site annotations.

        References:
            - "COSMOS: the COsmic-ray Soil Moisture Observing System", Zreda et al., 2012
                https://doi.org/10.5194/hess-16-4079-2012
            - Desilets et al., 2010 https://doi.org/10.1029/2009WR008726

        Config requirements:
            Site attributes:
                - ref_soc: Site attribute of reference soil organic carbon
                - ref_bulkdensity: Site attribute of reference soil bulk density
                - ref_latticewater: Site attribute of reference lattice water content
                - n0_mod: Site attribute of a calibration coefficient obtained from field calibration
                - n_max: Site attribute of maximum range for nuetron counts
                - n_min: Site attribute of minimum range for nuetron counts

        Args:
            columns: Dict with keys of required columns for the calculation.
                - cts_mod_corr: Nuetron counts (corrected for influences on cosmic-ray intensity).

        Returns:
            Polars expression for VWC.
        """
        ref_soc = self.config.params["ref_soc"]
        ref_bd = self.config.params["ref_bulkdensity"]
        ref_lw = self.config.params["ref_latticewater"]
        n0_mod = self.config.params["n0_mod"]
        n_max = self.config.params["n_max"]
        n_min = self.config.params["n_min"]

        # From Desilets et al., 2010 https://doi.org/10.1029/2009WR008726
        a0 = 0.0808
        a1 = 0.372
        a2 = 0.115

        cts_mod_corr = columns["cts_mod_corr"]
        cts_mod_corr = cts_mod_corr.clip(n_min, n_max)

        vwc = 100 * ref_bd * (a0 / ((cts_mod_corr / n0_mod) - a1) - a2 - ref_lw - ref_soc)
        return vwc.clip(0.0, 100.0)


@DerivationMethod.register
class GetSnowEstimatedCounts(DerivationMethod):
    """
    Calculate CRNS count estimates when there is snow.
    """

    name = "get_snow_estimated_counts"
    inputs = ("snow", "cts_smo_crns")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """
        Calculate CRNS count estimates when there is snow.

        This derivation reconstructs CRNS counts as if there had been no snow, because snow supresses the counts.
        During a snow event, the estimated count is set to the value of the counts just before the snow started.
        If the counts increase, so should the estimate.

        Reference: Wallbank JR, Cole SJ, Moore RJ, Anderson SR, Mellor EJ.
                Estimating snow water equivalent using cosmic-ray neutron sensors
                from the COSMOS-UK network. Hydrological Processes. 2021;35:e14048.
                https://doi.org/10.1002/hyp.14048

        Args:
            columns: Dict with keys of required columns for the calculation.
                - CTS_SMO_CRNS: smoothed nuetron counts (already corrected for influences on cosmic-ray intensity).
                - SNOW: binary values indicating if snow is present on that day. Daily values broadcasted hourly.
                - time: hourly timestamps corresponding to cts_smo values.

        Returns:
            Polars expression for estimated counts during snow periods. Null when no in snow period.
        """
        hours_in_a_day = 24

        cts_smo_crns = columns["cts_smo_crns"]
        snow = columns["snow"]
        snow_prev1 = snow.shift(hours_in_a_day)
        snow_prev2 = snow.shift(2 * hours_in_a_day)
        time = columns["time"]

        event_start = snow & (~snow_prev1) & (~snow_prev2) & (time.dt.hour() == 0)
        event_end = (~snow) & (~snow_prev1) & snow_prev2 & (time.dt.hour() == 0)
        period_boundary = (
            pl.when(event_start).then(True).when(event_end.shift(-hours_in_a_day)).then(False).otherwise(None)
        )

        # The event_end is identified when there has been two consecutive days of no snow,
        # but the actual end of the snow period is when the snow stops, i.e. the first day of no snow,
        # so the event_end is shifted back by 24 hours to denote the true end of the snow period.
        # This shift means the last 24 hours in period_boundary are not defined, and become null.
        # If there is snow in the last 24 hours, we know this is in a snow period,
        # so we fill the nulls as True in this case.
        in_snow_period = period_boundary.forward_fill().fill_null(snow)

        # Counts during snow period are initialised by the counts from the end of previous day.
        init_cts_est = pl.when(in_snow_period).then(pl.when(event_start).then(cts_smo_crns.shift(1)).forward_fill())
        cts_est = pl.when(cts_smo_crns > init_cts_est).then(cts_smo_crns).otherwise(init_cts_est)
        return cts_est

    def merge_inputs(self, config: DataProcessingMethodConfig, tf_map: dict, columns: dict) -> tuple:
        """Merge TimeFrames with different periodicities, broadcasting lower resolution to the higher resolution.

        Overrides the base `merge_inputs` because `snow` and `cts_smo_crns` have different
        periodicities (eg. daily vs. hourly), so `merge_multiple_timeframes` cannot be used directly.

        Args:
            config: Configuration parameters including input TimeFrames and output specs. Unused.
            tf_map: Mapping of input name to its TimeFrame.
            columns: Mapping of input name to its Polars column expression.

        Returns:
            Tuple of:
                - columns: The input `columns` dict, with a "time" entry added.
                - merged_tf: The TimeFrame with the lower resolution values joined onto each row.
        """
        snow_daily_tf = tf_map["snow"]
        cts_smo_tf = tf_map["cts_smo_crns"]

        if cts_smo_tf.resolution != ts.Period.of_hours(1):
            raise ValueError(f"Resolution of cts_smo_crns must be hourly. Got: {cts_smo_tf.resolution}")

        if snow_daily_tf.resolution != ts.Period.of_days(1):
            raise ValueError(f"Resolution of snow must be daily. Got: {snow_daily_tf.resolution}")

        merged_tf = cts_smo_tf.with_df(
            cts_smo_tf.df.with_columns(pl.col(cts_smo_tf.time_name).dt.date().alias("_date"))
            .join(
                snow_daily_tf.df.with_columns(pl.col(snow_daily_tf.time_name).dt.date().alias("_date")),
                on="_date",
                how="left",
            )
            .drop("_date")
        )
        columns["time"] = pl.col(cts_smo_tf.time_name)
        return columns, merged_tf


@DerivationMethod.register
class GetPrecipTipping(DerivationMethod):
    """Consolidate the tipping bucket rain gauges into one dataset."""

    name = "get_precip_tipping"
    inputs = ("precip_tipping_a", "precip_tipping_b")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Consolidate dataset PRECIP_TIPPING_A and PRECIP_TIPPING_B into a single PRECIP_TIPPING dataset
        (using the higher value where A and B are not the same)

        Args:
            columns: Dict with keys of required columns for the calculation.
                - precip_tipping_a: Precipitation from tipping bucket gauge A [mm]
                - precip_tipping_b: Precipitation from tipping bucket gauge B [mm]

        Returns:
            Polars expression consolidating tipping buckets A and B
        """
        return pl.max_horizontal(columns["precip_tipping_a"], columns["precip_tipping_b"])


@DerivationMethod.register
class VolumetricWaterContentWithSnow(VolumetricWaterContent):
    """Calculate volumetric water content with snow."""

    name = "calculate_vwc_with_snow"
    inputs = ("cts_mod_corr", "cts_est_crns")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate volumetric water content with snow.

        Reference:

        Config requirements:
            Site attributes:
                - ref_soc: Site attribute of reference soil organic carbon
                - ref_bulkdensity: Site attribute of reference soil bulk density
                - ref_latticewater: Site attribute of reference lattice water content
                - n0_mod: Site attribute of a calibration coefficient obtained from field calibration
                - n_max: Site attribute of maximum range for nuetron counts
                - n_min: Site attribute of minimum range for nuetron counts

        Args:
            columns: Dict with keys of required columns for the calculation.
            - cts_mod_corr: Nuetron counts (corrected for influences on cosmic-ray intensity).
            - cts_est_crns: estimated counts during snow periods

        Returns:
            Polars expression for VWC with snow
        """
        cts_mod_corr = columns["cts_mod_corr"]
        cts_est_crns = columns["cts_est_crns"]
        cts_mod_corr_with_snow_estimates = cts_est_crns.fill_null(cts_mod_corr)

        vwc_with_snow = super().expr({"cts_mod_corr": cts_mod_corr_with_snow_estimates})

        return vwc_with_snow


@DerivationMethod.register
class CalcFluxMeanShf(DerivationMethod):
    """Calculate mean soil heat flux from two SHF plate measurements."""

    name = "calc_flux_mean_shf"
    inputs = ("g_plate_1_1_1", "g_plate_1_1_2")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate mean soil heat flux [W m-2]

        Args:
            columns: Dict with keys of required columns for the calculation.
                - g_plate_1_1_1: Soil heat flux plate 1 [W m-2]
                - g_plate_1_1_2: Soil heat flux plate 2 [W m-2]

        Returns:
            Polars expression computing mean soil heat flux
        """
        return pl.mean_horizontal(columns["g_plate_1_1_1"], columns["g_plate_1_1_2"])


@DerivationMethod.register
class CalcFluxLeL1(DerivationMethod):
    """Calculate latent heat flux LE_L1 = Rn - SHF - H [W m-2]."""

    name = "calc_flux_le_l1"
    inputs = ("t_nr_avg", "shf", "h")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate latent heat flux LE_L1 [W m-2]

        Args:
            columns: Dict with keys of required columns for the calculation.
                - t_nr_avg: Net radiation [W m-2]
                - shf: Mean soil heat flux [W m-2]
                - h: Sensible heat flux [W m-2]

        Returns:
            Polars expression computing LE_L1
        """
        return columns["t_nr_avg"] - columns["shf"] - columns["h"]


@DerivationMethod.register
class CalcFluxEtL1(DerivationMethod):
    """Calculate evapotranspiration ET_L1 = LE_L1 / lambda / 1000 [mm 30min-1]."""

    name = "calc_flux_et_l1"
    inputs = ("le_l1", "airtemp_c")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate evapotranspiration ET_L1 [mm 30min-1]

        Args:
            columns: Dict with keys of required columns for the calculation.
                - le_l1: Latent heat flux L1 [W m-2]
                - airtemp_c: Air temperature [degC]

        Returns:
            Polars expression computing ET_L1
        """
        lv = 2.501 - 0.002361 * columns["airtemp_c"]
        return columns["le_l1"] / lv / 1000.0


@DerivationMethod.register
class CalcFluxLeL2(DerivationMethod):
    """Calculate latent heat flux LE_L2 = Rn - SHF - H_L2 [W m-2], using despiked H."""

    name = "calc_flux_le_l2"
    inputs = ("t_nr_avg", "shf", "h_l2")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate latent heat flux LE_L2 [W m-2]

        Args:
            columns: Dict with keys of required columns for the calculation.
                - t_nr_avg: Net radiation [W m-2]
                - shf: Mean soil heat flux [W m-2]
                - h_l2: Despiked sensible heat flux [W m-2]

        Returns:
            Polars expression computing LE_L2
        """
        return columns["t_nr_avg"] - columns["shf"] - columns["h_l2"]


@DerivationMethod.register
class CalcFluxEtL2(DerivationMethod):
    """Calculate evapotranspiration ET_L2 = LE_L2 / lambda / 1000 [mm 30min-1], using despiked LE."""

    name = "calc_flux_et_l2"
    inputs = ("le_l2", "airtemp_c")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate evapotranspiration ET_L2 [mm 30min-1]

        Args:
            columns: Dict with keys of required columns for the calculation.
                - le_l2: Despiked latent heat flux L2 [W m-2]
                - airtemp_c: Air temperature [degC]

        Returns:
            Polars expression computing ET_L2
        """
        lv = 2.501 - 0.002361 * columns["airtemp_c"]
        return columns["le_l2"] / lv / 1000.0


@DerivationMethod.register
class EddyProRun(DerivationMethod):
    """Run the EddyPro flux processing pipeline to produce an ObservationDataset bundle.

    Reads all required context from `config.params`, which is populated by the processor
    (`start_date`, `end_date`, `site_metadata`) and the derivation pipeline
    (`container`, `dataset_repository`). The raw .dat input is staged locally during the
    LOAD step, with its directory recorded on the raw dependency's `staged_dir`.
    """

    name = "eddypro-run"
    inputs: ClassVar[tuple] = ()

    # Should these be wired through the processing config / metadata API?
    # In practice these parameters are unlikely to change
    # H and Tau are the only flux variables that require MAD despiking,
    # R_SW_in_Avg is the standard day/night discriminator,
    # and the sensitivity/window values are established defaults from the legacy processing script.
    _DESPIKE_COLUMNS = ["H", "Tau"]
    _DESPIKE_REFERENCE_COLUMN = "R_SW_in_Avg"
    _DESPIKE_WINDOW_DAYS = 13
    _DESPIKE_LOOKBACK_DAYS = 13
    _DESPIKE_SENSITIVITY = 5.5
    _DESPIKE_ITERATIONS = 1

    def run(self, config: DataProcessingMethodConfig) -> ts.TimeFrame:
        container = config.params["container"]
        dataset_repository = config.params["dataset_repository"]
        start_date = config.params["processing_start_date"]
        end_date = config.params["processing_end_date"]
        site_metadata = config.params["site_metadata"]

        if len(container.base_dependency) != 1:
            raise ValueError(f"Expected exactly one base dependency. Got: {container.base_dependency}")
        raw_container = dataset_repository[container.base_dependency[0]]

        if raw_container.staged_dir is None:
            raise ValueError(f"Raw dependency {raw_container.ts_id} was not staged locally before the EddyPro run.")

        ancillary_containers = [
            dataset_repository[ds_id] for ds_id in container.all_dependencies() if ds_id != raw_container.ts_id
        ]

        df = EddyProPipeline(runner=EddyProRunner()).run(
            raw_data_dir=raw_container.staged_dir,
            method_config=config,
            site_metadata=site_metadata,
            start_date=start_date,
            end_date=end_date,
            ancillary_containers=ancillary_containers,
        )
        resolution = f"PT{config.params['file_duration']}M"
        data_router = config.params.get("data_router")
        if data_router is not None:
            # ObservationDataset bundles have source_bucket=None; find it from a sibling
            # processed dataset that does carry the bucket in the repository.
            processed_container = next(
                (
                    c
                    for c in dataset_repository.values()
                    if c.source_bucket is not None and c.processing_level is ProcessingLevel.PROCESSED
                ),
                None,
            )
            df = self._run_despiking(df, container, start_date, resolution, data_router, processed_container)
        else:
            logger.warning("data_router not available in EddyProRun params; despiking skipped.")

        container.time_column_name = "time"
        container.resolution = resolution
        container.periodicity = container.resolution
        container.init_timeframe(df)
        return container.data

    @staticmethod
    def _run_despiking(
        df: pl.DataFrame,
        container: TimeSeriesContainer,
        start_date: date,
        resolution: str,
        data_router: DataRouter,
        processed_container: TimeSeriesContainer | None = None,
    ) -> pl.DataFrame:
        """Load prior history and apply MAD despiking to H and Tau in the EddyPro output.

        Args:
            df: EddyPro output DataFrame for the current processing window.
            container: The EddyPro bundle container (provides site identifier).
            start_date: Start of the current processing window (used to calculate lookback range).
            resolution: ISO-8601 resolution string (e.g. "PT30M") for the hive partition path.
            data_router: Router used to load historical processed data from S3.
            processed_container: A sibling processed container providing network and source_bucket.
                ObservationDataset bundles carry network=None and source_bucket=None, so the
                caller resolves both from a sibling dataset.
        """
        site = container.source_site_identifier
        # ObservationDataset bundles don't carry network or source_bucket.
        # Borrow both from a sibling processed container — same source _build_save_tasks uses.
        network = processed_container.network if processed_container is not None else None
        source_bucket = processed_container.source_bucket if processed_container is not None else None

        history_start = datetime.combine(
            start_date - timedelta(days=EddyProRun._DESPIKE_LOOKBACK_DAYS), datetime.min.time()
        )
        history_end = datetime.combine(start_date - timedelta(days=1), datetime.min.time())

        # Derive a per-column container from the bundle so query_by_date_range can build the
        # hive path. processing_level=PROCESSED signals the resolution-keyed path.
        history_columns = [*EddyProRun._DESPIKE_COLUMNS, EddyProRun._DESPIKE_REFERENCE_COLUMN]
        history_containers = [
            replace(
                container,
                network=network,
                source_bucket=source_bucket,
                source_site_identifier=site,
                resolution=resolution,
                time_column_name="time",
                source_column=col,
                processing_level=ProcessingLevel.PROCESSED,
            )
            for col in history_columns
        ]

        try:
            history_df = data_router.query_by_date_range(
                *history_containers, start_date=history_start, end_date=history_end
            )
        except Exception:
            logger.warning(
                "Despiking skipped: failed to load history for site %s (window: %s to %s).",
                site,
                history_start,
                history_end,
            )
            return df

        if history_df is None or history_df.is_empty():
            logger.warning(
                "Despiking skipped: no history data available for site %s (window: %s to %s).",
                site,
                history_start,
                history_end,
            )
            return df

        return despike_df(
            current_df=df,
            history_df=history_df,
            columns=EddyProRun._DESPIKE_COLUMNS,
            reference_column=EddyProRun._DESPIKE_REFERENCE_COLUMN,
            window_days=EddyProRun._DESPIKE_WINDOW_DAYS,
            sensitivity=EddyProRun._DESPIKE_SENSITIVITY,
            iterations=EddyProRun._DESPIKE_ITERATIONS,
            output_names={"H": "H_despiked", "Tau": "Tau_L2"},
        )

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        raise NotImplementedError("EddyProRun overrides run() directly")
