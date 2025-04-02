import os
import sys
import runpy
import pathlib

import fire

class App:

    def ui(self):
        """Run UI"""
        os.chdir(pathlib.Path(__file__).parent / "ui")
        streamlit_app_path = pathlib.Path(__file__).parent / "ui" / "app.py"
        sys.argv = ["streamlit", "run", str(streamlit_app_path)]
        runpy.run_module("streamlit", run_name="__main__")

if __name__ == "__main__":
    fire.Fire(App)