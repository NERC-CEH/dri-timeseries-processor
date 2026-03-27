from abc import ABC, abstractmethod
from typing import ClassVar

import polars as pl
import time_stream as ts
from time_stream.operation import Operation

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.utils.enums import OperationType
from dritimeseriesprocessor.utils.polars_utils import join_time_intervals
from dritimeseriesprocessor.utils.time_stream_utils import merge_multiple_timeframes


class DerivationMethod(Operation, ABC):
    operation_type: OperationType.DERIVATION
    inputs: ClassVar[tuple]

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
        merged_tf = merge_multiple_timeframes(list(tf_map.values()))

        # Get column references for calculation
        columns = {name: pl.col(tf.metadata["column_name"]) for name, tf in tf_map.items()}

        # Build data columns for any time-bound deployment attributes (e.g. anemometer sensor height)
        for param, value in config.params.items():
            if isinstance(value, dict) and value.get(f"{param}.source", "") == "deployment":
                # Join the deployment values to the main DataFrame
                merged_tf = merged_tf.with_df(
                    join_time_intervals(value[f"{param}.value"], merged_tf.df, merged_tf.time_name, param)
                )
                # Make sure the deployment value column is available to any calculation method that needs it
                columns[param] = pl.col(param)

        # Perform the calculation (subclass-specific)
        calculation_expr = self.expr(columns).alias(config.params["output_col"])
        result_df = merged_tf.df.with_columns(calculation_expr)

        return (
            ts.TimeFrame(
                df=result_df,
                time_name=merged_tf.time_name,
                resolution=config.params["resolution"],
                periodicity=config.params["periodicity"],
            )
            .with_metadata({"column_name": config.params["output_col"]})
            .select(config.params["output_col"])
        )

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
    """Calculate net radiation

    Expects MethodConfig.params to contain:
    {
        "swin": <TimeFrame> Incoming shortwave radiation [W m-2]
        "swout": <TimeFrame> Outgoing shortwave radiation [W m-2]
        "lwin": <TimeFrame> Incoming longwave radiation [W m-2]
        "lwout": <TimeFrame> Outgoing longwave radiation [W m-2]
        "output_col": <str> Required name of output
        "resolution": <str> Expected output resolution
        "periodicity": <str> Expected output periodicity
    }
    """

    name = "calculate_rn"
    inputs = ("swin", "swout", "lwin", "lwout")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate net radiation (rn) [W m-2]

        Args:
            columns: Dict with keys of required columns for the calculation.

        Returns:
            Polars expression computing rn
        """
        return columns["swin"] - columns["swout"] + columns["lwin"] - columns["lwout"]


@DerivationMethod.register
class MeanSoilHeatFlux(DerivationMethod):
    """Calculate the mean soil heat flux (g) from inputs from multiple soil heat flux measurements."""

    name = "calc_mean_g"
    inputs = ("g1", "g2")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate mean soil heat flux (g) [MJ m-2 30min-1]

        Args:
            columns: Dict with keys of required columns for the calculation.

        Returns:
            Polars expression computing g
        """
        g1 = columns["g1"]
        g2 = columns["g2"]

        return pl.mean_horizontal(g1, g2)


