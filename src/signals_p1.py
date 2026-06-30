"""
PulseRadar — P1 增强信号检测模块
实现：板块共振、封单强度分析、连板梯队追踪、VWAP 突破检测。
"""

import logging
from datetime import datetime

import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)


class SectorResonance:
    """
    板块共振检测器。
    当个股触发异动时，检查其所在行业/概念板块是否同步走强。
    共振加分：个股异动 + 板块涨幅 top 10 → 置信度提升。
    
    性能优化：在 refresh() 时一次性拉取 top 板块的成分股并构建
    code → [板块名] 的映射表，check_resonance() 仅做字典查找，
    避免逐只股票请求网络导致扫描循环卡死。
    """
    
    def __init__(self):
        # 缓存板块数据（每轮扫描更新一次）
        self._industry_top: set[str] = set()   # 涨幅前 10 行业板块名称
        self._concept_top: set[str] = set()    # 涨幅前 10 概念板块名称
        # 预构建的 code → 所属强势板块列表 映射
        self._code_to_industry: dict[str, list[str]] = {}
        self._code_to_concept: dict[str, list[str]] = {}
        self._last_refresh: float = 0
        self._refresh_interval = 180  # 板块数据 3 分钟刷新一次（含成分股加载）
    
    def refresh(self):
        """刷新板块涨幅排行数据并预加载成分股映射。"""
        now = datetime.now().timestamp()
        if now - self._last_refresh < self._refresh_interval:
            return
        
        self._last_refresh = now
        
        # 行业板块
        try:
            industry_df = ak.stock_board_industry_name_em()
            if industry_df is not None and not industry_df.empty:
                if "涨跌幅" in industry_df.columns and "板块名称" in industry_df.columns:
                    top = industry_df.nlargest(10, "涨跌幅")
                    self._industry_top = set(top["板块名称"].tolist())
                    logger.debug(f"行业板块 Top10: {self._industry_top}")
                    # 预加载成分股映射
                    self._code_to_industry = self._build_member_map(
                        self._industry_top, ak.stock_board_industry_cons_em, "行业"
                    )
        except Exception as e:
            logger.debug(f"获取行业板块数据失败: {e}")
        
        # 概念板块
        try:
            concept_df = ak.stock_board_concept_name_em()
            if concept_df is not None and not concept_df.empty:
                if "涨跌幅" in concept_df.columns and "板块名称" in concept_df.columns:
                    top = concept_df.nlargest(10, "涨跌幅")
                    self._concept_top = set(top["板块名称"].tolist())
                    logger.debug(f"概念板块 Top10: {self._concept_top}")
                    # 预加载成分股映射
                    self._code_to_concept = self._build_member_map(
                        self._concept_top, ak.stock_board_concept_cons_em, "概念"
                    )
        except Exception as e:
            logger.debug(f"获取概念板块数据失败: {e}")
        
        total = len(set(self._code_to_industry.keys()) | set(self._code_to_concept.keys()))
        logger.info(f"板块共振映射已构建: {total} 只股票覆盖")
    
    @staticmethod
    def _build_member_map(
        board_names: set[str],
        fetch_fn,
        prefix: str,
    ) -> dict[str, list[str]]:
        """
        批量拉取板块成分股，构建 code → [板块名] 映射。
        在 refresh() 中一次性完成，后续 check 只查字典。
        """
        code_map: dict[str, list[str]] = {}
        for board_name in board_names:
            try:
                members = fetch_fn(symbol=board_name)
                if members is not None and "代码" in members.columns:
                    for code in members["代码"].values:
                        code_map.setdefault(code, []).append(f"{prefix}:{board_name}")
            except Exception:
                continue
        return code_map
    
    def check_resonance(self, stock_code: str, stock_name: str) -> dict | None:
        """
        检查个股是否与强势板块共振。
        纯字典查找，零网络开销。
        """
        resonance_boards = []
        
        industry_boards = self._code_to_industry.get(stock_code, [])
        if industry_boards:
            resonance_boards.append(industry_boards[0])  # 取第一个匹配
        
        concept_boards = self._code_to_concept.get(stock_code, [])
        if concept_boards:
            resonance_boards.append(concept_boards[0])
        
        if not resonance_boards:
            return None
        
        return {
            "signal_type": "板块共振",
            "strength": 1.0 + 0.5 * len(resonance_boards),
            "reasons": [f"与强势板块共振: {', '.join(resonance_boards)}"],
            "raw_data": {
                "resonance_boards": resonance_boards,
            }
        }
    
    def get_top_boards(self) -> dict:
        """返回当前 top 板块信息（供状态查询使用）。"""
        return {
            "industry_top10": sorted(self._industry_top),
            "concept_top10": sorted(self._concept_top),
        }


class SealStrength:
    """
    封单强度分析器。
    计算：封单金额 ÷ 流通市值
    分级：> 5% 强封、2%-5% 中等、< 2% 弱封
    """
    
    @staticmethod
    def analyze(zt_row: pd.Series, market_cap: float) -> dict | None:
        """
        分析一只涨停股的封单强度。
        
        参数:
            zt_row: stock_zt_pool_em 返回的单行数据
            market_cap: 流通市值（元）
        
        返回:
            封单强度信号，或 None
        """
        seal_money = zt_row.get("封板资金", 0) or 0
        if seal_money <= 0 or market_cap <= 0:
            return None
        
        ratio = seal_money / market_cap
        
        if ratio > 0.05:
            level = "强封"
            strength = 2.0
        elif ratio > 0.02:
            level = "中等"
            strength = 1.0
        else:
            level = "弱封"
            strength = 0.5
        
        return {
            "signal_type": "封单强度",
            "strength": strength,
            "reasons": [f"封单 {seal_money/1e8:.1f}亿 占流通市值 {ratio*100:.1f}% ({level})"],
            "raw_data": {
                "seal_money": seal_money,
                "market_cap": market_cap,
                "ratio": ratio,
                "level": level,
            }
        }


