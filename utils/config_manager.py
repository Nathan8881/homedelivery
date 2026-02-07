"""
Configuration Manager - Load and manage form configurations
"""
import json
import logging
from typing import Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ConfigManager:
    def __init__(self, base_path: Path = None):
        self.config_map: Optional[Dict] = None
        self.configs_cache: Dict[str, Dict] = {}
        self.base_path = base_path or Path.cwd()
    
    def load_config_map(self) -> Dict:
        """
        Load the config map that maps form IDs to configuration files.
        
        Returns:
            Dict: Configuration map
        """
        config_paths = [
            self.base_path / 'configs' / 'config_map.json',
            self.base_path / 'config_map.json'
        ]
        
        for path in config_paths:
            if path.exists():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        config_map = json.load(f)
                        logger.info(f"Config map loaded from: {path}")
                        return config_map
                except Exception as e:
                    logger.error(f"Error loading {path}: {e}")
        
        raise FileNotFoundError("config_map.json not found")
    
    def load_form_config(self, config_file: str) -> Dict:
        """
        Load a specific form configuration file.
        
        Args:
            config_file: Name of configuration file
            
        Returns:
            Dict: Form configuration
        """
        if config_file in self.configs_cache:
            return self.configs_cache[config_file]
        
        config_paths = [
            self.base_path / 'configs' / config_file,
            self.base_path / config_file
        ]
        
        for path in config_paths:
            if path.exists():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        self.configs_cache[config_file] = config
                        logger.info(f"Config loaded: {config_file}")
                        return config
                except Exception as e:
                    logger.error(f"Error loading {path}: {e}")
        
        raise FileNotFoundError(f"Config file not found: {config_file}")
    
    def get_config_for_form(self, form_id: str) -> Dict:
        """
        Get configuration for a specific form ID.
        
        Args:
            form_id: Jotform form ID
            
        Returns:
            Dict: Form configuration
        """
        if not self.config_map:
            raise RuntimeError("Config map not initialized")
        
        if form_id in self.config_map.get('forms', {}):
            form_info = self.config_map['forms'][form_id]
            logger.info(f"Config found for form {form_id}: {form_info['name']}")
            return self.load_form_config(form_info['config_file'])
        
        default_config = self.config_map.get('default_config', 'home_delivery.json')
        logger.warning(f"Form {form_id} not registered, using default: {default_config}")
        return self.load_form_config(default_config)
    
    def initialize(self):
        """
        Initialize configuration manager and create required directories.
        """
        self.config_map = self.load_config_map()
        
        # Create required directories
        (self.base_path / 'packing_slips').mkdir(parents=True, exist_ok=True)
        (self.base_path / 'barcodes').mkdir(parents=True, exist_ok=True)
        (self.base_path / 'assets').mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Directories created/verified")