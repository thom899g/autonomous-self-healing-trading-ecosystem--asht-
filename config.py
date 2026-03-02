"""
ASHT Configuration Manager
Centralized configuration with validation and Firebase fallback
"""
import os
import json
from typing import Dict, Any, Optional
import firebase_admin
from firebase_admin import firestore, credentials
from loguru import logger

class ConfigManager:
    """Manages configuration with Firebase fallback and validation"""
    
    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.db = None
        self._initialize_firebase()
        self._load_configuration()
        
    def _initialize_firebase(self) -> None:
        """Initialize Firebase connection with error handling"""
        try:
            # Check for Firebase credentials
            cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH')
            if not cred_path or not os.path.exists(cred_path):
                logger.warning("Firebase credentials not found. Using local config only.")
                return
                
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            self.db = firestore.client()
            logger.success("Firebase initialized successfully")
            
        except Exception as e:
            logger.error(f"Firebase initialization failed: {e}")
            self.db = None
            
    def _load_configuration(self) -> None:
        """Load configuration from multiple sources with priority"""
        config_sources = [
            self._load_from_firebase,
            self._load_from_env,
            self._load_defaults
        ]
        
        for source in config_sources:
            try:
                source()
            except Exception as e:
                logger.warning(f"Config source failed: {source.__name__}: {e}")
                
        self._validate_configuration()
        
    def _load_from_firebase(self) -> None:
        """Load configuration from Firebase Firestore"""
        if not self.db:
            raise ValueError("Firebase not initialized")
            
        doc_ref = self.db.collection('config').document('asht_main')
        doc = doc_ref.get()
        
        if doc.exists:
            self.config.update(doc.to_dict())
            logger.info("Loaded configuration from Firebase")
            
    def _load_from_env(self) -> None:
        """Load configuration from environment variables"""
        env_mapping = {
            'TRADING_SYMBOL': ('trading', 'symbol'),
            'MAX_POSITION_SIZE': ('risk', 'max_position_size'),
            'ANOMALY_THRESHOLD': ('monitoring', 'anomaly_threshold'),
            'MODEL_CHECKPOINT_PATH': ('paths', 'model_checkpoint'),
        }
        
        for env_var, config_path in env_mapping.items():
            value = os.getenv(env_var)
            if value:
                # Navigate nested dict structure
                keys = config_path
                d = self.config
                for key in keys[:-1]:
                    d = d.setdefault(key, {})
                d[keys[-1]] = self._parse_env_value(value)
                
    def _load_defaults(self) -> None:
        """Load default configuration"""
        defaults = {
            'trading': {
                'symbol': 'BTC/USDT',
                'timeframe': '1h',
                'exchange': 'binance',
                'paper_trading': True
            },
            'risk': {
                'max_position_size': 0.1,  # 10% of capital
                'max_daily_loss': 0.02,    # 2% daily loss limit
                'stop_loss_pct': 0.02,
                'take_profit_pct': 0.04
            },
            'rl': {
                'learning_rate': 0.001,
                'gamma': 0.99,
                'epsilon_start': 1.0,
                'epsilon_end': 0.01,
                'epsilon_decay': 0.995
            },
            'monitoring': {
                'anomaly_threshold': 3.0,
                'check_interval_minutes': 5,
                'performance_window': 24  # hours
            },
            'paths': {
                'model_checkpoint': './checkpoints/',
                'data_cache': './data/cache/',
                'logs': './logs/'
            }
        }
        
        # Merge defaults only for missing keys
        def deep_update(target, source):
            for key, value in source.items():
                if key not in target:
                    target[key] = value
                elif isinstance(value, dict) and isinstance(target[key], dict):
                    deep_update(target[key], value)
                    
        deep_update(self.config, defaults)
        
    def _parse_env_value(self, value: str) -> Any:
        """Parse environment variable values to appropriate types"""
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            # Try to parse as int, float, or bool
            if value.lower() in ('true', 'false'):
                return value.lower() == 'true'
            try:
                return int(value)
            except ValueError:
                try:
                    return float(value)
                except ValueError:
                    return value
                    
    def _validate_configuration(self) -> None:
        """Validate configuration values"""
        required_paths = ['model_checkpoint', 'data_cache', 'logs']
        for path_key in required_paths:
            path = self.config['paths'].get(path_key)
            if path:
                os.makedirs(path, exist_ok=True)
                
        # Validate risk parameters
        if self.config['risk']['max_position_size'] > 0.5: