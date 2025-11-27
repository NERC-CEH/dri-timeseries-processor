from enum import Enum


class ConfigurationType(Enum):
    CORRECTION = "correction-configuration"
    INFILLING = "infill-configuration"
    QUALITY_CONTROL = "qc"


class MethodType(Enum):
    PROCESS = "process"
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
