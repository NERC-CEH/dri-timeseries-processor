from new_processor.operations.flags.flag_names import (
    core_flag_column_name,
    corrs_flag_column_name,
    infill_flag_column_name,
    qc_flag_column_name,
)


class TestCoreFlagColumnName:
    def test_core_flag_column_name(self) -> None:
        assert core_flag_column_name("data") == "data_CORE_FLAG"


class TestCorrsFlagColumnName:
    def test_standard_column_name(self) -> None:
        assert corrs_flag_column_name("data") == "data_CORRS_FLAG"


class TestQCFlagColumnName:
    def test_standard_column_name(self) -> None:
        assert qc_flag_column_name("data") == "data_QC_FLAG"


class TestInfillFlagColumnName:
    def test_standard_column_name(self) -> None:
        assert infill_flag_column_name("data") == "data_INFILL_FLAG"