class ChainBoardTracker:
    """
    连板梯队追踪器。
    跟踪当前市场最高连板数和各层连板股数量，
    反映市场投机情绪温度。
    """
    
    def __init__(self):
        self._last_ladder: dict[int, int] = {}  # {连板数: 股票数}
        self._max_chain: int = 0
    
    def update(self, zt_df: pd.DataFrame | None) -> dict | None:
        """
        更新连板梯队数据。
        
        参数:
            zt_df: stock_zt_pool_em 返回的涨停股池
        
        返回:
            连板梯队汇总信号（如果有变化），或 None
        """
        if zt_df is None or zt_df.empty:
            return None
        
        # 涨停统计字段格式通常为 "X连板"
        chain_col = None
        for col in ["涨停统计", "连板数"]:
            if col in zt_df.columns:
                chain_col = col
                break
        
        if chain_col is None:
            return None
        
        # 解析连板数
        ladder: dict[int, list[str]] = {}
        for _, row in zt_df.iterrows():
            chain_str = str(row.get(chain_col, ""))
            chain_num = self._parse_chain_count(chain_str)
            if chain_num >= 2:  # 2 连板及以上才纳入
                if chain_num not in ladder:
                    ladder[chain_num] = []
                name = row.get("名称", "?")
                ladder[chain_num].append(name)
        
        if not ladder:
            return None
        
        max_chain = max(ladder.keys())
        ladder_counts = {k: len(v) for k, v in ladder.items()}
        
        # 检查是否有变化
        if max_chain == self._max_chain and ladder_counts == self._last_ladder:
            return None
        
        self._max_chain = max_chain
        self._last_ladder = ladder_counts
        
        # 构建描述
        desc_parts = []
        for chain_num in sorted(ladder.keys(), reverse=True):
            stocks = ladder[chain_num]
            if chain_num >= 3:
                desc_parts.append(f"{chain_num}连板: {', '.join(stocks[:3])}")
            else:
                desc_parts.append(f"{chain_num}连板: {len(stocks)}只")
        
        return {
            "signal_type": "连板梯队",
            "strength": min(max_chain / 3.0, 3.0),
            "reasons": [f"最高{max_chain}连板"] + desc_parts[:5],
            "raw_data": {
                "max_chain": max_chain,
                "ladder": ladder_counts,
                "top_stocks": {k: v[:5] for k, v in ladder.items()},
            }
        }
    
    @staticmethod
    def _parse_chain_count(chain_str: str) -> int:
        """解析连板数文本，如 '3连板' -> 3。"""
        import re
        match = re.search(r"(\d+)", chain_str)
        if match:
            return int(match.group(1))
        return 1  # 默认首板


class VWAPDetector:
    """
    VWAP 突破检测器。
    VWAP = 累计成交额 ÷ (累计成交量 × 100)
    由于 AKShare 的 spot 接口只提供当前值而非分钟级数据，
    这里使用简化版：当价格高于当前 VWAP 且量比放大时视为突破。
    """
    
    def __init__(self):
        # 上一轮各股票的 VWAP 位置（above/below）
        self._prev_vwap_position: dict[str, str] = {}
    
    def detect(self, row: pd.Series) -> dict | None:
        """
        检测 VWAP 突破。
        
        简化计算：
        VWAP ≈ 成交额 / (成交量 × 100)
        突破条件：当前价 > VWAP 且上一轮在 VWAP 下方 且量比 > 1.5
        """
        code = row.get("代码", "")
        price = row.get("最新价", 0) or 0
        volume = row.get("成交量", 0) or 0  # 手
        turnover = row.get("成交额", 0) or 0  # 元
        volume_ratio = row.get("量比", 0) or 0
        
        if price <= 0 or volume <= 0 or turnover <= 0:
            return None
        
        # 计算当日 VWAP
        vwap = turnover / (volume * 100)
        
        # 判断当前位置
        current_pos = "above" if price > vwap else "below"
        prev_pos = self._prev_vwap_position.get(code, "unknown")
        
        # 更新位置
        self._prev_vwap_position[code] = current_pos
        
        # 突破检测：从下方穿越到上方 + 放量确认
        if prev_pos == "below" and current_pos == "above" and volume_ratio >= 1.5:
            diff_pct = (price - vwap) / vwap * 100
            
            return {
                "signal_type": "VWAP突破",
                "strength": min(1.0 + diff_pct / 2, 3.0),
                "reasons": [
                    f"放量上穿VWAP (VWAP {vwap:.2f}, 现价 {price:.2f})",
                    f"量比 {volume_ratio:.1f}",
                ],
                "raw_data": {
                    "vwap": round(vwap, 2),
                    "price": price,
                    "diff_pct": round(diff_pct, 2),
                    "volume_ratio": volume_ratio,
                }
            }
        
        return None
