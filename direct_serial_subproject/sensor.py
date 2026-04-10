"""
Module for reading temperature data from the serial sensor.
"""

import serial
import json
import logging
import threading
import time
from datetime import datetime
from typing import Optional, Dict
from config import JSON_FILE

logger = logging.getLogger(__name__)


class TemperatureSensor:
    """Handles reading temperature data from a serial temperature sensor."""
    
    def __init__(self, port: str, baud_rate: int = 9600, 
                 timeout: int = 2):
        """
        Initialize the temperature sensor connection.
        
        Args:
            port: Serial port (e.g., 'COM7')
            baud_rate: Baud rate for serial communication (default: 9600)
            timeout: Read timeout in seconds (default: 2)
        """
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.ser = None
        
    def connect(self) -> bool:
        """
        Establish serial connection to the sensor.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=self.timeout)
            logger.info(f"Connected to sensor on {self.port} at {self.baud_rate} baud")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to sensor: {e}")
            return False
    
    def read_temperature_with_id(self) -> Optional[tuple]:
        """
        Read temperature with sensor ID from the serial data.
        
        Expected formats:
        - Multi-sensor: "SENSOR_1:72.34" or "sensor_1:72.34"
        - Legacy: "Temperature (F): 72.34" (assumes sensor_1)
        
        Returns:
            Tuple of (sensor_id, temperature_f) or None if read fails
        """
        if not self.ser or not self.ser.is_open:
            logger.warning("Serial connection is not open")
            return None
        
        try:
            # Discard stale buffered data, keep only fresh readings
            self.ser.reset_input_buffer()
            
            # Read one fresh line
            line = self.ser.readline().decode().strip()
            if not line:
                logger.debug("No data received from sensor (timeout)")
                return None
            
            # Parse format: "SENSOR_X:72.34" or "sensor_x:72.34"
            if ":" in line:
                parts = line.split(":")
                if len(parts) == 2:
                    sensor_id = parts[0].strip().lower()  # Normalize to lowercase
                    temp_f = float(parts[1].strip())
                    logger.debug(f"Read {sensor_id}: {temp_f}°F")
                    return (sensor_id, temp_f)
            
            # Fallback: Legacy format "Temperature (F): 72.34" - assume sensor_1
            if "Temperature" in line or "temperature" in line:
                temp_f = float(line.split()[-1])
                logger.debug(f"Read temperature (legacy format): {temp_f}°F, defaulting to sensor_1")
                return ("sensor_1", temp_f)
            
            logger.warning(f"Unrecognized format: {line}")
            return None
            
        except ValueError as e:
            logger.error(f"Failed to parse temperature value from '{line}': {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading temperature: {e}")
            return None
    
    def read_temperature(self) -> Optional[float]:
        """
        Read temperature only (legacy method for backward compatibility).
        
        Returns:
            Temperature in Fahrenheit, or None if read fails
        """
        result = self.read_temperature_with_id()
        return result[1] if result else None
    
    def disconnect(self):
        """Close the serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            logger.info("Disconnected from sensor")