@DerivationMethod.register
class MeanSeaLevelPressure(DerivationMethod):
    """Calculate the mean sea level pressure (mslp) from inputs PA and TA."""

    name = "calculate_mslp"
    inputs = ("pa", "ta")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate mean sea level pressure (mslp) [hPa]
        See US Standard Atmosphere, eq. 33a:
        https://ntrs.nasa.gov/api/citations/19770009539/downloads/19770009539.pdf
        See also: https://www.fao.org/4/x0490e/x0490e07.htm
        Args:
            columns: Dict with keys of required columns for the calculation: pa and ta.
            -pa: Atmospheric Pressure [hPa]
            -ta: Air Temperature [Celsius]

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

    Steps taken from Penman-Monteith Evapotranspiration (FAO-56 Method)
        https://www.fao.org/4/x0490e/x0490e06.htm#equation

        For hourly examples see eq53:
        https://www.fao.org/4/x0490e/x0490e08.htm

        "With the advent of electronic, automated weather stations, weather data are increasingly reported for
            hourly or shorter periods ... When applying the FAO Penman-Monteith equation on an hourly or shorter
            timescale, the equation and some of the procedures for calculating meteorological data should be
            adjusted for the smaller time step"

    Expects MethodConfig.params to contain:
    {
        "rn": <TimeFrame> Net radiation [MJ m-2 30min-1]
        "g": <TimeFrame> Soil heat flux density [MJ m-2 30min-1]
        "ta": <TimeFrame> Air temperature [degC]
        "rh": <TimeFrame> Relative humidity [%]
        "ws": <TimeFrame> Wind speed at 2m height [ms-1]
        "pa": <TimeFrame> Atmospheric pressure [hPa]
        "output_col": <str> Required name of output
        "resolution": <str> Expected output resolution
        "periodicity": <str> Expected output periodicity
    }
    """

    name = "calculate_pe"
    inputs = ("g", "pa", "rh", "rn", "ta", "ws")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate potential evapotranspiration (pet) [mm day-1]

        Args:
            columns: Dict with keys of required columns for the calculation.

        Returns:
            Polars expression computing pet
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

        # Convert RN and G from W/m2 - MJ per 30 min (if upstream provides W/m2)
        rn_mj = rn * 0.0018
        g_mj = g * 0.0018

        # FAO constants
        # Note: The Numerator and denominator constants for reference type and calculation time step are defined in the
        # following references:
        #     Allen, R. G., Walter, I. A., Elliot, R. L., Howell, T.A., Itenfisu, D., Jensen, M. E.
        #         and Snyder, R. 2005. The ASCE standardized reference evapotranspiration equation. ASCE and American
        #         Society of Civil Engineers.
        #
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
    """Calculate absolute humidity ('Q') from relative humidity and air temperature.
    Required for water vapour correction to CRS counts.
    Saturation vapour pressure, Psat (when relative humidity is 100%), is given by eq. 10 in Bolton's paper:
    https://doi.org/10.1175/1520-0493(1980)108%3C1046:TCOEPT%3E2.0.CO;2
    Relative humidity 100%:
    Psat = 6.11 exp((17.67 T)/(T + 243.5))
    Relative humidity of any value:
    Psat = 6.11 exp((17.67 T)/(T + 243.5))*rh/100
    Ideal gas formula: PV = nRT, => n = PV/(RT)
    molecular weight of water = 18.02 grams/mol
    Q = 18.02 * n
    => Q = 6.11 exp((17.67 T)/(T + 243.5))*rh*18.02/(100*R*(ta + 273.15))
         = 6.11 exp((17.67 T)/(T + 243.5))*rh*2.1674/(ta + 273.15)
    Q units: gram m^-3
    """

    name = "calculate_q"
    inputs = ("ta", "rh")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate absolute humidity Q [g m-3] (grams per cubic meter)
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
    """
    Calculate angle of the sun from the vertical [radians]
    Taken from https://en.wikipedia.org/wiki/Solar_zenith_angle, with some approximations.

    theta_s is solar zenith in radians; 0 = overhead, pi/2 = horizon, pi = nadir
    cos(theta_s) > 0 means sun above horizon, proxy for daylight hours.
    """

    name = "solar_zenith"
    inputs = ("swin",)

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """
        Calculate angle of the sun from the vertical [radians]
        Uses: site attribute LAT [degrees]

        Args:
            columns: Dict with keys of required columns for the calculation.
            - "swin": Shortwave incoming radiation [W m-2] (Not used, datetimes only)

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
    """
    Calculate albedo from incoming and outgoing short wave radiation.
    See reference: https://www.fao.org/4/x0490e/x0490e07.htm
    See: https://onlinelibrary.wiley.com/doi/epdf/10.1002/hyp.14048
    This calculation does not account for correction due to site being on a slope.
    This is accounted for in a correction method.
    """

    name = "calc_albedo"
    inputs = ("swin", "swout", "solar_zenith")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate albedo [unitless fraction]
        Args:
            columns: Dict with keys of required columns for the calculation.
            - "swin": Shortwave incoming radiation [W m-2]
            - "swout": Shortwave outgoing radiation [W m-2]
            - "solar_zenith": Solar zenith angle [radians]
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
class AbsoluteHumidityFactor(DerivationMethod):
    """Calculate correction factor for absolute humidity Q.
    This factor is used to correct neutron counts.
    Emperical structure contant: 0.0054.
    See references:

    1.  Rosolem, R., W. J. Shuttleworth, M. Zreda, T. E. Franz, X. Zeng, and S. A. Kurc, 2013:
        The Effect of Atmospheric Water Vapor on Neutron Count in the Cosmic-Ray Soil Moisture Observing System.
        J. Hydrometeor., 14, 1659–1671, https://doi.org/10.1175/JHM-D-12-0120.1

    2.  M. Andreasen, K.H. Jensen, D. Desilets, T.E. Franz, M. Zreda, H.R. Bogena, and M.C. Looms. 2017.
        Status and perspectives on the cosmic-ray neutron method for soil moisture estimation
        and other environmental science applications.
        Vadose Zone J. 16(8). doi:10.2136/vzj2017.04.0086

    Uses processed data from absolute humidity Q and REF_Q0.
    REF_Q0 is a site annotation.
    """

    name = "calc_factor_Q"
    inputs = "q"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate absolute humidity correction factor to neutron counts.
        Args:
            columns: Dict with keys of required columns for the calculation.
            - "q":  Q [g m-3] (grams per cubic meter)

        Returns:
            Polars expression for absolute humidity factor, [units = None]
        """

        ref_q0 = self.config.params["REF_Q0"]
        q = columns["q"]

        return 1 + 0.0054 * (q - ref_q0)


@DerivationMethod.register
class AtmosphericPressureFactor(DerivationMethod):
    """Calculate correction factor for atmospheric pressure, PA.
    This factor is used to correct neutron counts.
    See CRNPy correction factor, Desilets & Zreda, 2003: https://doi.org/10.1016/S0012-821X(02)01088-9
    Uses processed data from atmospheric pressure.
    Barometric attenuation length, L is a site annotation.
    P0: "Arbitrary reference pressure [hPa]: Zreda et al. (2012) HESS" - set to a constant of 1000.0
    See: https://doi.org/10.5194/hess-16-4079-2012
    """

    name = "calc_factor_PA"
    inputs = ("pa",)

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate atmospheric pressure correction factor to neutron counts.
        Args:
            columns: Dict with keys of required columns for the calculation.
            - "pa":  PA [hPa]

        Returns:
            Polars expression for atmospheric pressure factor, [units = None]
        """

        barometric_attenuation_length = self.config.params["L"]
        pa = columns["pa"]
        p0 = 1000

        return ((pa - p0) / barometric_attenuation_length).exp()


