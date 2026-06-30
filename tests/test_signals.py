"""signals 模块单元测试。"""

import pandas as pd
import pytest
from src.signals import SignalDetector, LimitDetector


def _row(**kw) -> pd.Series:
    """构造模拟行情 Series。"""
    defaults = {
        "代码": "000001", "名称": "测试股",
        "涨速": 0, "5分钟涨跌": 0, "量比": 1.0,
        "最新价": 10.0, "涨跌幅": 0, "换手率": 2.0,
        "成交额": 100_000_000, "成交量": 10_000_000,
    }
    defaults.update(kw)
    return pd.Series(defaults)


class TestSignalDetector:
    """SignalDetector 测试。"""

    def setup_method(self):
        self.detector = SignalDetector({"sensitivity": "medium"})

    def test_no_signal_on_calm_stock(self):
        row = _row(涨速=0.1, 量比=0.8)
        signals = self.detector.detect_all(row)
        assert signals == []

    def test_speed_anomaly_triggered(self):
        row = _row(涨速=3.5, 量比=2.0)
        signals = self.detector.detect_all(row)
        types = [s["signal_type"] for s in signals]
        assert "涨速异动" in types

    def test_speed_needs_volume(self):
        """涨速高但量比不达标，不应触发涨速异动。"""
        row = _row(涨速=5.0, 量比=0.5)
        sig = self.detector.detect_speed_anomaly(row)
        assert sig is None

    def test_volume_surge_significant(self):
        row = _row(量比=4.0)
        sig = self.detector.detect_volume_surge(row)
        assert sig is not None
        assert sig["signal_type"] == "量比突变"
        assert sig["strength"] == 1.0

    def test_volume_surge_extreme(self):
        row = _row(量比=10.0)
        sig = self.detector.detect_volume_surge(row)
        assert sig is not None
        assert sig["strength"] == 3.0

    def test_volume_below_threshold_no_signal(self):
        row = _row(量比=2.0)
        sig = self.detector.detect_volume_surge(row)
        assert sig is None

    def test_high_sensitivity_lower_thresholds(self):
        det = SignalDetector({"sensitivity": "high"})
        # 在 medium 下不会触发，但 high 灵敏度下会触发
        row = _row(涨速=1.8, 量比=2.0)
        sig = det.detect_speed_anomaly(row)
        assert sig is not None  # high: threshold=1.5, 1.8 > 1.5

    def test_low_sensitivity_higher_thresholds(self):
        det = SignalDetector({"sensitivity": "low"})
        # 在 medium 下会触发（2.0 threshold），但 low 下不会（3.0 threshold）
        row = _row(涨速=2.5, 量比=2.0)
        sig = det.detect_speed_anomaly(row)
        assert sig is None  # low: threshold=3.0, 2.5 < 3.0


class TestLimitDetector:
    """LimitDetector 测试。"""

    def setup_method(self):
        self.detector = LimitDetector()

    def test_new_zt_detected(self):
        zt_df = pd.DataFrame([{
            "代码": "000001", "名称": "平安银行",
            "封板资金": 5e8, "首次封板时间": "10:05",
            "涨停统计": "2连板",
        }])
        signals = self.detector.detect_limit_changes(zt_df, None)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "涨停封板"
        assert signals[0]["stock_code"] == "000001"

    def test_known_zt_not_repeated(self):
        zt_df = pd.DataFrame([{"代码": "000001", "名称": "A", "封板资金": 0, "首次封板时间": "", "涨停统计": ""}])
        self.detector.detect_limit_changes(zt_df, None)
        # 第二次相同涨停不应重复
        signals = self.detector.detect_limit_changes(zt_df, None)
        assert len(signals) == 0

    def test_zb_detected(self):
        zb_df = pd.DataFrame([{"代码": "000002", "名称": "万科A", "炸板次数": 2}])
        signals = self.detector.detect_limit_changes(None, zb_df)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "涨停炸板"

    def test_zb_dedup(self):
        """同一只票炸板不重复。"""
        zb_df = pd.DataFrame([{"代码": "000002", "名称": "万科A", "炸板次数": 1}])
        self.detector.detect_limit_changes(None, zb_df)
        signals = self.detector.detect_limit_changes(None, zb_df)
        assert len(signals) == 0

    def test_none_inputs_no_crash(self):
        signals = self.detector.detect_limit_changes(None, None)
        assert signals == []
