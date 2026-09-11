from arduino_iot_cloud import ArduinoCloudClient
from credentials import DEVICE_ID, SECRET_KEY

from dash import Dash, dcc, html, Input, Output
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go

from collections import deque
from threading import Thread, Lock
from datetime import datetime

import csv
import os
import logging


# ============================================================
# 1. CLEANER TERMINAL OUTPUT
# ============================================================

logging.getLogger("werkzeug").setLevel(logging.ERROR)


# ============================================================
# 2. REUSABLE SMOOTH STREAM WRAPPER
# ============================================================

class SmoothDashStream:
    """
    Reusable wrapper for buffering continuous sensor data
    and preparing it for Plotly Dash extendData updates.
    """

    def __init__(self, channels, max_points=200):

        self.channels = channels
        self.max_points = max_points

        self.buffer = deque()
        self.lock = Lock()


    def add_sample(self, timestamp=None, **values):
        """
        Add one new sensor sample to the buffer.
        """

        if timestamp is None:
            timestamp = datetime.now()

        sample = {
            "time": timestamp
        }

        for channel in self.channels:
            sample[channel] = values[channel]

        with self.lock:
            self.buffer.append(sample)


    def get_extend_data(self):
        """
        Retrieve new buffered samples and convert them
        into the format required by Plotly Dash extendData.
        """

        with self.lock:

            if not self.buffer:
                return None

            samples = list(self.buffer)
            self.buffer.clear()

        times = [
            sample["time"]
            for sample in samples
        ]

        x_data = []
        y_data = []

        for channel in self.channels:

            x_data.append(times)

            y_data.append([
                sample[channel]
                for sample in samples
            ])

        new_data = {
            "x": x_data,
            "y": y_data
        }

        trace_indexes = list(
            range(len(self.channels))
        )

        return (
            new_data,
            trace_indexes,
            self.max_points
        )


# ============================================================
# 3. CREATE STREAM OBJECT
# ============================================================

stream = SmoothDashStream(
    channels=["x", "y", "z"],
    max_points=200
)


# ============================================================
# 4. STORE LATEST CLOUD VALUES
# ============================================================

latest_values = {
    "x": None,
    "y": None,
    "z": None
}


# ============================================================
# 5. CSV FILE SETUP
# ============================================================

CSV_FILE = "accelerometer_data.csv"

if not os.path.exists(CSV_FILE):

    with open(
        CSV_FILE,
        "w",
        newline=""
    ) as file:

        writer = csv.writer(file)

        writer.writerow([
            "timestamp",
            "x",
            "y",
            "z"
        ])


# ============================================================
# 6. ARDUINO CLOUD CALLBACK FUNCTIONS
# ============================================================

def on_x_changed(client, value):
    """
    Called whenever Accelerometer_X changes.
    """

    latest_values["x"] = float(value)


def on_y_changed(client, value):
    """
    Called whenever Accelerometer_Y changes.
    """

    latest_values["y"] = float(value)


def on_z_changed(client, value):
    """
    Called whenever Accelerometer_Z changes.

    When all three values are available,
    one complete sample is stored.
    """

    latest_values["z"] = float(value)

    if (
        latest_values["x"] is not None
        and latest_values["y"] is not None
        and latest_values["z"] is not None
    ):

        timestamp = datetime.now()

        # Add sample to reusable dashboard buffer
        stream.add_sample(
            timestamp=timestamp,
            x=latest_values["x"],
            y=latest_values["y"],
            z=latest_values["z"]
        )

        # Save the same sample to CSV
        with open(
            CSV_FILE,
            "a",
            newline=""
        ) as file:

            writer = csv.writer(file)

            writer.writerow([
                timestamp.isoformat(),
                latest_values["x"],
                latest_values["y"],
                latest_values["z"]
            ])

        # Show sample in terminal
        print(
            f"X: {latest_values['x']:.3f} | "
            f"Y: {latest_values['y']:.3f} | "
            f"Z: {latest_values['z']:.3f}"
        )


# ============================================================
# 7. CONNECT TO ARDUINO IOT CLOUD
# ============================================================

cloud_client = ArduinoCloudClient(
    device_id=DEVICE_ID,
    username=DEVICE_ID,
    password=SECRET_KEY
)


cloud_client.register(
    "Accelerometer_X",
    value=None,
    on_write=on_x_changed
)

cloud_client.register(
    "Accelerometer_Y",
    value=None,
    on_write=on_y_changed
)

cloud_client.register(
    "Accelerometer_Z",
    value=None,
    on_write=on_z_changed
)


def run_cloud():

    print("Connecting to Arduino Cloud...")

    cloud_client.start()


cloud_thread = Thread(
    target=run_cloud,
    daemon=True
)

cloud_thread.start()


# ============================================================
# 8. CREATE DASH APPLICATION
# ============================================================

app = Dash(__name__)


# ============================================================
# 9. INITIAL PLOTLY FIGURE
# ============================================================

figure = go.Figure()


figure.add_trace(
    go.Scatter(
        x=[],
        y=[],
        mode="lines",
        name="Accelerometer X"
    )
)


figure.add_trace(
    go.Scatter(
        x=[],
        y=[],
        mode="lines",
        name="Accelerometer Y"
    )
)


figure.add_trace(
    go.Scatter(
        x=[],
        y=[],
        mode="lines",
        name="Accelerometer Z"
    )
)


figure.update_layout(
    title="Live Smartphone Accelerometer",
    xaxis_title="Time",
    yaxis_title="Acceleration",
    uirevision="keep"
)


# ============================================================
# 10. DASH PAGE LAYOUT
# ============================================================

app.layout = html.Div([

    html.H1(
        "SIT225 - Live Accelerometer Dashboard"
    ),

    html.P(
        "Live smartphone accelerometer data "
        "streamed through Arduino IoT Cloud."
    ),

    dcc.Graph(
        id="accelerometer-graph",
        figure=figure
    ),

    dcc.Interval(
        id="update-timer",
        interval=250,
        n_intervals=0
    )

])


# ============================================================
# 11. SMOOTH GRAPH UPDATE CALLBACK
# ============================================================

@app.callback(
    Output(
        "accelerometer-graph",
        "extendData"
    ),
    Input(
        "update-timer",
        "n_intervals"
    )
)
def update_graph(n):

    result = stream.get_extend_data()

    if result is None:
        raise PreventUpdate

    return result


# ============================================================
# 12. RUN DASH SERVER
# ============================================================

if __name__ == "__main__":

    print(
        "Dash is running on "
        "http://127.0.0.1:8051/"
    )

    print(
        f"Accelerometer data is being saved to: "
        f"{CSV_FILE}"
    )

    app.run(
        debug=False,
        port=8051
    )