import math
from typing import Optional, Type, Union

import polars as pl
from time_stream import Period, TimeSeries, aggregation  # noqa: F401

from dritimeseriesprocessor.deriving.calculation import Calculation


class PotentialEvapotranspiration30Min(Calculation):
    def __init__(
        self,
        rn: Union[str, pl.Expr],
        g1: Union[str, pl.Expr],
        g2: Union[str, pl.Expr],
        ta: Union[str, pl.Expr],
        rh: Union[str, pl.Expr],
        ws: Union[str, pl.Expr],
        pa: Union[str, pl.Expr],
        column_name: str = None,
    ):
        """Calculate potential evaporation from measured variables at 30min time resolution.

        Steps taken from Penman-Monteith Evapotranspiration (FAO-56 Method)
        https://www.fao.org/4/x0490e/x0490e06.htm#equation

        For hourly examples see eq53:
        https://www.fao.org/4/x0490e/x0490e08.htm

        "With the advent of electronic, automated weather stations, weather data are increasingly reported for
            hourly or shorter periods ... When applying the FAO Penman-Monteith equation on an hourly or shorter
            timescale, the equation and some of the procedures for calculating meteorological data should be
            adjusted for the smaller time step"

        Args:
            rn: Net radiation [MJ m-2 30min-1]
            g1: Soil heat flux density [MJ m-2 30min-1]
            g2: Soil heat flux density [MJ m-2 30min-1]
            ta: Air temperature [degC]
            rh: Relative humidity [%]
            ws: Wind speed at 2m height [ms-1]
            pa: Atmospheric pressure [kPa]

        Returns:
            Potential evapotranspiration [mm 30min-1]
        """
        super().__init__("Potential Evapotranspiration", column_name, "mm")
        (self._rn, self._g1, self._g2, self._ta, self._rh, self._ws, self._pa) = self._columns_to_expressions(
            rn, g1, g2, ta, rh, ws, pa
        )

        # Define dependencies
        self._g = pl.mean_horizontal(self._g1, self._g2)
        self._es = SaturationVapourPressure(self._ta)
        self._ea = ActualVapourPressureFao56Eq54(self._rh, self._ta)
        self._gamma = PsychrometricConstant(self._pa, self._ta)
        self._delta = VapourPressureCurveSlope(self._ta)

    @property
    def default_column_name(self) -> str:
        return "pet"

    def expr(self) -> pl.Expr:
        """The Polars expression representation of this Calculation

        Note: The Numerator and denominator constants for reference type and calculation time step are defined in the
        following references:
            Allen, R. G., Walter, I. A., Elliot, R. L., Howell, T.A., Itenfisu, D., Jensen, M. E.
                and Snyder, R. 2005. The ASCE standardized reference evapotranspiration equation. ASCE and American
                Societyof Civil Engineers.

            FAO-56 Chapter 4 - Determination of ETo - "Hourly time step"
                https://www.fao.org/4/x0490e/x0490e08.htm
        """
        # Numerator given as 900 for daily, and 37 for hourly. Here for 30 min data, adjusted to
        #   900 / 48 = 18.75 (rounded to 19)
        reference_crop_type_numerator = 19
        # Denominator is the same between daily and hourly in FAO-56 Chapter 4, eq. 53. Assume same is okay for 30min.
        reference_crop_type_denominator = 0.34

        vapour_pressure_deficit = self._es.expr() - self._ea.expr()
        radiation_term = 0.408 * self._delta.expr() * (self._rn - self._g)
        aerodynamic_term = (
            self._gamma.expr() * (reference_crop_type_numerator / (self._ta + 273)) * self._ws * vapour_pressure_deficit
        )
        resistance_term = self._delta.expr() + (self._gamma.expr() * (1 + (reference_crop_type_denominator * self._ws)))

        pet = (radiation_term + aerodynamic_term) / resistance_term
        return pet


class SaturationVapourPressure(Calculation):
    def __init__(self, ta: Union[str, pl.Expr], column_name: str = None):
        """Calculate saturation vapour pressure from air temperature.

        Steps taken from FAO-56 method (eq11) https://www.fao.org/4/x0490e/x0490e07.htm#calculation%20procedures

        Args:
            ta: Air temperature [degC]

        Returns:
            Saturation vapour pressure (es) [kPa]
        """
        super().__init__("Saturation vapour pressure", column_name, "kPa")
        self._ta = self._columns_to_expressions(ta)

    @property
    def default_column_name(self) -> str:
        return "es"

    def expr(self) -> pl.Expr:
        es = 0.6108 * ((17.27 * self._ta) / (self._ta + 237.3)).exp()
        return es


