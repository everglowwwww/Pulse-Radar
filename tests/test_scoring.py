"""scoring 模块单元测试。"""

import pytest
from src.scoring import score_signals, calculate_confidence, merge_signals


class TestScoreSignals:
    """score_signals 测试。"""

    def test_empty_signals_returns_zero(self):
        assert score_signals([], {}) == 0.0

    def test_single_speed_signal(self):
        signals = [{"signal_type": "涨速异动", "strength": 1.0}]
        stock = {"流通市值": 5_000_000_000, "量比": 2.0, "换手率": 3.0}
        score = score_signals(signals, stock)
        assert 0 < score <= 100

    def test_stronger_signal_gets_higher_score(self):
        weak = [{"signal_type": "涨速异动", "strength": 1.0}]
        strong = [{"signal_type": "涨速异动", "strength": 2.5}]
        stock = {"流通市值": 5_000_000_000, "量比": 2.0, "换手率": 3.0}
        assert score_signals(strong, stock) > score_signals(weak, stock)

    def test_multi_signal_resonance_boost(self):
        """多信号共振应该高于单信号。"""
        single = [{"signal_type": "涨速异动", "strength": 2.0}]
        multi = [
            {"signal_type": "涨速异动", "strength": 2.0},
            {"signal_type": "量比突变", "strength": 2.0},
        ]
        stock = {"流通市值": 5_000_000_000, "量比": 5.0, "换手率": 3.0}
        assert score_signals(multi, stock) > score_signals(single, stock)

    def test_score_clamped_to_100(self):
        """得分上限 100。"""
        signals = [
            {"signal_type": "涨停封板", "strength": 3.0},
            {"signal_type": "涨速异动", "strength": 3.0},
            {"signal_type": "量比突变", "strength": 3.0},
            {"signal_type": "VWAP突破", "strength": 3.0},
        ]
        stock = {"流通市值": 100_000_000_000, "量比": 10.0, "换手率": 5.0}
        score = score_signals(signals, stock)
        assert score <= 100.0

    def test_zt_signal_high_base(self):
        """涨停封板基础分应该较高。"""
        zt = [{"signal_type": "涨停封板", "strength": 1.0}]
        speed = [{"signal_type": "涨速异动", "strength": 1.0}]
        stock = {"流通市值": 5_000_000_000, "量比": 2.0, "换手率": 3.0}
        assert score_signals(zt, stock) > score_signals(speed, stock)


class TestCalculateConfidence:
    """calculate_confidence 测试。"""

    def test_large_cap_boost(self):
        """大市值股票置信度提升。"""
        large = {"流通市值": 10_000_000_000, "量比": 2.0, "换手率": 3.0}
        small = {"流通市值": 1_000_000_000, "量比": 2.0, "换手率": 3.0}
        signals = [{"signal_type": "涨速异动", "strength": 1.0}]
        assert calculate_confidence(large, signals) > calculate_confidence(small, signals)

    def test_confidence_bounded(self):
        """置信度范围 0.1 ~ 2.0。"""
        stock = {"流通市值": 500_000_000, "量比": 0.5, "换手率": 0.2}
        signals = [{"signal_type": "涨速异动", "strength": 1.0}]
        c = calculate_confidence(stock, signals)
        assert 0.1 <= c <= 2.0


class TestMergeSignals:
    """merge_signals 测试。"""

    def test_basic_merge(self):
        signals = [
            {"signal_type": "涨速异动", "strength": 2.0, "reasons": ["涨速 +3.5%/min"]},
            {"signal_type": "量比突变", "strength": 1.5, "reasons": ["显著放量 量比 4.2"]},
        ]
        stock = {
            "代码": "000001", "名称": "平安银行",
            "最新价": 12.5, "涨跌幅": 3.2,
            "量比": 4.2, "换手率": 2.1,
            "流通市值": 50_000_000_000,
        }
        record = merge_signals(signals, stock, 75.0)
        assert record["stock_code"] == "000001"
        assert record["stock_name"] == "平安银行"
        assert record["score"] == 75.0
        assert record["signal_type"] == "涨速异动"  # 最强信号
        assert len(record["reasons"]) == 2
        assert record["notified"] is False
