from enum import Enum


class CliSelectionMode(Enum):
    EXPLICIT = "from-selection"
    CROSS_PRODUCT = "from-cross-product"
    EDDYPRO = "eddypro"
    LIST_SITES = "list-sites"


class ConfigurationType(Enum):
    """Represents specific data-processing-configuration types held in the metadata store.

    See:
    - https://dri-metadata-api.staging.eds.ceh.ac.uk/vocab/metadata/InternalDataProcessingConfiguration
    - https://dri-metadata-api.staging.eds.ceh.ac.uk/ref/common/configuration-type
    """

    CALIBRATION_CORRECTION = "sensor-calibration-correction"
    CORRECTION = "correction-configuration"
    INFILLING = "infill-configuration"
    QUALITY_CONTROL = "qc"
    DERIVATION = "calculate"
    AGGREGATION = "aggregate"
    PROCESS = "process"
    EDDYPRO = "eddypro"
    LOAD_LOCAL_COPY = "load-local-copy"


class MethodType(Enum):
    """Represents specific steps within the data processing pipeline."""

    PROCESS = "process"
    DERIVATION = "calculate"
    AGGREGATION = "aggregate"
    LOAD = "load"
    EDDYPRO = "eddypro"
    LOAD_LOCAL_COPY = "load-local-copy"


class OperationType(Enum):
    """Represents specific operations within the data processing pipeline.

    For example, for the `MethodType.PROCESS`, there are 3 operations to carry out: correction, qc, infilling.
    """

    CORRECTION = "correction"
    INFILLING = "infilling"
    QUALITY_CONTROL = "quality_control"
    DERIVATION = "calculate"
    AGGREGATION = "aggregate"


class ProcessingLevel(Enum):
    RAW = "raw"
    PROCESSED = "processed"


class Environment(Enum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"
    STAGING_FAKE = "staging-fake"