class PsychrometricConstant(Calculation):
    def __init__(self, pa: Union[str, pl.Expr], ta: Union[str, pl.Expr], column_name: str = None):
        """Calculate psychrometric constant.

        Steps taken from FAO-56 method (eq8) https://www.fao.org/4/x0490e/x0490e07.htm#psychrometric%20constant%20(g)

        Args:
            pa: Atmospheric pressure [kPa]
            ta: Air temperature [degC]

        Returns:
            Psychrometric constant (gamma) [kPa degC-1]
        """
        super().__init__("Psychrometric Constant", column_name, "kPa degC-1")
        self._pa, self._ta = self._columns_to_expressions(pa, ta)

        # Define dependencies
        self._lv = LatentHeatOfVaporization(self._ta)

    @property
    def default_column_name(self) -> str:
        return "gamma"

    def expr(self) -> pl.Expr:
        cp = 1.013e-3  # Specific heat at constant pressure
        e = 0.622  # Ratio molecular weight of water vapour/dry air
        gamma = (cp * self._pa) / (e * self._lv.expr())
        return gamma


class VapourPressureCurveSlope(Calculation):
    def __init__(self, ta: Union[str, pl.Expr], column_name: str = None):
        """Calculate slope of vapour pressure curve from measured variables.

        Steps taken from FAO-56 method (eq13) https://www.fao.org/4/x0490e/x0490e07.htm#calculation%20procedures

        Args:
            ta: Air temperature [degC]

        Returns:
            Slope of vapour pressure curve (delta) [kPa degC-1]
        """
        super().__init__("Slope of Vapour Pressure Curve", column_name, "kPa degC-1")
        self._ta = self._columns_to_expressions(ta)

        # Define dependencies
        self._es = SaturationVapourPressure(self._ta)

    @property
    def default_column_name(self) -> str:
        return "delta"

    def expr(self) -> pl.Expr:
        delta = (4098 * self._es.expr()) / ((self._ta + 237.3) ** 2)
        return delta


class ActualVapourPressureFao56Eq54(Calculation):
    def __init__(self, rh: Union[str, pl.Expr], ta: Union[str, pl.Expr], column_name: str = None):
        """Calculate Actual vapour pressure from relative humidity.

        Steps taken from FAO-56 1-hour method (eq54) https://www.fao.org/4/x0490e/x0490e08.htm

        Args:
            rh: Relative humidity [%]
            ta: Air temperature [degC]

        Returns:
            Actual vapour pressure (ea) [kPa]
        """
        super().__init__("Actual Vapour Pressure", column_name, "kPa")
        self._rh, self._ta = self._columns_to_expressions(rh, ta)

        # Define dependencies
        self._es = SaturationVapourPressure(self._ta)

    @property
    def default_column_name(self) -> str:
        return "ea"

    def expr(self) -> pl.Expr:
        ea = self._es.expr() * (self._rh / 100)
        return ea


class WindSpeedHeightCorrection(Calculation):
    def __init__(self, ws: Union[str, pl.Expr], measured_height: Union[int, float], column_name: str = None):
        """Correct wind speed to the standard 2m height.

        Steps taken from FAO-56 method (eq47) https://www.fao.org/4/x0490e/x0490e07.htm#wind%20profile%20relationship

        Args:
            ws: Wind speed measured at given height [ms-1]
            measured_height: The height the wind was measured at

        Returns:
            Wind speed corrected to 2m height [ms-1]
        """
        super().__init__("Wind Speed 2m", column_name, "ms-1")
        self._ws = self._columns_to_expressions(ws)
        self._measured_height = measured_height

    @property
    def default_column_name(self) -> str:
        return "ws_2m"

    def expr(self) -> pl.Expr:
        ws_corrected = self._ws * (4.87 / math.log((67.8 * self._measured_height) - 5.42))
        return ws_corrected


class LatentHeatOfVaporization(Calculation):
    def __init__(self, ta: Union[str, pl.Expr], column_name: str = None):
        """Calculate latent heat of vaporization

        Steps taken from Harrison (1963), referenced by FAO Annex 3 https://www.fao.org/4/x0490e/x0490e0k.htm

        Harrison, L.P. 1963. "Fundamental concepts and definitions relating to humidity."
            In: Wexler, A. & Wildhack, W.A. (eds.) Humidity and Moisture. Vol. 3. Reinhold Publishing Company, New York

        Args:
            ta: Air temperature [degC]

        Returns:
            Latent heat of vaporization (lv) [MJ kg-1]
        """
        super().__init__("Latent Heat of Vaporization", column_name, "MJ kg-1")
        self._ta = self._columns_to_expressions(ta)

    @property
    def default_column_name(self) -> str:
        return "lv"

    def expr(self) -> pl.Expr:
        lv = 2.501 - 2.361e-3 * self._ta
        return lv


