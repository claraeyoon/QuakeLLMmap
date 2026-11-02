from __future__ import annotations
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

class ShakeMapRunner:
    """
    Orchestrates execution of the USGS ShakeMap v4 CLI commands:
    `shake <event_id> assemble`
    `shake <event_id> model`
    `shake <event_id> gridxml`
    `shake <event_id> contour`
    `shake <event_id> mapping`
    """

    def __init__(self, shakemap_install_dir: Optional[str | Path] = None):
        self.install_dir = Path(shakemap_install_dir) if shakemap_install_dir else None
        self.shake_binary = shutil.which("shake")

    def is_shakemap_installed(self) -> bool:
        return self.shake_binary is not None

    def prepare_event_folder(self, event_id: str, workspace_data_dir: Path, agent_dat_json: Path) -> Path:
        """Sets up the current/ directory with event.xml, fault, and the agent *_dat.json."""
        event_dir = workspace_data_dir / event_id / "current"
        event_dir.mkdir(parents=True, exist_ok=True)

        # Copy agent observation file into current/
        target_dat = event_dir / "agent_mmi_dat.json"
        shutil.copy2(agent_dat_json, target_dat)
        return event_dir

    def run_pipeline(self, event_id: str) -> Dict[str, Any]:
        if not self.is_shakemap_installed():
            return {
                "status": "shakemap_cli_not_found",
                "message": (
                    "USGS 'shake' CLI not detected in system PATH. "
                    "The agent observations have been formatted and exported to the official "
                    "USGS ShakeMap v4 Input Data Specification (*_dat.json). "
                    "To compute the alternative ShakeMap, install USGS ShakeMap v4 from "
                    "https://code.usgs.gov/ghsc/esi/shakemap and run 'shake <event_id> assemble && shake <event_id> model'."
                )
            }

        steps = ["assemble", "model", "gridxml", "contour", "mapping"]
        log = []
        for step in steps:
            try:
                cmd = [self.shake_binary, event_id, step]
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                log.append(f"✅ {step} succeeded")
            except subprocess.CalledProcessError as e:
                log.append(f"❌ {step} failed: {e.stderr}")
                return {"status": "error", "failed_step": step, "log": log}

        return {"status": "success", "log": log}
