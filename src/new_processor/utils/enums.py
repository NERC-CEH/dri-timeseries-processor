from enum import Enum


class CliSelectionMode(Enum):
    EXPLICIT = "explicit"
    CROSS_PRODUCT = "cross_product"


class ConfigurationType(Enum):
    CORRECTION = "correction-configuration"
    INFILLING = "infill-configuration"
    QUALITY_CONTROL = "qc"


class MethodType(Enum):
    PROCESS = "process"
    DERIVATION = "calculate"
    AGGREGATION = "aggregate"
    LOAD = "load_raw"


class OperationType(Enum):
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
