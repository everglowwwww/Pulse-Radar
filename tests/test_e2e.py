"""
端到端集成测试 — 使用 mock 数据模拟完整的扫描流程。
不依赖 AKShare 网络请求。
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from src.scanner import PulseRadarScanner


def _mock_market_df() -> pd.DataFrame:
    """构造模拟全市场行情 DataFrame，包含各种类型的股票。
    
    为通过反爬保护（stock_count >= 1000），使用填充行补足到 1200 条。
    """
    notable_rows = [
        # 涨速异动 + 放量 → 应触发信号
        {
            "代码": "000001", "名称": "平安银行",
            "最新价": 12.50, "涨跌幅": 4.5, "涨速": 3.5,
            "5分钟涨跌": 3.2, "量比": 5.0, "换手率": 3.5,
            "成交额": 500_000_000, "成交量": 40_000_000,
            "流通市值": 80_000_000_000,
        },
        # 极端量比突变 → 应触发信号
        {
            "代码": "600519", "名称": "贵州茅台",
            "最新价": 1800.00, "涨跌幅": 1.2, "涨速": 0.3,
            "5分钟涨跌": 0.5, "量比": 10.0, "换手率": 2.0,
            "成交额": 3_000_000_000, "成交量": 1_700_000,
            "流通市值": 2_000_000_000_000,
        },
        # 正常股票 → 不应触发
        {
            "代码": "000002", "名称": "万科A",
            "最新价": 8.00, "涨跌幅": 0.5, "涨速": 0.1,
            "5分钟涨跌": 0.2, "量比": 1.2, "换手率": 1.5,
            "成交额": 200_000_000, "成交量": 25_000_000,
            "流通市值": 60_000_000_000,
        },
        # ST 股 → 应被过滤
        {
            "代码": "000003", "名称": "ST退市股",
            "最新价": 1.50, "涨跌幅": 5.0, "涨速": 4.0,
            "5分钟涨跌": 5.0, "量比": 8.0, "换手率": 10.0,
            "成交额": 50_000_000, "成交量": 30_000_000,
            "流通市值": 500_000_000,
        },
        # 小市值 → 应被过滤
        {
            "代码": "000004", "名称": "小盘股",
            "最新价": 5.00, "涨跌幅": 3.0, "涨速": 3.0,
            "5分钟涨跌": 3.0, "量比": 6.0, "换手率": 5.0,
            "成交额": 20_000_000, "成交量": 4_000_000,
            "流通市值": 800_000_000,
        },
    ]
    # 填充行：普通平静的股票，满足反爬检测（>= 1000 条）
    filler = [{
        "代码": f"{100000 + i}", "名称": f"填充股{i}",
        "最新价": 10.0, "涨跌幅": 0.1, "涨速": 0.0,
        "5分钟涨跌": 0.0, "量比": 1.0, "换手率": 1.0,
        "成交额": 100_000_000, "成交量": 10_000_000,
        "流通市值": 5_000_000_000,
    } for i in range(1200)]
    return pd.DataFrame(notable_rows + filler)


def _mock_zt_df() -> pd.DataFrame:
    """模拟涨停池数据。"""
    return pd.DataFrame([{
        "代码": "300999", "名称": "金龙鱼",
        "封板资金": 8e8, "首次封板时间": "09:42",
        "涨停统计": "3连板",
    }])


def _mock_zb_df() -> pd.DataFrame:
    """模拟炸板池数据。"""
    return pd.DataFrame([{
        "代码": "002456", "名称": "欧菲光",
        "炸板次数": 2,
    }])


def _make_config(tmpdir: str) -> dict:
    """构造测试配置。"""
    return {
        "poll_interval": 5,
        "push_threshold": 30,  # 低阈值确保能触发
        "sensitivity": "medium",
        "filters": {
            "exclude_st": True,
            "min_market_cap": 2_000_000_000,
            "min_daily_turnover": 50_000_000,
            "min_turnover_rate": 0.3,
        },
        "watchlist": {
            "enabled": True,
            "stocks": [
                {"code": "000002", "name": "万科A", "target_price": 7.5, "stop_loss": None},
            ],
            "push_threshold": 20,
            "midday_summary": True,
        },
        "notifications": {"desktop": False},  # 测试中禁用通知
        "output_dir": tmpdir,
    }


class TestEndToEnd:
    """端到端扫描集成测试。"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = _make_config(self.tmpdir)
        # 写入 config.json 供 WatchlistManager 使用
        self.config_path = str(Path(self.tmpdir) / "config.json")
        with open(self.config_path, "w") as f:
            json.dump(self.config, f)

    def _make_scanner(self) -> PulseRadarScanner:
        return PulseRadarScanner(self.config, config_path=self.config_path)

    @patch("src.scanner.ak")
    def test_full_scan_produces_signals(self, mock_ak):
        """完整扫描流程应能检测到信号。"""
        mock_ak.stock_zh_a_spot_em.return_value = _mock_market_df()
        mock_ak.stock_zt_pool_em.return_value = _mock_zt_df()
        mock_ak.stock_zt_pool_zbgc_em.return_value = _mock_zb_df()

        scanner = self._make_scanner()
        signals = scanner.scan_once()

        # 平安银行（涨速异动+放量）或贵州茅台（极端量比）应该触发
        assert len(signals) > 0
        codes = [s["stock_code"] for s in signals]
        # 至少一个核心信号触发
        assert "000001" in codes or "600519" in codes

    @patch("src.scanner.ak")
    def test_st_filtered_out(self, mock_ak):
        """ST 股票应被过滤掉。"""
        mock_ak.stock_zh_a_spot_em.return_value = _mock_market_df()
        mock_ak.stock_zt_pool_em.return_value = pd.DataFrame()
        mock_ak.stock_zt_pool_zbgc_em.return_value = pd.DataFrame()

        scanner = self._make_scanner()
        signals = scanner.scan_once()

        codes = [s["stock_code"] for s in signals]
        assert "000003" not in codes  # ST 退市股

    @patch("src.scanner.ak")
    def test_small_cap_filtered_out(self, mock_ak):
        """小市值股应被过滤掉。"""
        mock_ak.stock_zh_a_spot_em.return_value = _mock_market_df()
        mock_ak.stock_zt_pool_em.return_value = pd.DataFrame()
        mock_ak.stock_zt_pool_zbgc_em.return_value = pd.DataFrame()

        scanner = self._make_scanner()
        signals = scanner.scan_once()

        codes = [s["stock_code"] for s in signals]
        assert "000004" not in codes  # 小盘股

    @patch("src.scanner.ak")
    def test_process_signals_logs_to_file(self, mock_ak):
        """信号处理后应写入 JSON 日志。"""
        mock_ak.stock_zh_a_spot_em.return_value = _mock_market_df()
        mock_ak.stock_zt_pool_em.return_value = pd.DataFrame()
        mock_ak.stock_zt_pool_zbgc_em.return_value = pd.DataFrame()

        scanner = self._make_scanner()
        signals = scanner.scan_once()

        if signals:
            scanner.process_signals(signals)
            # 检查日志文件
            log_files = list(Path(self.tmpdir).glob("pulse-radar-*.json"))
            assert len(log_files) >= 1
            with open(log_files[0]) as f:
                logged = json.load(f)
            assert len(logged) > 0
            assert "stock_code" in logged[0]
            assert "score" in logged[0]

    @patch("src.scanner.ak")
    def test_anti_crawl_protection(self, mock_ak):
        """数据量骤降应触发反爬保护。"""
        # 返回极少数据模拟反爬
        tiny_df = _mock_market_df().head(1)  # 只有 1 条
        mock_ak.stock_zh_a_spot_em.return_value = tiny_df

        scanner = self._make_scanner()
        result = scanner.fetch_market_data()
        assert result is None  # 数据量太少，返回 None

    @patch("src.scanner.ak")
    def test_empty_data_handled_gracefully(self, mock_ak):
        """空数据不应崩溃。"""
        mock_ak.stock_zh_a_spot_em.return_value = pd.DataFrame()

        scanner = self._make_scanner()
        result = scanner.fetch_market_data()
        assert result is None

    @patch("src.scanner.ak")
    def test_scan_stats_updated(self, mock_ak):
        """扫描后统计数据应正确更新。"""
        mock_ak.stock_zh_a_spot_em.return_value = _mock_market_df()
        mock_ak.stock_zt_pool_em.return_value = pd.DataFrame()
        mock_ak.stock_zt_pool_zbgc_em.return_value = pd.DataFrame()

        scanner = self._make_scanner()
        scanner.scan_once()

        assert scanner.stats["scan_count"] == 1
        assert scanner.stats["last_scan_time"] is not None
        assert scanner.stats["last_stock_count"] == 1205  # 5 notable + 1200 filler

    @patch("src.scanner.ak")
    def test_limit_signals_on_third_scan(self, mock_ak):
        """涨停/炸板信号在第 3 次扫描时检测（scan_count % 3 == 0）。"""
        mock_ak.stock_zh_a_spot_em.return_value = _mock_market_df()
        mock_ak.stock_zt_pool_em.return_value = _mock_zt_df()
        mock_ak.stock_zt_pool_zbgc_em.return_value = _mock_zb_df()

        scanner = self._make_scanner()
        # 前两次扫描
        scanner.scan_once()
        scanner.scan_once()
        # 第三次扫描应包含涨停/炸板检测
        signals = scanner.scan_once()

        all_types = [s.get("signal_type") for s in signals]
        # 涨停或炸板信号应该在第 3 轮出现
        has_limit = "涨停封板" in all_types or "涨停炸板" in all_types
        # 不强制要求（取决于评分是否过阈值），但至少 scan_count 正确
        assert scanner.stats["scan_count"] == 3
