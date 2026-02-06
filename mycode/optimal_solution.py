"""
最优因子解决方案：多因子自适应融合策略

策略概述：
本策略融合了多个维度的市场信息，构建了一个稳健的多因子模型：
1. 订单簿不平衡因子 - 捕捉盘口买卖力量对比
2. 短期动量反转因子 - 捕捉价格短期偏离均值的反转效应
3. 量价背离因子 - 识别量价不匹配的异常情况
4. 流动性因子 - 衡量交易成本和市场深度

核心创新：
- 多因子动态加权（根据市场波动率调整）
- 多时间尺度特征（充分利用15分钟窗口内的信息）
- 稳健性处理（极端值处理、标准化）

预期优势：
- 信息维度丰富，不依赖单一信号
- 自适应机制，适应不同市场环境
- 计算效率高，符合9小时时间限制
"""


def main(datasource, start_date, end_date):
    """
    多因子自适应融合策略
    
    核心思想：
    1. 订单簿不平衡 - 盘口买卖力量
    2. 短期动量反转 - 价格均值回归
    3. 量价背离 - 异常交易识别
    4. 流动性 - 交易成本
    5. 自适应权重 - 根据波动率动态调整
    
    Args:
        datasource (str): Datasource table name
        start_date (str): Start date in 'YYYY-MM-DD HH:MM:SS' format
        end_date (str): End date in 'YYYY-MM-DD HH:MM:SS' format

    Returns:
        pd.DataFrame: Factor data with columns ['date', 'instrument', 'factor']
    """
    import pandas as pd
    import dai

    sql = f"""
    -- 性能优化设置
    SET preserve_insertion_order=false;
    SET threads=4;
    
    WITH cte_snapshot AS (
        SELECT
            date, 
            instrument_id,
            price,
            volume,
            amount,
            
            -- 基础价格指标
            (ask_price1 + bid_price1) / 2.0 AS mid_price,
            ask_price1,
            bid_price1,
            
            -- 盘口量指标
            ask_volume1, bid_volume1,
            ask_volume2, bid_volume2,
            ask_volume3, bid_volume3,
            ask_volume4, bid_volume4,
            ask_volume5, bid_volume5,
            
            -- 交易日
            strftime(date, '%Y-%m-%d') AS trading_day,
            
            -- 15分钟时间段
            CASE 
                -- 上午时间段
                WHEN strftime(date, '%H%M') >= '0930' AND strftime(date, '%H%M') < '0945' THEN  94500
                WHEN strftime(date, '%H%M') >= '0945' AND strftime(date, '%H%M') < '1000' THEN 100000
                WHEN strftime(date, '%H%M') >= '1000' AND strftime(date, '%H%M') < '1015' THEN 101500
                WHEN strftime(date, '%H%M') >= '1015' AND strftime(date, '%H%M') < '1030' THEN 103000
                WHEN strftime(date, '%H%M') >= '1030' AND strftime(date, '%H%M') < '1045' THEN 104500
                WHEN strftime(date, '%H%M') >= '1045' AND strftime(date, '%H%M') < '1100' THEN 110000
                WHEN strftime(date, '%H%M') >= '1100' AND strftime(date, '%H%M') < '1115' THEN 111500
                WHEN strftime(date, '%H%M') >= '1115' AND strftime(date, '%H%M') <= '1130' THEN 113000
                
                -- 下午时间段
                WHEN strftime(date, '%H%M') >= '1300' AND strftime(date, '%H%M') < '1315' THEN 131500
                WHEN strftime(date, '%H%M') >= '1315' AND strftime(date, '%H%M') < '1330' THEN 133000
                WHEN strftime(date, '%H%M') >= '1330' AND strftime(date, '%H%M') < '1345' THEN 134500
                WHEN strftime(date, '%H%M') >= '1345' AND strftime(date, '%H%M') < '1400' THEN 140000
                WHEN strftime(date, '%H%M') >= '1400' AND strftime(date, '%H%M') < '1415' THEN 141500
                WHEN strftime(date, '%H%M') >= '1415' AND strftime(date, '%H%M') < '1430' THEN 143000
                WHEN strftime(date, '%H%M') >= '1430' AND strftime(date, '%H%M') < '1445' THEN 144500
                WHEN strftime(date, '%H%M') >= '1445' AND strftime(date, '%H%M') < '1457' THEN 150000
                ELSE -1
            END AS time_segment
        FROM {datasource}
        WHERE time_segment != -1
    ),
    
    -- 计算各类子因子
    cte_features AS (
        SELECT
            *,
            
            -- === 1. 订单簿特征 ===
            -- 加权买方力量（5档指数衰减加权）
            (
                COALESCE(bid_volume1, 0) * 1.0 + 
                COALESCE(bid_volume2, 0) * EXP(-0.3) + 
                COALESCE(bid_volume3, 0) * EXP(-0.6) + 
                COALESCE(bid_volume4, 0) * EXP(-0.9) + 
                COALESCE(bid_volume5, 0) * EXP(-1.2)
            ) AS weighted_bid,
            
            -- 加权卖方力量
            (
                COALESCE(ask_volume1, 0) * 1.0 + 
                COALESCE(ask_volume2, 0) * EXP(-0.3) + 
                COALESCE(ask_volume3, 0) * EXP(-0.6) + 
                COALESCE(ask_volume4, 0) * EXP(-0.9) + 
                COALESCE(ask_volume5, 0) * EXP(-1.2)
            ) AS weighted_ask,
            
            -- 订单簿不平衡度
            (weighted_bid - weighted_ask) / (weighted_bid + weighted_ask + 1e-8) AS order_imbalance,
            
            -- === 2. 流动性特征 ===
            -- 相对价差
            (ask_price1 - bid_price1) / (mid_price + 1e-8) AS relative_spread,
            
            -- 盘口深度
            (
                COALESCE(bid_volume1, 0) + COALESCE(bid_volume2, 0) + COALESCE(bid_volume3, 0) +
                COALESCE(ask_volume1, 0) + COALESCE(ask_volume2, 0) + COALESCE(ask_volume3, 0)
            ) AS total_depth,
            
            -- === 3. 价格特征 ===
            -- 前一时刻价格（用于计算收益率）
            LAG(mid_price, 1) OVER (
                PARTITION BY instrument_id, trading_day, time_segment 
                ORDER BY date
            ) AS prev_mid_price,
            
            -- === 4. 成交量特征 ===
            -- 前一时刻成交量
            LAG(volume, 1) OVER (
                PARTITION BY instrument_id, trading_day, time_segment 
                ORDER BY date
            ) AS prev_volume
        FROM cte_snapshot
    ),
    
    -- 计算收益率和成交量变化
    cte_returns AS (
        SELECT
            *,
            -- 瞬时收益率
            (mid_price - prev_mid_price) / (prev_mid_price + 1e-8) AS returns,
            
            -- 成交量变化
            (volume - prev_volume) AS volume_delta,
            
            -- 成交额变化率（成交量 × 价格）
            CASE
                WHEN prev_volume > 0 THEN (volume - prev_volume) / prev_volume
                ELSE 0
            END AS volume_change_rate
        FROM cte_features
        WHERE prev_mid_price IS NOT NULL
    ),
    
    -- 聚合到15分钟级别，计算各子因子
    cte_window AS (
        SELECT
            trading_day,
            time_segment,
            instrument_id,
            
            -- === 因子1: 订单簿压力因子 ===
            -- 最新的订单簿不平衡度（赋予更高权重）
            argMax(order_imbalance, date) AS last_imbalance,
            
            -- 窗口内平均不平衡度
            AVG(order_imbalance) AS avg_imbalance,
            
            -- 标准差（衡量稳定性）
            nanstd(order_imbalance) AS std_imbalance,
            
            -- 标准化的订单簿压力
            CASE
                WHEN std_imbalance > 0
                THEN (last_imbalance - avg_imbalance) / std_imbalance
                ELSE last_imbalance
            END AS factor_orderbook,
            
            -- === 因子2: 短期动量反转因子 ===
            -- 开盘和收盘价格
            argMin(mid_price, date) AS open_price,
            argMax(mid_price, date) AS close_price,
            
            -- 窗口内均价
            AVG(mid_price) AS avg_price,
            
            -- 动量 = 收盘价偏离均价的程度
            (close_price - avg_price) / (avg_price + 1e-8) AS raw_momentum,
            
            -- 反转因子（负号表示反转）
            -1 * raw_momentum AS factor_momentum,
            
            -- === 因子3: 量价背离因子 ===
            -- 计算量价相关性（样本数>=3时才计算）
            CASE
                WHEN COUNT(*) >= 3
                THEN COALESCE(CORR(returns, volume_change_rate), 0)
                ELSE 0
            END AS pv_correlation,
            
            -- 量价背离 = 负相关性（价涨量缩为异常）
            -1 * pv_correlation AS factor_pv_divergence,
            
            -- === 因子4: 流动性因子 ===
            -- 平均相对价差（越大流动性越差）
            AVG(relative_spread) AS avg_spread,
            
            -- 平均盘口深度（越大流动性越好）
            AVG(total_depth) AS avg_depth,
            
            -- 流动性综合指标（价差小、深度大为好）
            -1 * (avg_spread / (LOG(avg_depth + 1) + 1e-8)) AS factor_liquidity,
            
            -- === 市场状态指标 ===
            -- 价格波动率（用于自适应权重）
            nanstd(returns) AS volatility,
            
            -- 成交量标准差
            nanstd(volume_change_rate) AS volume_volatility,
            
            -- 波动率阈值（80%分位数）
            quantile(returns, 0.8) AS volatility_threshold
        FROM cte_returns
        GROUP BY instrument_id, trading_day, time_segment
    ),
    
    -- 最终因子合成
    cte_final AS (
        SELECT
            trading_day,
            time_segment,
            instrument_id,
            
            -- === 自适应权重计算 ===
            -- 高波动时：增加订单簿因子权重，降低动量因子权重
            -- 低波动时：均衡权重
            CASE
                WHEN volatility > volatility_threshold THEN 0.45  -- 高波动
                ELSE 0.30  -- 低波动
            END AS w_orderbook,
            
            CASE
                WHEN volatility > volatility_threshold THEN 0.20
                ELSE 0.30
            END AS w_momentum,
            
            CASE
                WHEN volatility > volatility_threshold THEN 0.25
                ELSE 0.25
            END AS w_pv,
            
            CASE
                WHEN volatility > volatility_threshold THEN 0.10
                ELSE 0.15
            END AS w_liquidity,
            
            -- === 多因子加权合成 ===
            (
                w_orderbook * factor_orderbook +
                w_momentum * factor_momentum +
                w_pv * factor_pv_divergence +
                w_liquidity * factor_liquidity
            ) AS raw_factor,
            
            -- === 因子后处理 ===
            -- 1. tanh压缩到[-1, 1]，防止极端值
            -- 2. 乘以3是为了在tanh之前放大信号
            TANH(raw_factor * 3.0) AS factor
        FROM cte_window
    )
    
    -- 输出最终结果
    SELECT
        CAST(CONCAT(
            f.trading_day,
            ' ',
            strftime(strptime(LPAD(f.time_segment, 6, '0'), '%H%M%S'), '%H:%M:%S')
        ) AS DATETIME) AS date,
        all_instruments.instrument,
        f.factor
    FROM cte_final f
    LEFT JOIN all_instruments USING (instrument_id)
    ORDER BY date, instrument
    """

    df = dai.query(sql, filters={'date': [start_date, end_date]}).df()
    return df


