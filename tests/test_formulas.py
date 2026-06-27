from tools.sbs_gzclp.columns import col
from tools.sbs_gzclp.formulas import t2_target_formula, t2_streak_formula, \
    t2_weight_formula, t3_weight_formula, t3_target_formula

# Week-2 block (I) derived from week-1 block (B). State row 12, log row 13.

def test_t2_target_formula_week2():
    f = t2_target_formula(prev_block="B", next_block="I", state_row=12, log_row=13)
    assert f == ("=IF(F13=\"\",C12,IF(F13>=C12,C12,"
                 "IF(D12+1>='Quick Setup'!$B$73,IF(C12=10,8,IF(C12=8,6,10)),C12)))")

def test_t2_streak_formula_week2():
    f = t2_streak_formula(prev_block="B", next_block="I", state_row=12, log_row=13)
    assert f == "=IF(F13=\"\",D12,IF(F13>=C12,0,IF(D12+1>='Quick Setup'!$B$73,0,D12+1)))"

def test_t2_weight_formula_week2():
    f = t2_weight_formula(prev_block="B", next_block="I", state_row=12, log_row=13)
    assert f == ("=IF(F13=\"\",B12,IF(F13>=C12,MROUND(B12+'Quick Setup'!$B$71,"
                 "'Quick Setup'!$A$2),IF(AND(D12+1>='Quick Setup'!$B$73,C12=6),"
                 "MROUND(B12*'Quick Setup'!$B$72,'Quick Setup'!$A$2),B12)))")

def test_t3_weight_formula_week2():
    f = t3_weight_formula(prev_block="B", next_block="I", row=12)
    assert f == ("=IF(F12=\"\",B12,IF(F12>='Quick Setup'!$B$74,"
                 "MROUND(B12+'Quick Setup'!$B$75,'Quick Setup'!$A$2),B12))")

def test_t3_target_formula_is_constant_reference():
    assert t3_target_formula(row=12) == "='Quick Setup'!$B$74"

def test_formula_uses_correct_columns_for_block_P_to_W():
    f = t2_target_formula(prev_block="P", next_block="W", state_row=20, log_row=21)
    assert f.startswith("=IF(T21=\"\",Q20,IF(T21>=Q20,Q20,")
    assert "R20+1" in f
    assert f.endswith(",Q20)))")
