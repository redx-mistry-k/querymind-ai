from io import BytesIO

import pandas as pd

from frontend.components.exports import rows_to_csv, rows_to_xlsx


def test_csv_and_xlsx_exports_preserve_actual_rows():
    rows = [
        {"customer": "Maya Shah", "revenue": 1250.5},
        {"customer": "Noah Kim", "revenue": 999.25},
    ]
    columns = ["customer", "revenue"]
    csv_frame = pd.read_csv(BytesIO(rows_to_csv(rows, columns)))
    xlsx_frame = pd.read_excel(BytesIO(rows_to_xlsx(rows, columns)))
    expected = pd.DataFrame(rows, columns=columns)
    pd.testing.assert_frame_equal(csv_frame, expected)
    pd.testing.assert_frame_equal(xlsx_frame, expected)
