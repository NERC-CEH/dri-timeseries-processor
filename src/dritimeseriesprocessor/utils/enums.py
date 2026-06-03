from enum import Enum


class CliSelectionMode(Enum):
    EXPLICIT = "from-selection"
    CROSS_PRODUCT = "from-cross-product"
    FROM_DATASETS = "from-datasets"
    LIST_SITES = "list-sites"


class ConfigurationType(Enum):
    """Represents specific data-processing-configuration types held in the metadata store.

    See:
    - https://dri-metadata-api.dri.ceh.ac.uk/vocab/metadata/InternalDataProcessingConfiguration
    - https://dri-metadata-api.dri.ceh.ac.uk/ref/common/configuration-type
    """

    CORRECTION = "correction"
    INFILLING = "infill"
    QUALITY_CONTROL = "qc"
    DERIVATION = "calculate"
    AGGREGATION = "aggregate"
    LOAD_LOCAL_COPY = "load-local-copy"


class DatasetType(Enum):
    """The metadata `@type` of a dataset record.

    `TIMESERIES_DATASET` is a single-variable timeseries dataset; `OBSERVATION_DATASET` is a multi-column bundle
    (e.g. raw EddyPro inputs, EddyPro outputs).
    """

    TIMESERIES_DATASET = "TimeSeriesDataset"
    OBSERVATION_DATASET = "ObservationDataset"


class ProcessingLevel(Enum):
    RAW = "raw"
    PROCESSED = "processed"


class Environment(Enum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"
    STAGING_FAKE = "staging-fake"
