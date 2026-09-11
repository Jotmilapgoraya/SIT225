import logging

logging.getLogger("werkzeug").setLevel(logging.ERROR)
from arduino_iot_cloud import ArduinoCloudClient
from credentials import DEVICE_ID, SECRET_KEY

from dash import Dash, dcc, html, Input, Output
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go

from collections import deque
from threading import Thread, Lock
from datetime import datetime


# ============================================================
# 1. REUSABLE SMOOTH STREAM WRAPPER
# ============================================================

class SmoothDashStream:
    """
    Reusable wrapper for buffering continuous sensor data
    and preparing it for Plotly Dash extendData updates.

    Parameters
    ----------
    channels : list
        Names of the data channels being streamed.
        Example: ["x", "y", "z"]

    max_points : int
        Maximum number of points displayed on the graph.
    """

    def __init__(self, channels, max_points=200):

        self.channels = channels
        self.max_points = max_points

        # Temporary buffer for newly arrived samples
        self.buffer = deque()

        # Prevent Arduino and Dash threads from accessing
        # the buffer at exactly the same time
        self.lock = Lock()


    def add_sample(self, timestamp=None, **values):
        """
        Add one new sensor sample to the buffer.

        Example:
        stream.add_sample(
            x=0.12,
            y=-0.45,
            z=0.88
        )
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
        Remove all currently buffered samples and convert
        them into the format required by Plotly Dash extendData.

        Returns
        -------
        tuple or None

        (
            new_data,
            trace_indexes,
            max_points
        )

        Returns None when no fresh samples are available.
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

            # Same timestamps are supplied to each Plotly trace
            x_data.append(times)

            # Extract values for this particular channel
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
# 2. CREATE STREAM OBJECT
# ============================================================

stream = SmoothDashStream(
    channels=["x", "y", "z"],
    max_points=200
)


# ============================================================
# 3. STORE LATEST ARDUINO CLOUD VALUES
# ============================================================

latest_values = {
    "x": None,
    "y": None,
    "z": None
}


# ============================================================
# 4. ARDUINO CLOUD CALLBACK FUNCTIONS
# ============================================================

def on_x_changed(client, value):
    """
    Called whenever Accelerometer_X receives a new value.
    """

    latest_values["x"] = float(value)


def on_y_changed(client, value):
    """
    Called whenever Accelerometer_Y receives a new value.
    """

    latest_values["y"] = float(value)


def on_z_changed(client, value):
    """
    Called whenever Accelerometer_Z receives a new value.

    When X, Y and Z are all available, one complete
    XYZ sample is added to SmoothDashStream.
    """

    latest_values["z"] = float(value)

    if (
        latest_values["x"] is not None
        and latest_values["y"] is not None
        and latest_values["z"] is not None
    ):

        stream.add_sample(
            x=latest_values["x"],
            y=latest_values["y"],
            z=latest_values["z"]
        )

        print(
            f"X: {latest_values['x']:.3f} | "
            f"Y: {latest_values['y']:.3f} | "
            f"Z: {latest_values['z']:.3f}"
        )


# ============================================================
# 5. CONNECT PYTHON DEVICE TO ARDUINO IOT CLOUD
# ============================================================

cloud_client = ArduinoCloudClient(
    device_id=DEVICE_ID,
    username=DEVICE_ID,
    password=SECRET_KEY
)


# Register the three synced Arduino Cloud variables.
# Names must exactly match the variables in Arduino Cloud.

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
    """
    Run the Arduino Cloud connection.
    """

    print("Connecting to Arduino Cloud...")
    cloud_client.start()


# Arduino Cloud must run independently of the Dash server.
cloud_thread = Thread(
    target=run_cloud,
    daemon=True
)

cloud_thread.start()


# ============================================================
# 6. CREATE DASH APPLICATION
# ============================================================

app = Dash(__name__)


# ============================================================
# 7. CREATE INITIAL EMPTY PLOTLY GRAPH
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
# 8. DASH PAGE LAYOUT
# ============================================================

app.layout = html.Div([

    html.H1(
        "SIT225 - Live Accelerometer Dashboard"
    ),

    html.P(
        "Live smartphone accelerometer data streamed "
        "through Arduino IoT Cloud."
    ),

    dcc.Graph(
        id="accelerometer-graph",
        figure=figure
    ),

    # Check for fresh data every 250 milliseconds
    dcc.Interval(
        id="update-timer",
        interval=250,
        n_intervals=0
    )

])


# ============================================================
# 9. SMOOTH DASH UPDATE CALLBACK
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
    """
    Update only the new portion of the graph.

    extendData avoids rebuilding the entire Plotly figure
    whenever fresh sensor values arrive.
    """

    result = stream.get_extend_data()

    if result is None:
        raise PreventUpdate

    return result


# ============================================================
# 10. RUN DASH SERVER
# ============================================================

if __name__ == "__main__":

    print(
        "Dash is running on "
        "http://127.0.0.1:8051/"
    )

    app.run(
        debug=False,
        port=8051
    )