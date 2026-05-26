# Bidding AI Simulator

Streamlit MVP for simulating Korean supervision-service bidding.

The app estimates adjustment-rate distributions, expected price ranges, minimum eligible bid ranges, and a single competitive bidding result based on participant count.

## Quick Start on Windows

1. Download or clone this repository.
2. Put your private historical bid file in the downloaded folder.
   - Supported names: `호수위바위.csv`, `호수위바위.xlsx`, or `호수위바위` folder containing `.csv` / `.xlsx` files.
   - These private files are intentionally ignored by Git and are not uploaded to GitHub.
3. Double-click `입찰AI_실행.bat`.
4. The app opens at `http://localhost:8502`.

The batch file automatically installs Python packages from `requirements.txt` if Streamlit is missing, restarts the local app server, and opens the browser.

If Python is not installed, the batch file first tries to install Python 3.11 with Windows `winget`.
If that fails, it opens the official Python download page. After installing Python manually, double-click `입찰AI_실행.bat` again.

## Main Features

- Automatically loads local historical bid files
- Required columns: `notice_id`, `title`, `base_price`, `expected_price`, `lower_rate`
- Korean column names such as `공고번호`, `공고명`, `기초금액`, `예정가격`, `낙찰하한율` are also accepted
- The current `호수위바위.xlsx` style is also accepted: `사업명`, `발주기관`, `개찰일`, `기초금액`, `세대수`, `예가/기초`
- Adjustment-rate quantiles: P10, P25, P50, P75, P90
- Expected price and minimum eligible bid range
- Participant-count-based competitive bidding simulation

## Updating Data

Keep entering new rows into the local historical bid file, save it, then press `F5` in the browser.
The app reloads the local file each time the page refreshes or the server restarts.

## Competitive Bidding Simulation

The single-run simulator follows this process:

1. Generate 15 preliminary price rates inside base price +/- 3% or +/- 2%.
2. Each participant selects 2 preliminary-price numbers.
3. The 4 most selected numbers determine the expected price.
4. Each participant bids `base_price * lower_rate * bidder_adjustment_rate`.
5. The winner is the lowest bid greater than or equal to `expected_price * lower_rate`.

## Notes

This is a decision-support simulator. It does not predict or guarantee a winning bid.

The included `sample_data.csv` is a small public-web sample and should be verified against original notices before practical use.
