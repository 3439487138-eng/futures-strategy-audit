import io
import json
import zipfile

import pandas as pd

from futures_audit.data import _parse_cffex_month, _parse_shfe_day


def test_parse_cffex_delivery_contracts_only():
    csv_text = (
        "合约代码,今开盘,最高价,最低价,成交量,成交金额,持仓量,持仓变化,今收盘,今结算,前结算,涨跌1,涨跌2,Delta\n"
        "IF2503,3900,3920,3890,100,1,200,5,3910,3908,3899,0,0,--\n"
        "IO2503-C-3900,1,2,1,1,1,1,0,1,1,1,0,0,0.5\n"
    ).encode("gb18030")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("20250102_1.csv", csv_text)
    rows, dates = _parse_cffex_month(buffer.getvalue(), "202501")
    assert dates == {"2025-01-02"}
    assert len(rows) == 1
    assert rows[0]["contract"] == "IF2503"
    assert rows[0]["open_interest"] == 200


def test_parse_shfe_delivery_contracts_only():
    row = {
        "PRODUCTGROUPID": "cu", "DELIVERYMONTH": "2503", "OPENPRICE": 70000,
        "HIGHESTPRICE": 70100, "LOWESTPRICE": 69900, "CLOSEPRICE": 70050,
        "SETTLEMENTPRICE": 70020, "PRESETTLEMENTPRICE": 69980, "VOLUME": 100,
        "OPENINTEREST": 200,
    }
    payload = json.dumps({"o_trade_day": "7830", "report_date": "20250102", "o_curinstrument": [row]}).encode()
    rows, observed = _parse_shfe_day(payload, pd.Timestamp("2025-01-02").date())
    assert observed == "2025-01-02"
    assert rows[0]["contract"] == "CU2503"
    assert rows[0]["settle"] == 70020
