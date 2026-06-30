"""logger 模块单元测试。"""

import json
import tempfile
from pathlib import Path

from src.logger import SignalLogger


class TestSignalLogger:
    """SignalLogger 测试。"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.logger = SignalLogger(self.tmpdir, retention_days=7)

    def test_log_signal_creates_file(self):
        self.logger.log_signal({
            "stock_code": "000001",
            "stock_name": "平安银行",
            "signal_type": "涨速异动",
            "score": 75.0,
        })
        # 应该创建了一个 JSON 文件
        json_files = list(Path(self.tmpdir).glob("pulse-radar-*.json"))
        assert len(json_files) == 1

    def test_log_signal_adds_timestamp(self):
        self.logger.log_signal({"stock_code": "000001", "signal_type": "test"})
        signals = self.logger.get_today_signals()
        assert len(signals) == 1
        assert "timestamp" in signals[0]

    def test_get_today_signals_returns_copy(self):
        self.logger.log_signal({"stock_code": "000001", "signal_type": "test"})
        s1 = self.logger.get_today_signals()
        s2 = self.logger.get_today_signals()
        assert s1 == s2
        # 修改返回值不影响内部状态
        s1.append({"fake": True})
        assert len(self.logger.get_today_signals()) == 1

    def test_today_summary_empty(self):
        summary = self.logger.get_today_summary()
        assert summary["total_signals"] == 0

    def test_today_summary_with_signals(self):
        for i in range(3):
            self.logger.log_signal({
                "stock_code": f"00000{i}",
                "stock_name": f"股票{i}",
                "signal_type": "涨速异动" if i < 2 else "量比突变",
                "score": 80 - i * 10,
                "notified": i == 0,
            })
        summary = self.logger.get_today_summary()
        assert summary["total_signals"] == 3
        assert summary["notified_count"] == 1
        assert summary["by_type"]["涨速异动"] == 2
        assert summary["by_type"]["量比突变"] == 1
        assert len(summary["top_10"]) == 3

    def test_cleanup_old_logs(self):
        """测试日志清理。"""
        # 创建一些模拟的旧日志文件
        old_file = Path(self.tmpdir) / "pulse-radar-2024-01-01.json"
        old_file.write_text("[]")
        recent_file = Path(self.tmpdir) / "pulse-radar-2099-12-31.json"
        recent_file.write_text("[]")

        self.logger.cleanup_old_logs()

        assert not old_file.exists()  # 旧文件应被删除
        assert recent_file.exists()   # 未来文件不应被删除

    def test_cleanup_runs_once_per_day(self):
        """cleanup_old_logs 每天只执行一次。"""
        old_file = Path(self.tmpdir) / "pulse-radar-2024-01-01.json"
        old_file.write_text("[]")

        self.logger.cleanup_old_logs()
        assert not old_file.exists()

        # 再创建一个旧文件，由于今天已执行过，不会清理
        old_file2 = Path(self.tmpdir) / "pulse-radar-2024-02-01.json"
        old_file2.write_text("[]")
        self.logger.cleanup_old_logs()
        assert old_file2.exists()  # 不会被清理（今天已执行过）
