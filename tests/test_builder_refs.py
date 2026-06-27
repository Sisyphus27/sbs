from tools.sbs_gzclp.builder import shift_same_sheet_refs as sh


def test_shifts_plain_same_sheet_ref():
    assert sh("=IF(K19=\"\",F20)", 13, 4) == "=IF(K23=\"\",F24)"


def test_shifts_absolute_row():
    assert sh("=MROUND($A$20)", 13, 4) == "=MROUND($A$24)"


def test_leaves_below_threshold_alone():
    assert sh("=A2+B5", 13, 4) == "=A2+B5"


def test_leaves_other_sheet_refs_alone():
    assert sh("=Setup!F5+'Quick Setup'!$A$2", 13, 4) == "=Setup!F5+'Quick Setup'!$A$2"


def test_handles_concatenate_and_function_names():
    assert sh('=CONCATENATE(A20," TM")', 13, 4) == '=CONCATENATE(A24," TM")'
    assert sh("=MROUND(B19*Setup!N5,'Quick Setup'!$A$2)", 13, 4) == "=MROUND(B23*Setup!N5,'Quick Setup'!$A$2)"


def test_non_formula_unchanged():
    assert sh(10, 13, 4) == 10
    assert sh("hello", 13, 4) == "hello"


def test_quoted_sheet_ref_above_insertion_is_preserved():
    # the bug: 'Quick Setup'!D13 (row >= insertion 13) must NOT shift
    from tools.sbs_gzclp.builder import shift_same_sheet_refs as sh
    assert sh("='Quick Setup'!D13", 13, 4) == "='Quick Setup'!D13"
    assert sh("='Quick Setup'!D20", 13, 4) == "='Quick Setup'!D20"
    assert sh("=IF(D23=\"\",'Quick Setup'!D13,D23/'Quick Setup'!E13)", 13, 4) \
        == "=IF(D27=\"\",'Quick Setup'!D13,D27/'Quick Setup'!E13)"
    # multi-letter col in quoted sheet, row >= insertion
    assert sh("='Quick Setup'!AA15", 13, 4) == "='Quick Setup'!AA15"
