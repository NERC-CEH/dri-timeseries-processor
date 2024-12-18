from dritimeseriesprocessor.flagging.bitwise import FlagManager, create_flag_class

QCFlags = create_flag_class(
    "QCFlags",
    {
        "RANGE_CHECK": 1,
        "SPIKE_CHECK": 2,
        "OTHER_CHECK": 4,
    },
)


# Example usage for QCFlags
qc_manager = FlagManager(QCFlags)
qc_manager.add_flag(QCFlags.RANGE_CHECK)
qc_manager.add_flag(QCFlags.SPIKE_CHECK)

print(qc_manager.flags)
