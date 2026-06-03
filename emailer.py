"""Builds the HTML report (NASDAQ + TSX sections) and sends it via SMTP."""
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO, SMTP_PORT, SMTP_SERVER

DIRECTION_COLORS = {
    "BULLISH": "#1b873f",
    "MILD BULLISH": "#4ea96b",
    "NEUTRAL": "#888888",
    "MILD BEARISH": "#d97b3a",
    "BEARISH": "#c62828",
}


def _earnings_row(item: dict) -> str:
    a, s = item["analysis"], item["signal"]
    color = DIRECTION_COLORS.get(s["direction"], "#333")
    return f"""
      <tr>
        <td><b>{a['symbol']}</b><br><span style="color:#444;font-size:11px">{a.get('company_name','')}</span><br><span style="color:#999;font-size:10px">{item.get('timing','')}</span></td>
        <td>${a['current_price']}</td>
        <td>{a['return_3m_pct']}%</td>
        <td>{a['momentum_20d_pct']}%</td>
        <td>{a['rsi']}</td>
        <td>{a['price_vs_sma20_pct']}% / {a['price_vs_sma50_pct']}%</td>
        <td>{a['volatility_pct']}%</td>
        <td style="color:{color};font-weight:bold">{s['direction']}<br>
            <span style="font-weight:normal;color:#444;font-size:11px">score {s['score']}</span></td>
        <td style="font-size:11px;color:#444">{'; '.join(s['reasons'])}</td>
      </tr>
    """


def _earnings_table(exchange: str, scored: list[dict]) -> str:
    scored = sorted(scored, key=lambda x: x["signal"]["score"], reverse=True)
    rows = "\n".join(_earnings_row(x) for x in scored) or \
        f'<tr><td colspan="9" style="text-align:center;color:#888">No {exchange} earnings today.</td></tr>'
    return f"""
      <h3 style="margin-top:24px">{exchange} earnings today (sorted by signal)</h3>
      <table cellpadding="6" cellspacing="0" border="1" style="border-collapse:collapse;font-size:12px;width:100%">
        <thead style="background:#f3f3f3">
          <tr>
            <th>Ticker</th><th>Price</th><th>3M %</th><th>20D %</th>
            <th>RSI</th><th>vs SMA20 / 50</th><th>Vol (ann)</th>
            <th>Signal</th><th>Why</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    """


def _ipo_table(exchange: str, ipos: list[dict]) -> str:
    if not ipos:
        return ""
    rows = "".join(
        f"<tr><td><b>{i.get('symbol','N/A')}</b></td><td>{i.get('name','')}</td>"
        f"<td>{i.get('date','')}</td><td>{i.get('exchange','')}</td>"
        f"<td>{i.get('price_range','')}</td><td>{i.get('shares','')}</td>"
        f"<td>{i.get('status','')}</td></tr>"
        for i in ipos
    )
    return f"""
      <h3 style="margin-top:24px">{exchange} — upcoming IPOs (next 7 days)</h3>
      <table cellpadding="6" cellspacing="0" border="1" style="border-collapse:collapse;font-size:12px;width:100%">
        <thead style="background:#f3f3f3">
          <tr><th>Ticker</th><th>Name</th><th>Date</th><th>Exchange</th>
              <th>Price</th><th>Shares</th><th>Status</th></tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    """


class ReportEmailer:
    def build_html(self, scored_by_exch: dict[str, list[dict]],
                   ipos_by_exch: dict[str, list[dict]]) -> str:
        today = date.today().isoformat()

        # High-level summary
        parts = []
        total_e = 0
        total_bull = 0
        total_bear = 0
        for exch, lst in scored_by_exch.items():
            bull = sum(1 for x in lst if x["signal"]["score"] >= 2)
            bear = sum(1 for x in lst if x["signal"]["score"] <= -2)
            total_e += len(lst); total_bull += bull; total_bear += bear
            parts.append(f"<b>{exch}</b>: {len(lst)} reporting ({bull} bullish, {bear} bearish)")

        ipo_summary = " · ".join(
            f"{exch} {len(v)} IPO(s)" for exch, v in ipos_by_exch.items() if v
        )

        summary = " &nbsp;|&nbsp; ".join(parts)
        if ipo_summary:
            summary += f" &nbsp;|&nbsp; {ipo_summary}"

        # Build tables
        earnings_html = "".join(
            _earnings_table(exch, lst) for exch, lst in scored_by_exch.items()
        )
        ipo_html = "".join(
            _ipo_table(exch, lst) for exch, lst in ipos_by_exch.items()
        )

        return f"""
        <html><body style="font-family:-apple-system,Segoe UI,Arial,sans-serif;color:#222">
          <h2 style="margin-bottom:4px">Pre-Market Scanner — {today}</h2>
          <p style="color:#666;margin-top:0">{summary}</p>

          {earnings_html}
          {ipo_html}

          <p style="margin-top:24px;padding:12px;background:#fff8e1;border-left:4px solid #f9a825;font-size:12px;color:#555">
            <b>Disclaimer:</b> Automated technical-indicator screen, not investment advice or a price
            prediction. Earnings reactions are driven by surprise vs. expectations, which this tool does
            <i>not</i> measure — a technically bullish stock can still gap down on a soft guide. Newly
            priced IPOs have no price history. Do your own research and size positions accordingly.
          </p>
        </body></html>
        """

    def send(self, html: str, subject: str | None = None) -> None:
        if not (EMAIL_FROM and EMAIL_PASSWORD and EMAIL_TO):
            print("[email] SMTP creds missing; skipping send. Report saved locally.")
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject or f"Pre-Market Scanner — {date.today().isoformat()}"
        msg["From"] = EMAIL_FROM
        msg["To"] = ", ".join(EMAIL_TO)
        msg.attach(MIMEText(html, "html"))

        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as s:
                s.starttls()
                s.login(EMAIL_FROM, EMAIL_PASSWORD)
                s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
            print(f"[email] sent to {len(EMAIL_TO)} recipient(s).")
        except Exception as e:
            print(f"[email] send failed: {e}")
