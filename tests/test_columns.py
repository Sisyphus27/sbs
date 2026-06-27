from tools.sbs_gzclp.columns import BLOCKS, col, block_start_cols

def test_blocks_are_21_weeks_stepping_7():
    starts = block_start_cols(weeks=21, start=2, step=7)
    assert len(starts) == 21
    assert starts[0] == "B"
    assert starts[1] == "I"
    assert starts[2] == "P"
    assert starts[3] == "W"
    assert starts[20] == "EL"

def test_col_offset_within_block():
    assert col("B", 0) == "B"
    assert col("B", 4) == "F"
    assert col("I", 4) == "M"
    assert col("P", 1) == "Q"

def test_BLOCKS_constant_matches_generator():
    assert BLOCKS == block_start_cols(21, 2, 7)