if __name__ == '__main__':
    """
    本地开发测试模块
    
    用途：
    1. 验证因子计算逻辑
    2. 评估因子性能
    3. 调试和优化
    
    提示：
    - 调整日期范围测试不同时期
    - 使用分块计算避免内存溢出
    - 通过eval_dwc模块评估因子效果
    """
    from bigmodule import M
    from datetime import datetime
    import pandas as pd
    import structlog
    import gc

    logger = structlog.get_logger()
    
    # 数据源配置
    datasource = 'cpt_dwc_2026_stock_hs300_snapshot'
    
    # ==========================================
    # 测试配置：可以先用小范围测试，确认无误后再跑全量
    # ==========================================
    # 小范围测试（快速验证）
    # full_start_date = '2023-01-01'
    # full_end_date = '2023-01-31'
    
    # 完整测试（提交前）
    full_start_date = '2023-01-01'
    full_end_date = '2024-12-31'
    
    # 分块计算（按月）以避免内存问题
    date_ranges = pd.date_range(start=full_start_date, end=full_end_date, freq='MS')
    all_results = []
    
    logger.info(f"\n{'='*60}")
    logger.info(f"🚀 多因子自适应融合策略 - 回测启动")
    logger.info(f"{'='*60}")
    logger.info(f"📅 测试周期: {full_start_date} 至 {full_end_date}")
    logger.info(f"📊 数据源: {datasource}")
    logger.info(f"🔧 分块数量: {len(date_ranges)} 个月")
    logger.info(f"{'='*60}\n")
    
    # 分块处理
    for i, start_dt in enumerate(date_ranges, 1):
        current_start = start_dt.strftime('%Y-%m-%d 00:00:00')
        current_end = (start_dt + pd.offsets.MonthEnd(0)).strftime('%Y-%m-%d 23:59:59')
        
        logger.info(f"[{i}/{len(date_ranges)}] 处理分块: {current_start[:10]} => {current_end[:10]}")
        
        try:
            t1 = datetime.now()
            df_chunk = main(datasource, current_start, current_end)
            t2 = datetime.now()
            
            if df_chunk is not None and not df_chunk.empty:
                all_results.append(df_chunk)
                elapsed = (t2 - t1).total_seconds()
                logger.info(f"  ✅ 完成! 数据行数: {len(df_chunk):,} | 耗时: {elapsed:.1f}秒\n")
            else:
                logger.warning(f"  ⚠️  分块为空: {current_start[:10]}\n")
            
            # 清理内存
            del df_chunk
            gc.collect()
            
        except Exception as e:
            logger.error(f"  ❌ 错误: {current_start[:10]} - {str(e)}\n")
    
    # 合并结果
    if all_results:
        logger.info(f"\n{'='*60}")
        logger.info("🧩 合并所有分块数据...")
        final_data = pd.concat(all_results, ignore_index=True)
        final_data.sort_values(by=['date', 'instrument'], inplace=True)
        
        logger.info(f"✅ 合并完成!")
        logger.info(f"{'='*60}")
        logger.info(f"\n📈 最终数据统计:")
        logger.info(f"  - 总行数: {final_data.shape[0]:,}")
        logger.info(f"  - 股票数: {final_data['instrument'].nunique()}")
        logger.info(f"  - 交易日数: {final_data['date'].nunique()}")
        logger.info(f"  - 因子均值: {final_data['factor'].mean():.6f}")
        logger.info(f"  - 因子标准差: {final_data['factor'].std():.6f}")
        logger.info(f"  - 因子缺失率: {final_data['factor'].isna().sum() / len(final_data) * 100:.2f}%")
        logger.info(f"\n📊 数据样本 (前5行):")
        logger.info(f"\n{final_data.head().to_string()}")
        
        # 因子评估
        logger.info(f"\n{'='*60}")
        logger.info("📊 开始因子评估...")
        logger.info(f"{'='*60}\n")
        
        try:
            results = M.eval_dwc._latest(data=final_data)
            logger.info("\n✅ 因子评估完成! 请查看评估结果。")
        except Exception as e:
            logger.warning(f"\n⚠️  评估模块执行失败（本地环境可能缺少特定模块）: {e}")
            logger.info("💡 提示：在线平台会自动完成评估，无需担心。")
    else:
        logger.error("\n❌ 没有生成任何数据，请检查配置和数据源。")
