from new_processor.operations.correction import CorrectionProcessor
from new_processor.operations.infill import InfillProcessor
from new_processor.operations.qc import QCProcessor
from new_processor.utils.enums import OperationType


OPERATION_PROCESSORS = {
    OperationType.CORRECTION: CorrectionProcessor(),
    OperationType.QUALITY_CONTROL: QCProcessor(),
    OperationType.INFILLING: InfillProcessor()
}