class TemperatureDataStore:
    """Handles reading and writing temperature data to JSON file for multiple sensors."""
    
    def __init__(self, json_file: str = JSON_FILE):
        """
        Initialize the data store.
        
        Args:
            json_file: Path to the JSON file for storing temperature data
        """
        self.json_file = json_file
    
    def save_temperature(self, sensor_id: str, temperature_f: float) -> bool:
        """
        Save temperature reading for a specific sensor to JSON file.
        
        Maintains a multi-sensor structure: {sensor_1: {temp, timestamp}, sensor_2: {...}}
        
        Args:
            sensor_id: Unique sensor identifier (e.g., 'sensor_1')
            temperature_f: Temperature in Fahrenheit
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Load existing data to preserve other sensors
            try:
                with open(self.json_file, "r") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                data = {}
            
            # Update this sensor's data
            data[sensor_id] = {
                "temperature_F": temperature_f,
                "last_updated": datetime.utcnow().isoformat()
            }
            
            # Write back to file
            with open(self.json_file, "w") as f:
                json.dump(data, f, indent=4)
            logger.debug(f"Saved temperature for {sensor_id}: {temperature_f}°F")
            return True
        except Exception as e:
            logger.error(f"Failed to save temperature to JSON: {e}")
            return False
    
    def load_temperature(self, sensor_id: str) -> Optional[float]:
        """
        Load the latest temperature for a specific sensor from JSON file.
        
        Args:
            sensor_id: Unique sensor identifier (e.g., 'sensor_1')
        
        Returns:
            Temperature in Fahrenheit, or None if not found or invalid
        """
        try:
            with open(self.json_file, "r") as f:
                data = json.load(f)
            sensor_data = data.get(sensor_id, {})
            temp = sensor_data.get("temperature_F")
            logger.debug(f"Loaded temperature for {sensor_id}: {temp}°F")
            return temp
        except FileNotFoundError:
            logger.warning(f"JSON file not found: {self.json_file}")
            return None
        except Exception as e:
            logger.error(f"Failed to load temperature from JSON: {e}")
            return None
    
    def load_all_temperatures(self) -> Dict[str, dict]:
        """
        Load all sensor readings from JSON file.
        
        Returns:
            Dictionary with all sensor readings: {sensor_id: {temp, timestamp, last_updated}}
        """
        try:
            with open(self.json_file, "r") as f:
                data = json.load(f)
            return data
        except FileNotFoundError:
            logger.warning(f"JSON file not found: {self.json_file}")
            return {}
        except Exception as e:
            logger.error(f"Failed to load temperatures from JSON: {e}")
            return {}


class ContinuousTemperatureReader:
    """
    Runs a background thread to continuously read temperature from a sensor
    and save to JSON file at regular intervals.
    
    Note: When using shared COM port (multiple sensors on one receiver),
    the sensor_id from the serial data takes precedence over the config sensor_id.
    """
    
    def __init__(self, expected_sensor_ids: list, sensor: TemperatureSensor, 
                 data_store: TemperatureDataStore, read_interval: int = 5):
        """
        Initialize the continuous reader.
        
        Args:
            expected_sensor_ids: List of sensor IDs expected from this COM port (e.g., ['sensor_1', 'sensor_2'])
            sensor: TemperatureSensor instance to read from
            data_store: TemperatureDataStore instance to save to
            read_interval: Seconds between reads (default: 5)
        """
        self.expected_sensor_ids = expected_sensor_ids
        self.sensor = sensor
        self.data_store = data_store
        self.read_interval = read_interval
        self.is_running = False
        self.thread = None
    
    def start(self):
        """Start the background reading thread."""
        if self.is_running:
            logger.warning(f"Reader already running for {self.expected_sensor_ids}")
            return
        
        self.is_running = True
        self.thread = threading.Thread(
            target=self._read_loop,
            name=f"ContinuousReader-{','.join(self.expected_sensor_ids)}",
            daemon=True
        )
        self.thread.start()
        logger.info(f"Started continuous reading thread for sensors: {', '.join(self.expected_sensor_ids)}")
    
    def stop(self):
        """Stop the background reading thread."""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info(f"Stopped continuous reading thread for sensors: {', '.join(self.expected_sensor_ids)}")
    
    def _read_loop(self):
        """Main reading loop (runs in background thread)."""
        while self.is_running:
            try:
                result = self.sensor.read_temperature_with_id()
                if result is not None:
                    sensor_id, temperature = result
                    
                    # Log all received data
                    logger.info(f"Received: {sensor_id}: {temperature}°F")
                    
                    # Validate sensor_id format (should be like "sensor_1", "sensor_2", etc.)
                    if not sensor_id.startswith("sensor_"):
                        logger.warning(f"Ignoring invalid sensor ID format: '{sensor_id}' (must start with 'sensor_')")
                        time.sleep(self.read_interval)
                        continue
                    
                    # Only process sensors that are configured
                    if sensor_id not in self.expected_sensor_ids:
                        logger.warning(f"Ignoring unexpected sensor '{sensor_id}' (expected: {self.expected_sensor_ids})")
                        time.sleep(self.read_interval)
                        continue
                    
                    # Save valid sensor data
                    self.data_store.save_temperature(sensor_id, temperature)
                    
                time.sleep(self.read_interval)
            except Exception as e:
                logger.error(f"Error in read loop: {e}")
                time.sleep(self.read_interval)
