import logging
from abc import ABC, abstractmethod
from typing import Iterable, Literal

import polars as pl
import time_stream as ts
from hydrometlib import cosmos, evapotranspiration, flux, meteorology
from isoperiod import Period

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.operation_method import GenerativeMethod
from dritimeseriesprocessor.utils.enums import ConfigurationType
from dritimeseriesprocessor.utils.polars_utils import join_time_intervals
from dritimeseriesprocessor.utils.time_stream_utils import merge_multiple_timeframes

logger = logging.getLogger(__name__)


class DerivationMethod(GenerativeMethod, ABC):
    operation_type = ConfigurationType.DERIVATION
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
        # NOTE: This collects *all* timeframe objects rather than named timeframe objects required by the
        #   method (as was done previously - i.e ``{name: config.params[name] for name in self.inputs}``).
        #   This is to handle scenarios where certain timeseries use derivation methods with different input column
        #   names - e.g. the standard CRNS vs. SNOWFOX sensor that both use the CorrectCounts / GetSnowEstimatedCounts
        #   methods.
        tf_map = {key: val for key, val in config.params.items() if isinstance(val, ts.TimeFrame)}

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
        and `join_annotation_attributes` themselves if they also need time-bound attribute columns joined in.

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
        columns, merged_tf = self.join_deployment_attributes(config, columns, merged_tf)
        columns, merged_tf = self.join_annotation_attributes(config, columns, merged_tf)
        return columns, merged_tf

    @staticmethod
    def join_deployment_attributes(config: DataProcessingMethodConfig, columns: dict, merged_tf: ts.TimeFrame) -> tuple:
        """Join any time-bound deployment attribute columns (e.g. anemometer sensor height) onto a TimeFrame.

        A deployment attribute is metadata about something deployed at a site (e.g. a sensor), which can be
        replaced or moved over time.

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

    @staticmethod
    def join_annotation_attributes(config: DataProcessingMethodConfig, columns: dict, merged_tf: ts.TimeFrame) -> tuple:
        """Join any time-variable site annotation columns (e.g. soil properties) onto a TimeFrame.

        A site annotation describes the site itself and can vary over time (e.g. soil saturation, wilting point,
        field capacity).

        Args:
            config: Configuration parameters including input TimeFrames and output specs
            columns: Mapping of input name to its Polars column expression
            merged_tf: The already-merged TimeFrame that annotation attribute columns should be joined onto

        Returns:
            Tuple of:
                - columns: The input `columns` dict, with an added entry for each time-variable
                  annotation found in `config.params`
                - merged_tf: The input `merged_tf`, with any time-variable annotation columns joined in
        """
        for param, value in config.params.items():
            if isinstance(value, list) and value and isinstance(value[0], tuple):
                # Join the annotation's dated values to the main DataFrame
                merged_tf = merged_tf.with_df(join_time_intervals(value, merged_tf.df, merged_tf.time_name, param))
                # Make sure the annotation value column is available to any calculation method that needs it
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
    """Calculate net radiation - the difference between the downward and upward total radiation.

    See `hydrometlib.meteorology.net_radiation` for the science.
    """

    name = "calculate_rn"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return meteorology.net_radiation(
            swin=columns["swin"], swout=columns["swout"], lwin=columns["lwin"], lwout=columns["lwout"]
        )


@DerivationMethod.register
class MeanSoilHeatFlux(DerivationMethod):
    """Calculate the mean soil heat flux from inputs from multiple soil heat flux measurements.

    See `hydrometlib.meteorology.mean_soil_heat_flux` for the science.
    """

    name = "calc_mean_g"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return meteorology.mean_soil_heat_flux(g1=columns["g1"], g2=columns["g2"])


@DerivationMethod.register
class MeanSeaLevelPressure(DerivationMethod):
    """Adjust measured atmospheric pressure to its sea-level equivalent.

    See `hydrometlib.meteorology.mean_sea_level_pressure` for the science.
    """

    name = "calculate_mslp"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return meteorology.mean_sea_level_pressure(
            pa=columns["pa"], ta=columns["ta"], altitude=self.config.params["altitude"]
        )


@DerivationMethod.register
class PotentialEvapotranspiration30Min(DerivationMethod):
    """Calculate Potential Evapotranspiration (PET) (30 min).

    See `hydrometlib.evapotranspiration.potential_evapotranspiration_30min` for the science.
    """

    name = "calculate_pe"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return evapotranspiration.potential_evapotranspiration_30min(
            rn=columns["rn"],
            g=columns["g"],
            ta=columns["ta"],
            rh=columns["rh"],
            ws=columns["ws"],
            pa=columns["pa"],
            wind_height=columns["wind_height"],
        )


@DerivationMethod.register
class AbsoluteHumidity(DerivationMethod):
    """Calculate absolute humidity (Q) - a measure of the actual amount of water vapor in the air.

    See `hydrometlib.meteorology.absolute_humidity` for the science.
    """

    name = "calculate_q"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return meteorology.absolute_humidity(ta=columns["ta"], rh=columns["rh"])


@DerivationMethod.register
class SolarZenith(DerivationMethod):
    """Calculate Solar Zenith - the angle of the sun from the vertical.

    See `hydrometlib.meteorology.solar_zenith` for the science.

    Uses:
        Site attribute: latitude [degrees]
        NOTE: Also accesses "swin" from config params - only uses this as a placeholder to get datetime values.
    """

    name = "solar_zenith"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        swin_tf = self._get_swin_tf()
        return meteorology.solar_zenith(time=pl.col(swin_tf.time_name), latitude=self.config.params["lat"])

    def _get_swin_tf(self) -> ts.TimeFrame:
        """
        Different networks may use the same method, but have different column names.
        The allowed column names for this method are listed in possible_keys below


        Raises:
            KeyError: If both possible_keys are found, it is not clear which should be used.
                      If no possible_keys are found, a new key may need to be added.

        Returns:
            ts.TimeFrame: TimeFrame of shortwave ingoing radiation
        """
        possible_keys = {"swin", "r_sw_in_avg"}
        found_keys = possible_keys & self.config.params.keys()

        if len(found_keys) != 1:
            raise KeyError(f"Expected exactly one of {possible_keys}, found {found_keys}")

        return self.config.params[found_keys.pop()]


@DerivationMethod.register
class Albedo(DerivationMethod):
    """Calculate albedo - the ratio of reflected solar radiation to the total incoming solar radiation.

    See `hydrometlib.meteorology.albedo` for the science.
    """

    name = "calc_albedo"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        swin, swout = self._get_sw_column_names(columns)
        return meteorology.albedo(swin=swin, swout=swout, solar_zenith_angle=columns["solar_zenith"])

    def _get_sw_column_names(self, columns: dict[str, pl.Expr]) -> tuple[pl.Expr, pl.Expr]:
        """
        Different networks may use the same method, but have different column names.
        The allowed column names for this method are listed in possible_keys below

        Raises:
            KeyError: If both possible_keys are found, it is not clear which should be used.
                      If no possible_keys are found, a new key may need to be added.

        Returns:
            tuple[pl.Expr,pl.Expr]: expressions for ingoing and outgoing short wave radiation.
        """
        possible_keys_in = {"swin", "r_sw_in_avg"}
        possible_keys_out = {"swout", "r_sw_out_avg"}
        found_keys_in = possible_keys_in & columns.keys()
        found_keys_out = possible_keys_out & columns.keys()

        if len(found_keys_in) != 1 and len(found_keys_out) != 1:
            raise KeyError(
                f"Expected exactly one of {possible_keys_in} and one of{possible_keys_out}, found {found_keys_out}"
            )

        return columns[found_keys_in.pop()], columns[found_keys_out.pop()]


@DerivationMethod.register
class NeutronIntensityFactor(DerivationMethod):
    """Calculate incoming neutron count intensity correction factor using a background reference station.

    See `hydrometlib.cosmos.neutron_intensity_factor` for the science.
    """

    name = "calc_factor_inten"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return cosmos.neutron_intensity_factor(
            crns_count=columns["crns-count"],
            ref_c0=self.config.params["ref_c0"],
            gamma=self.config.params["gamma"],
        )


@DerivationMethod.register
class AbsoluteHumidityFactor(DerivationMethod):
    """Calculate absolute humidity correction factor to neutron counts.

    See `hydrometlib.cosmos.absolute_humidity_factor` for the science.
    """

    name = "calc_factor_q"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return cosmos.absolute_humidity_factor(q=columns["q"], ref_q0=self.config.params["ref_q0"])


@DerivationMethod.register
class AtmosphericPressureFactor(DerivationMethod):
    """Calculate atmospheric pressure correction factor to neutron counts.

    See `hydrometlib.cosmos.atmospheric_pressure_factor` for the science.
    """

    name = "calc_factor_PA"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return cosmos.atmospheric_pressure_factor(
            pa=columns["pa"], barometric_attenuation_length=self.config.params["l"]
        )


@DerivationMethod.register
class IsSnowDay(DerivationMethod):
    """Calculate if a given day is a snow day.

    See `hydrometlib.meteorology.is_snow_day` for the science.
    """

    name = "is_snow_day"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return meteorology.is_snow_day(
            albedo_expr=columns["albedo"],
            albedo_min_threshold=self.config.params["albedo_min_threshold"],
            albedo_max_threshold=self.config.params["albedo_max_threshold"],
        )


@DerivationMethod.register
class CorrectCounts(DerivationMethod):
    """Calculate corrected neutron counts using correction factors.

    See `hydrometlib.cosmos.correct_counts` for the science.
    """

    name = "correct_counts"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        cts_mod = columns[_get_crns_column(columns.keys(), "cts_mod")]
        return cosmos.correct_counts(
            cts_mod=cts_mod,
            factor_inten=columns["cosmosfactor_inten"],
            factor_pa=columns["cosmosfactor_pa"],
            factor_q=columns["cosmosfactor_q"],
        )


@DerivationMethod.register
class VolumetricWaterContent(DerivationMethod):
    """Calculate volumetric water content (VWC) - the total volume of water present in a given volume of soil.

    See `hydrometlib.cosmos.volumetric_water_content` for the science.
    """

    name = "calculate_vwc"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return cosmos.volumetric_water_content(
            cts_mod_corr=columns["cts_mod_corr"],
            ref_soc=self.config.params["ref_soc"],
            ref_bulkdensity=self.config.params["ref_bulkdensity"],
            ref_latticewater=self.config.params["ref_latticewater"],
            n0_mod=self.config.params["n0_mod"],
            n_min=self.config.params["n_min"],
            n_max=self.config.params["n_max"],
        )


@DerivationMethod.register
class GetSnowEstimatedCounts(DerivationMethod):
    """Calculate CRNS count estimates when there is snow.

    See `hydrometlib.cosmos.snow_estimated_counts` for the science.
    """

    name = "get_snow_estimated_counts"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        cts_smo_crns = columns[_get_crns_column(columns.keys(), "cts_smo")]
        return cosmos.snow_estimated_counts(cts_smo=cts_smo_crns, snow=columns["snow"], time=columns["time"])

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
        cts_smo_tf = tf_map[_get_crns_column(columns.keys(), "cts_smo")]

        if cts_smo_tf.resolution != Period.of_hours(1):
            raise ValueError(f"Resolution of cts_smo_crns must be hourly. Got: {cts_smo_tf.resolution}")

        if snow_daily_tf.resolution != Period.of_days(1):
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
    """Consolidate the tipping bucket rain gauges into one dataset.

    Takes the larger of the two gauge readings at each time step. This is specific to the networks that run two
    tipping bucket gauges side by side, so it is not part of `hydrometlib`.
    """

    name = "get_precip_tipping"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return pl.max_horizontal(columns["precip_tipping_a"], columns["precip_tipping_b"])


@DerivationMethod.register
class VolumetricWaterContentWithSnow(VolumetricWaterContent):
    """Calculate volumetric water content with snow.

    Uses CTS_EST_CRNS, the estimated counts during snow periods, to calculate VWC when there is snow.
    See `hydrometlib.cosmos.volumetric_water_content` for the science.

    Reference: Wallbank JR, Cole SJ, Moore RJ, Anderson SR, Mellor EJ.
                    Estimating snow water equivalent using cosmic-ray neutron sensors
                    from the COSMOS-UK network. Hydrological Processes. 2021;35:e14048.
                    https://doi.org/10.1002/hyp.14048
    """

    name = "calculate_vwc_with_snow"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        cts_mod_corr = columns["cts_mod_corr"]
        cts_est_crns = columns["cts_est_crns"]
        cts_mod_corr_with_snow_estimates = cts_est_crns.fill_null(cts_mod_corr)

        return super().expr({"cts_mod_corr": cts_mod_corr_with_snow_estimates})


@DerivationMethod.register
class SnowWaterEquivalence(DerivationMethod):
    """Calculate snow water equivalence (SWE) for an above ground COSMOS sensor.

    See `hydrometlib.cosmos.snow_water_equivalence` for the science.
    """

    name = "calculate_crns_swe"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return cosmos.snow_water_equivalence(
            cts_smo=columns["cts_smo_crns"], cts_est=columns["cts_est_crns"], n0_mod=self.config.params["n0_mod"]
        )


@DerivationMethod.register
class SnowWaterEquivalenceSnowfox(DerivationMethod):
    """Calculate snow water equivalence (SWE) for a below ground (SnowFox) COSMOS sensor.

    See `hydrometlib.cosmos.snow_water_equivalence_snowfox` for the science.
    """

    name = "calculate_snowfox_swe"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return cosmos.snow_water_equivalence_snowfox(
            cts_smo=columns["cts_smo_snowfox"], cts_est=columns["cts_est_snowfox"]
        )


@DerivationMethod.register
class SigmaSnowWaterEquivalence(DerivationMethod):
    """Calculate **uncertainty** in a snow water equivalence (SWE) calculation for the above ground COSMOS sensor.

    See `hydrometlib.cosmos.sigma_snow_water_equivalence` for the science.
    """

    name = "calculate_crns_sigma_swe"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return cosmos.sigma_snow_water_equivalence(
            cts_smo=columns["cts_smo_crns"], cts_est=columns["cts_est_crns"], n0_mod=self.config.params["n0_mod"]
        )


@DerivationMethod.register
class SigmaSnowWaterEquivalenceSnowfox(DerivationMethod):
    """Calculate **uncertainty** in a snow water equivalence (SWE) calculation for a below ground (SnowFox) COSMOS
    sensor.

    See `hydrometlib.cosmos.sigma_snow_water_equivalence_snowfox` for the science.
    """

    name = "calculate_snowfox_sigma_swe"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return cosmos.sigma_snow_water_equivalence_snowfox(
            cts_smo=columns["cts_smo_snowfox"], cts_est=columns["cts_est_snowfox"]
        )


@DerivationMethod.register
class SoilMoistureIndex(DerivationMethod):
    """Calculate soil moisture index.

    See `hydrometlib.cosmos.soil_moisture_index` for the science.
    """

    name = "calculate_smi"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return cosmos.soil_moisture_index(
            cosmos_vwc=columns["cosmos_vwc"],
            wilting_point=columns["vwc_wilting_point"],
            field_capacity=columns["vwc_field_capacity"],
            saturation=columns["vwc_saturation"],
        )


@DerivationMethod.register
class EffectiveDepth(DerivationMethod):
    """Original effective depth calculation from SIMPLE VWC method.

    See `hydrometlib.cosmos.effective_depth` for the science.
    """

    name = "calculate_eff_depth"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return cosmos.effective_depth(
            cosmos_vwc=columns["cosmos_vwc"],
            ref_soc=self.config.params["ref_soc"],
            ref_bulkdensity=self.config.params["ref_bulkdensity"],
            ref_latticewater=self.config.params["ref_latticewater"],
        )


@DerivationMethod.register
class D86(DerivationMethod):
    """Calculate d86 value.

    See `hydrometlib.cosmos.d86` for the science.
    """

    name = "calculate_d86"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return cosmos.d86(
            cosmos_vwc=columns["cosmos_vwc"],
            pa=columns["pa"],
            ref_soc=self.config.params["ref_soc"],
            ref_bulkdensity=self.config.params["ref_bulkdensity"],
            ref_latticewater=self.config.params["ref_latticewater"],
            distance=self.config.params["distance"],
        )


@DerivationMethod.register
class CalcFluxMeanShf(DerivationMethod):
    """Calculate mean soil heat flux from two SHF plate measurements.

    See `hydrometlib.meteorology.mean_soil_heat_flux` for the science.
    """

    name = "calc_flux_mean_shf"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return meteorology.mean_soil_heat_flux(g1=columns["g_plate_1_1_1"], g2=columns["g_plate_1_1_2"])


@DerivationMethod.register
class CalcFluxLeL1(DerivationMethod):
    """Calculate latent heat flux LE_L1 = Rn - SHF - H [W m-2].

    See `hydrometlib.flux.latent_heat_flux` for the science.
    """

    name = "calc_flux_le_l1"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return flux.latent_heat_flux(rn=columns["t_nr_avg"], shf=columns["shf"], h=columns["h"])


@DerivationMethod.register
class CalcFluxEtL1(DerivationMethod):
    """Calculate evapotranspiration ET_L1 = LE_L1 / lambda / 1000 [mm 30min-1].

    See `hydrometlib.flux.evapotranspiration_from_latent_heat_flux` for the science.
    """

    name = "calc_flux_et_l1"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return flux.evapotranspiration_from_latent_heat_flux(le=columns["le_l1"], ta=columns["airtemp_c"])


@DerivationMethod.register
class CalcFluxLeL2(DerivationMethod):
    """Calculate latent heat flux LE_L2 = Rn - SHF - H_L2 [W m-2], using despiked H.

    See `hydrometlib.flux.latent_heat_flux` for the science.
    """

    name = "calc_flux_le_l2"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return flux.latent_heat_flux(rn=columns["t_nr_avg"], shf=columns["shf"], h=columns["h_l2"])


@DerivationMethod.register
class CalcFluxEtL2(DerivationMethod):
    """Calculate evapotranspiration ET_L2 = LE_L2 / lambda / 1000 [mm 30min-1], using despiked LE.

    See `hydrometlib.flux.evapotranspiration_from_latent_heat_flux` for the science.
    """

    name = "calc_flux_et_l2"

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return flux.evapotranspiration_from_latent_heat_flux(le=columns["le_l2"], ta=columns["airtemp_c"])


def _get_crns_column(input_column_names: Iterable[str], option: Literal["cts_mod", "cts_smo"]) -> str:
    """Retrieve the expected CRNS column name from the input column mapping.

    This is a workaround to support calculations that are used by the standard above ground CRNS and the
    below ground SNOWFOX CRNS.

    To keep downstream logic generic, this function resolves which input dataset it's been provided with and
    return that column name.

    NOTE: This is a temporary solution to a wider problem that we want to solve via metadata. The solution will be
        some way in the metadata to be able to specify dependent timeseries (dep_ts) inputs that are named against
        the input parameter names expected by the given derivation method. So the derivation method input parameter
        names stay generic, and the data processing configurations can handle the specific mapping.

    Args:
        input_column_names: Column names provided to the calculation

    Returns:
        The CTS MOD column name
    """
    match option:
        case "cts_mod":
            possible_keys = {"cts_mod", "cts_snowfox"}
        case "cts_smo":
            possible_keys = {"cts_smo_crns", "cts_smo_snowfox"}

    found_keys = possible_keys & set(input_column_names)

    if len(found_keys) != 1:
        raise KeyError(f"Expected exactly one of {possible_keys}, found {found_keys}")

    return found_keys.pop()