class NetRadiation(Calculation):
    def __init__(
        self,
        swin: Union[str, pl.Expr],
        swout: Union[str, pl.Expr],
        lwin: Union[str, pl.Expr],
        lwout: Union[str, pl.Expr],
        column_name: str = None,
    ):
        """Calculate net radiation.

        Args:
            swin: Incoming shortwave radiation [W m-2]
            swout: Outgoing shortwave radiation [W m-2]
            lwin: Incoming longwave radiation [W m-2]
            lwout: Outgoing longwave radiation [W m-2]

        Returns:
            Net radiation [W m-2]
        """
        super().__init__("Net radiation", column_name, "W m-2")
        self._swin, self._swout, self._lwin, self._lwout = self._columns_to_expressions(swin, swout, lwin, lwout)

    @property
    def default_column_name(self) -> str:
        return "rn"

    def expr(self) -> pl.Expr:
        rn = self._swin - self._swout + self._lwin - self._lwout
        return rn


class DailyTotalRadiation(Calculation):
    def __init__(self, column_name: str = None, **kwargs):
        """
        Aggregate sub daily radiation, measured in W m-2, into total energy for the day, MJ m-2 day-1
        Note, the sub daily values must be evenly spaced in time and each value must represent the average radiation
        over its interval (not instantaneous).

        The column to use to calculate the daily total radiation should be provided as a kwarg. This is to allow
        flexibility in the expected input column structure.

        Returns:
            Daily total radiation [MJ m-2 day-1]

        """
        super().__init__("Daily total radiation", column_name, "MJ m-2 day-1")

        # In order to support data from multiple possible column sources
        _, rad = kwargs.popitem()
        self._rad = self._columns_to_expressions(rad)

    @property
    def default_column_name(self) -> str:
        return "radiation"

    @property
    def preprocess_aggregation_method(self) -> str:
        return "mean_sum"

    @property
    def preprocess_aggregation_period(self) -> str:
        return Period.of_iso_duration("P1D")

    def expr(self) -> pl.Expr:
        daily_radiation = self._rad * 0.0864
        return daily_radiation


class DailyPotentialEvaporation(Calculation):
    def __init__(
        self,
        pe: Union[str, pl.Expr],
        column_name: str = None,
    ):
        """Calculate daily potential evaporation.

        Args:
            pe: potential evaporation at 30min resolution [mm 30min-l]

        Returns:
            Daily potential evaporation [mm day-l]

        """
        super().__init__("Daily potential evaporation", column_name, "mm day-l")

        self._pe_30min = self._columns_to_expressions(pe)

    @property
    def default_column_name(self) -> str:
        return "pe"

    @property
    def postprocess_aggregation_method(self) -> str:
        return "mean_sum"

    @property
    def postprocess_aggregation_period(self) -> str:
        return Period.of_iso_duration("P1D")

    def expr(self) -> pl.Expr:
        filtered_pe = pl.when(self._pe_30min < 0).then(0).otherwise(self._pe_30min)
        return filtered_pe


def derive(
    ts: TimeSeries,
    calc: Type[Calculation],
    column_name: Optional[str] = None,
    units_meta_name: str = "units",
    include_dependencies: bool = False,
    resolution: str = None,
    periodicity: str = None,
    **kwargs,
) -> TimeSeries:
    """Derive a new TimeSeries from a given Calculation.

    Args:
        ts: Input TimeSeries object.
        calc: The Calculation class to be instantiated and used.
        column_name: The name for the derived column.  If not provided, uses the default defined within the class.
        units_meta_name: Metadata key name for units. Defaults to "units".
        include_dependencies: Whether to include calculation dependencies in the final Time Series data.
        resolution: The resolution to use for the output TimeSeries object. This is useful to provide if the derivation
            calculation involves aggregation (e.g. calculating potential evaporation at 1 day resolution from 30 minute
            data)
        periodicity: The periodicity to use for the output TimeSeries object. This is useful to provide if the
            derivation calculation involves aggregation.
        **kwargs: Arguments required for the calculation

    Returns:
        TimeSeries: The resulting TimeSeries after applying the calculation.
    """
    calc_instance = calc(**kwargs, column_name=column_name)

    # Where aggregation is required there is a possibility that the data to be aggregated has the same
    # source column name as the output aggregated data. Check if the calculation instance has a default
    # column name matching the timeseries source column name and enable the `allow_override` flag if required.
    allow_override = True
    if calc_instance.default_column_name in ts.df.columns:
        allow_override = False

    ts = calc_instance.evaluate(
        ts, include_dependency_columns=include_dependencies, allow_override=allow_override
    )

    # TODO: this could use some work.
    # new_column_metadata = (
    #     {col: ts.columns[col].metadata() for col in ts.columns}
    #     | {calc_instance.column_name: {units_meta_name: calc_instance.units}}
    #     | {dep_calc.column_name: {units_meta_name: dep_calc.units} for dep_calc in calc_instance.dependencies}
    # )

    # new_ts = TimeSeries(
    #     df=new_df,
    #     time_name=ts.time_name,
    #     resolution=resolution if not None else ts.resolution,
    #     periodicity=periodicity if not None else ts.periodicity,
    #     supplementary_columns=ts.supplementary_columns,
    #     flag_columns=ts.flag_columns,
    #     flag_systems=ts.flag_systems,
    #     column_metadata=new_column_metadata,
    #     metadata=ts.metadata(),
    # )

    return ts
