# Historical ERN Google Sheet Extraction (Superseded)

> **Not a source of truth.** This directory is retained only as an audit
> artifact of the pre-workbook Google Sheet extraction.

## Production sources

- Asset-return and index CSVs in `data/ern/` are generated from
  `SWR_Toolbox_v2.0.xlsx` by `tools/ern/extract_workbook_returns.py`.
- The historical FFR segment in `data/ern/ffr.csv` is generated from
  `Timing-Leverage-Calc.xlsx`, sheet `Return Data`, column `K`
  (`K4:K1815`), by `tools/ern/extract_ffr_from_workbook.py`.
- The 2022-01 through 2026-08 FFR extension comes from
  `data/ern/raw/FEDFUNDS.csv` and is recorded separately in
  `data/ern/ffr.provenance.json`. The raw file is a local FRED snapshot; its
  acquisition path is not fully reproducible from repository evidence.
- `ffr_monthly.json` is a reconstructed research artifact, not the canonical
  workbook `K` series. It must not replace the historical FFR segment.
- The SWR cash series (`Asset Returns!I`) is a 3-month T-bill total-return
  index, not FFR, and must not be used as an FFR proxy.

## Source

- **Google Sheet**: [ERN SWR Toolbox](https://docs.google.com/spreadsheets/d/1QGrMm6XSGWBVLI8I_DOAeJV5whoCnSdmaR8toQB2Jz8/edit?gid=1084562995#gid=1084562995)
- **Tab**: Asset Returns (gid=1084562995)
- **Extraction Date**: 2026-09-15

## Files

| File | Description |
|------|-------------|
| `ern_asset_returns.csv` | Clean extracted data with columns: year, month, spx_tr_real, y10_bm_real, cpi, spx_tr_cum, y10_bm_cum, cape_shiller |
| `ern_asset_returns.provenance.json` | Source metadata, SHA256 hash, extraction details |

## Data Coverage

- **Historical data**: 1871-01 to 2026-06 (1866 months)
- **Forward extrapolation**: 2026-07 to 2076-12 (606 months)
- **Total**: 2472 months

## Forward Extrapolation Rules

| Zone | Period | SPX-TR Monthly | SPX-TR Annual | 10Y BM Monthly | 10Y BM Annual |
|------|--------|----------------|---------------|----------------|---------------|
| 1 | 2026-07 to 2036-06 | 0.33% | 4.03% | 0.21% | 2.55% |
| 2 | 2036-07 to 2076-12 | 0.45% | 5.54% | 0.19% | 2.30% |

## Usage

Production extraction:

```bash
python3 tools/ern/extract_workbook_returns.py \
  --workbook /path/to/SWR_Toolbox_v2.0.xlsx \
  --output-dir data/ern

python3 tools/ern/extract_ffr_from_workbook.py \
  --workbook /path/to/Timing-Leverage-Calc.xlsx \
  --output-dir data/ern
```
