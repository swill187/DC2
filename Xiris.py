import os
import subprocess
from typing import Optional

class XirisCamera:
    def __init__(self):
        self.process = None
        self.executable = os.path.join(os.path.dirname(__file__), 
                                     "Xiris Code", "XIR-1800Collection.exe")

    def check_connection(self) -> bool:
        """Check if Xiris camera is accessible."""
        try:
            result = subprocess.run(
                [self.executable, "--check"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            print(f"Error checking Xiris camera: {e}")
            return False

    def start_recording(self, output_path: str, formats: list = None) -> bool:
        """
        Start recording from the Xiris camera.
        formats: list of strings ('raw', 'png'). If None, both formats are enabled.
        """
        try:
            cmd = [self.executable, "--record", output_path]
            if formats:
                for fmt in formats:
                    if fmt in ['raw', 'png']:  # Only allow RAW and PNG formats
                        cmd.append(f"--{fmt}")
                    
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            return True
        except Exception as e:
            print(f"Error starting Xiris recording: {e}")
            return False

    def stop_recording(self):
        """Stop the recording process."""
        if self.process:
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                self.process = None
            except Exception as e:
                print(f"Error stopping Xiris recording: {e}")
