import requests
import json
import os
from typing import Optional, Dict, Any

class KlipperRemoteController:
    """
    Remote controller for Klipper via Moonraker API
    """
    
    def __init__(self, host: str, port: int = 7125):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        
    def test_connection(self) -> bool:
        """Test if Klipper/Moonraker is accessible"""
        try:
            response = requests.get(f"{self.base_url}/server/info", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False
    
    def send_gcode(self, gcode_command: str) -> Dict[str, Any]:
        """Send a single G-code command to Klipper"""
        try:
            url = f"{self.base_url}/printer/gcode/script"
            data = {"script": gcode_command}
            response = requests.post(url, json=data, timeout=10)
            response.raise_for_status()
            return {"success": True, "response": response.json()}
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}
    
    def upload_file(self, file_path: str, target_folder: str = "gcodes") -> Dict[str, Any]:
        """Upload a G-code file to Klipper"""
        try:
            if not os.path.exists(file_path):
                return {"success": False, "error": "File not found"}
            
            with open(file_path, 'rb') as f:
                files = {'file': (os.path.basename(file_path), f, 'text/plain')}
                data = {'root': target_folder}
                
                url = f"{self.base_url}/server/files/upload"
                response = requests.post(url, files=files, data=data, timeout=30)
                response.raise_for_status()
                
                return {"success": True, "response": response.json()}
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}
    
    def start_print(self, filename: str) -> Dict[str, Any]:
        """Start printing a file"""
        try:
            url = f"{self.base_url}/printer/print/start"
            data = {"filename": filename}
            response = requests.post(url, json=data, timeout=10)
            response.raise_for_status()
            return {"success": True, "response": response.json()}
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}
    
    def upload_and_print(self, file_path: str) -> Dict[str, Any]:
        """Upload file and immediately start printing"""
        # Upload file first
        upload_result = self.upload_file(file_path)
        if not upload_result["success"]:
            return upload_result
        
        # Extract filename from upload response
        try:
            filename = upload_result["response"]["item"]["path"]
            return self.start_print(filename)
        except KeyError:
            return {"success": False, "error": "Could not determine uploaded filename"}
    
    def get_printer_status(self) -> Dict[str, Any]:
        """Get current printer status"""
        try:
            url = f"{self.base_url}/printer/objects/query"
            params = {
                "print_stats": None,
                "toolhead": None,
                "extruder": None
            }
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            return {"success": True, "status": response.json()}
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}
    
    def emergency_stop(self) -> Dict[str, Any]:
        """Emergency stop the printer"""
        return self.send_gcode("M112")
    
    def home_all_axes(self) -> Dict[str, Any]:
        """Home all axes"""
        return self.send_gcode("G28")
    
    def set_manual_stepper(self, stepper_name: str, position: float) -> Dict[str, Any]:
        """Move a manual stepper (like B-axis)"""
        command = f"MANUAL_STEPPER STEPPER={stepper_name} MOVE={position}"
        return self.send_gcode(command)

# Example usage and testing
if __name__ == "__main__":
    # Replace with your Raspberry Pi's IP address
    PRINTER_IP = "172.20.10.4"  # Change this!
    
    controller = KlipperRemoteController(PRINTER_IP)
    
    # Test connection
    if controller.test_connection():
        print("✅ Connected to Klipper successfully!")
        
        # Get printer status
        status = controller.get_printer_status()
        if status["success"]:
            print("📊 Printer Status:", status["status"])
        
        # Example: Move B-axis stepper
        result = controller.set_manual_stepper("b_stepper", 45.0)
        if result["success"]:
            print("🔄 B-axis moved successfully!")
        else:
            print("❌ B-axis move failed:", result["error"])
            
    else:
        print("❌ Could not connect to Klipper")
        print(f"Make sure Moonraker is running on {PRINTER_IP}:7125") 
