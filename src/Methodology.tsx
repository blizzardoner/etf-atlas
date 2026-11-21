export default function Methodology({ source }: { source: string[] }) {
  return (
    <section className="methodology">
      <div className="eyebrow">METHODOLOGY / 研究口径</div>
      <h3>看清口径，再看回报。</h3>
      <div className="methodology-grid">
        <div>
          <strong>01 · 价格与总回报，不混为一谈</strong>
          <p>
            价格涨跌幅按份额拆并调整，不含现金分红。仅在供应商提供可验证复权数据时展示总回报；价格指数不能冒充含分红指数。
          </p>
        </div>
        <div>
          <strong>02 · 现金分配，是历史而非承诺</strong>
          <p>
            TTM 为最近完整 12
            个月现金分配除以最近收盘价。分红事件未知、历史不足或抵税比例未知，均不估为零；收益不是未来预测。
          </p>
        </div>
        <div>
          <strong>03 · 同一基准，保留真实缺口</strong>
          <p>
            多资产从同一个有效交易日归一为
            100，并在共同截止日结束。区间随历史覆盖缩短，缺失交易日保留断点；本币表现不做汇率换算。
          </p>
        </div>
      </div>
      <details>
        <summary>查看数据快照的原始来源口径（保留供应商原文）</summary>
        {source.map((line, i) => (
          <p key={i}>{line}</p>
        ))}
      </details>
      <p>
        数据来自已完成的交易日。行情按交易日历核验最新应有收盘日期，并在明确时区的到期时间到达时标为滞后；长假不会仅因收盘日期较旧而滞后。仅无交易日历元数据时，采用快照或收盘日期超过 5 个自然日的回退规则。快照年龄另行提醒；无效或未来快照时间不能证明行情有效。实时刷新不会生成新行情，而是读取最新发布的有效快照。仅供研究，不构成投资建议。
      </p>
    </section>
  );
}
