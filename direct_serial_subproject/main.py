"""
Main orchestration script for the Temperature Sensor Reading system.

This script manages multiple temperature sensors, reading and updating on a single interval.
Temperature data is stored locally in JSON format and batch-updated to ArcGIS Online.

Architecture:
- One thread per COM port: reads from serial every UPDATE_INTERVAL seconds
- Main thread: batch-updates all sensors to ArcGIS every UPDATE_INTERVAL seconds
- All sensor readings stored in single JSON file with multi-sensor structure
"""

import time
import logging
import threading
from typing import Dict, List
from sensor import TemperatureSensor, TemperatureDataStore, ContinuousTemperatureReader
from arcgis_client import ArcGISAuthenticator, ArcGISFeatureUpdater
from config import (
    SENSORS,
    JSON_FILE,
    UPDATE_INTERVAL,
    LOG_LEVEL
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TemperatureSensorSystem:
    """Main system orchestrator for multi-sensor temperature reading and ArcGIS batch updates."""
    
    def __init__(self):
        """Initialize the system components."""
        self.com_port_sensors: Dict[str, TemperatureSensor] = {}  # One sensor per unique COM port
        self.readers: List[ContinuousTemperatureReader] = []
        self.data_store = TemperatureDataStore(JSON_FILE)
        self.authenticator = ArcGISAuthenticator()
        self.feature_updater = ArcGISFeatureUpdater(authenticator=self.authenticator)
        self.is_running = False
        
        # Build sensor-to-ObjectID mapping for ArcGIS updates
        self.sensor_to_object_id: Dict[str, int] = {}
    
    def initialize(self) -> bool:
        """
        Initialize all system components (sensors, readers, ArcGIS connection).
        Groups sensors by COM port - multiple sensors can share one receiver Arduino.
        
        Returns:
            True if all components initialized successfully, False otherwise
        """
        logger.info(f"Initializing Temperature Sensor System with {len(SENSORS)} sensor(s)...")
        
        # Group sensors by COM port
        com_port_to_sensors: Dict[str, List[str]] = {}
        for sensor_id, config in SENSORS.items():
            com_port = config["com_port"]
            if com_port not in com_port_to_sensors:
                com_port_to_sensors[com_port] = []
            com_port_to_sensors[com_port].append(sensor_id)
            
            # Store ObjectID mapping for ArcGIS updates
            self.sensor_to_object_id[sensor_id] = config["arcgis_object_id"]
        
        # Create one TemperatureSensor instance per unique COM port
        for com_port, sensor_ids in com_port_to_sensors.items():
            try:
                # Use config from first sensor on this port for connection settings
                first_sensor_config = SENSORS[sensor_ids[0]]
                
                sensor = TemperatureSensor(
                    port=com_port,
                    baud_rate=first_sensor_config.get("baud_rate", 9600),
                    timeout=first_sensor_config.get("timeout", 2)
                )
                
                if not sensor.connect():
                    logger.error(f"Failed to connect to {com_port}")
                    return False
                
                self.com_port_sensors[com_port] = sensor
                logger.info(f"Connected to {com_port} (handling sensors: {', '.join(sensor_ids)})")
            
            except Exception as e:
                logger.error(f"Failed to initialize {com_port}: {e}")
                return False
        
        # Authenticate with ArcGIS Online
        if not self.feature_updater.authenticate_and_connect():
            logger.error("Failed to authenticate with ArcGIS Online")
            self._disconnect_all_sensors()
            return False
        
        logger.info("System initialization successful")
        return True
    
    def start_sensor_readers(self):
        """Start background reading threads - one per unique COM port."""
        logger.info("Starting sensor reading threads...")
        
        # Group sensors by COM port
        com_port_to_sensors: Dict[str, List[str]] = {}
        for sensor_id, config in SENSORS.items():
            com_port = config["com_port"]
            if com_port not in com_port_to_sensors:
                com_port_to_sensors[com_port] = []
            com_port_to_sensors[com_port].append(sensor_id)
        
        # Create one reader per COM port
        for com_port, sensor_ids in com_port_to_sensors.items():
            reader = ContinuousTemperatureReader(
                expected_sensor_ids=sensor_ids,
                sensor=self.com_port_sensors[com_port],
                data_store=self.data_store,
                read_interval=UPDATE_INTERVAL
            )
            reader.start()
            self.readers.append(reader)
        
        logger.info(f"Started {len(self.readers)} reader thread(s) for {len(SENSORS)} sensor(s)")
    
    def batch_update_arcgis(self) -> bool:
        """
        Read all latest sensor readings from JSON and batch-update ArcGIS Online.
        
        Returns:
            True if update successful, False otherwise
        """
        try:
            # Load all current sensor readings from JSON
            all_readings = self.data_store.load_all_temperatures()
            
            if not all_readings:
                logger.warning("No sensor readings available to update")
                return False
            
            # Filter readings to only sensors we have configured
            sensor_data = {
                sensor_id: data
                for sensor_id, data in all_readings.items()
                if sensor_id in SENSORS and data.get("temperature_F") is not None
            }
            
            if not sensor_data:
                logger.debug("No valid temperature readings to update")
                return False
            
            # Send batch update to ArcGIS
            success = self.feature_updater.update_temperature_batch(
                sensor_data=sensor_data,
                sensor_to_object_id=self.sensor_to_object_id
            )
            
            if success:
                logger.info(f"Updated {len(sensor_data)} sensor(s) to ArcGIS")
            else:
                logger.warning("ArcGIS batch update had errors")
            
            return success
        
        except Exception as e:
            logger.error(f"Failed to batch update ArcGIS: {e}")
            return False
    
    def run(self):
        """
        Main run loop:
        - Sensor readers run continuously in background threads, reading every UPDATE_INTERVAL
        - Main thread batch-updates ArcGIS on the same UPDATE_INTERVAL
        """
        self.is_running = True
        logger.info(f"Starting main orchestration loop (update interval: {UPDATE_INTERVAL}s)")
        
        self.start_sensor_readers()
        
        try:
            while self.is_running:
                # Perform batch update to ArcGIS
                self.batch_update_arcgis()
                
                # Wait until next update cycle
                logger.debug(f"Waiting {UPDATE_INTERVAL}s until next update...")
                time.sleep(UPDATE_INTERVAL)
        
        except KeyboardInterrupt:
            logger.info("Stopped by user (Ctrl+C)")
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
        finally:
            self.cleanup()
    
    def _disconnect_all_sensors(self):
        """Stop all sensor readers and disconnect sensors."""
        logger.info("Disconnecting all sensors...")
        
        for reader in self.readers:
            reader.stop()
        
        for com_port, sensor in self.com_port_sensors.items():
            sensor.disconnect()
    
    def cleanup(self):
        """Clean up resources before shutdown."""
        logger.info("Cleaning up resources...")
        self.is_running = False
        self._disconnect_all_sensors()
        logger.info("System shutdown complete")


def main():
    """Entry point for the application."""
    system = TemperatureSensorSystem()
    
    if not system.initialize():
        logger.error("Failed to initialize system. Exiting.")
        return 1
    
    system.run()
    return 0


if __name__ == "__main__":
    exit(main())
