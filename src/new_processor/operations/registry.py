from new_processor.operations.correction.correction import CorrectionProcessor
from new_processor.operations.infill.infill import InfillProcessor
from new_processor.operations.quality_control.qc import QCProcessor
from new_processor.utils.enums import OperationType


OPERATION_PROCESSORS = {
    OperationType.CORRECTION: CorrectionProcessor(),
    OperationType.QUALITY_CONTROL: QCProcessor(),
    OperationType.INFILLING: InfillProcessor()
}