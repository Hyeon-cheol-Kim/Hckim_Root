from langflow.custom import Component
from langflow.io import Output
from langflow.schema.message import Message


class VersionCheckComponent(Component):
    display_name = "Version Check"
    name = "VersionCheck"

    outputs = [Output(display_name="Result", name="result", method="run")]

    def run(self) -> Message:
        try:
            from importlib.metadata import version
            lf_ver = version("langflow")
        except Exception:
            lf_ver = "unknown"

        try:
            from importlib.metadata import version
            lf_base_ver = version("langflow-base")
        except Exception:
            lf_base_ver = "unknown"

        import sys
        msg = f"langflow: {lf_ver}\nlangflow-base: {lf_base_ver}\nPython: {sys.version}"
        print(msg)
        return Message(text=msg)
