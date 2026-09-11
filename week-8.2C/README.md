# SIT225 Task 5C - Continuous Accelerometer Visualisation

This folder contains the implementation for SIT225 Task 5C.

The project streams smartphone accelerometer X, Y and Z data through Arduino IoT Cloud to a Python application and displays the data continuously using Plotly Dash.

## Main file

- `smooth_dashboard.py` - receives accelerometer data and updates the Plotly Dash graph using a reusable `SmoothDashStream` wrapper.

## Security

Arduino IoT Cloud credentials are stored separately and are not included in this repository.