@DerivationMethod.register
class IsSnowDay(DerivationMethod):
    """Calculate if snow day. True is snow, False if not.
    If today's albedo is None, then is_snow_day is None.
    albedo >= 0.5 is a proxy for is_snow_day = True
    albedo < 0.35 is a proxy for is_snow_day = False

    It is more likely that today is (not) a snow day if yesterday was (not).

    If there was snow the previous day, i.e. the previous day's albedo >= 0.5, then
    the current day is a snow day if the albedo > 0.35.

    If there was no snow the previous day, i.e. the previous day's albedo < 0.5, then
    the current day is a snow day if the albedo >= 0.5.
    """

    name = "is_snow_day"
    inputs = ("albedo",)

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        """Calculate if snow day. True is snow, False if not.
        Args:
            columns: Dict with keys of required columns for the calculation.
            - albedo: ALBEDO, measure of reflection with values between 0 and 1 [unitless fraction]

        Returns: Polars expression with boolean values.
        """
        # Use timeframe rather than columns as need to access datetimes as well as values
        albedo_tf = self.config.params["albedo"]
        albedo_tf = albedo_tf.with_df(albedo_tf.df.rename({"albedo": "ALBEDO"}).sort(albedo_tf.time_name))

        df = albedo_tf.df.with_columns([pl.col("ALBEDO").shift().alias("ALBEDO_prev")]).with_columns(
            [
                pl.when(pl.col("ALBEDO_prev").is_null())
                .then(
                    pl.when(pl.col("ALBEDO") >= 0.5)
                    .then(True)
                    .when(pl.col("ALBEDO") < 0.35)
                    .then(False)
                    .otherwise(None)
                )
                .when(pl.col("ALBEDO_prev") >= 0.5)
                .then(
                    pl.when(pl.col("ALBEDO") >= 0.35)
                    .then(True)
                    .when(pl.col("ALBEDO") < 0.35)
                    .then(False)
                    .otherwise(None)
                )
                .otherwise(
                    pl.when(pl.col("ALBEDO") >= 0.5).then(True).when(pl.col("ALBEDO") < 0.5).then(False).otherwise(None)
                )
                .alias("is_snow_day")
            ]
        )

        return df["is_snow_day"]
