"""
Tests for ML model configuration and hyperparameter validation.

This module tests model configuration loading, hyperparameter validation,
and configuration management functionality.
"""

import json
import os
import sys
import tempfile
from unittest.mock import Mock, patch

import pytest

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), "../../.."))


class TestModelConfiguration:
    """Test suite for model configuration management."""

    @pytest.fixture
    def default_config(self):
        """Default model configuration."""
        return {
            "model_name": "hamzelou/fake-news-bert",
            "confidence_threshold": 0.7,
            "max_length": 512,
            "batch_size": 16,
            "learning_rate": 2e-5,
            "num_epochs": 3,
            "warmup_steps": 100,
            "weight_decay": 0.01,
            "save_steps": 500,
            "eval_steps": 100,
            "logging_steps": 50,
            "gradient_accumulation_steps": 1,
            "fp16": False,
            "early_stopping_patience": 3,
            "early_stopping_threshold": 0.01,
            "dataloader_num_workers": 4,
            "seed": 42
        }

    @pytest.fixture
    def valid_config_file(self, default_config):
        """Create a valid configuration file."""
        config_data = {
            "fake_news_detection": default_config
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
            
        yield config_path
        
        # Cleanup
        if os.path.exists(config_path):
            os.unlink(config_path)

    @pytest.fixture
    def invalid_config_file(self):
        """Create an invalid configuration file."""
        invalid_config = {
            "fake_news_detection": {
                "learning_rate": -0.1,  # Invalid negative learning rate
                "batch_size": 0,        # Invalid zero batch size
                "max_length": -100      # Invalid negative max length
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(invalid_config, f)
            config_path = f.name
            
        yield config_path
        
        # Cleanup
        if os.path.exists(config_path):
            os.unlink(config_path)

    def test_default_configuration_values(self, default_config):
        """Test default configuration values are valid."""
        config = default_config
        
        # Test model parameters
        assert isinstance(config["model_name"], str)
        assert len(config["model_name"]) > 0
        
        # Test confidence threshold
        assert 0.0 <= config["confidence_threshold"] <= 1.0
        
        # Test sequence length
        assert config["max_length"] > 0
        assert config["max_length"] <= 2048  # Reasonable upper bound
        
        # Test batch size
        assert config["batch_size"] > 0
        assert config["batch_size"] <= 128  # Reasonable upper bound
        
        # Test learning rate
        assert 0 < config["learning_rate"] < 1
        
        # Test epochs
        assert config["num_epochs"] > 0
        assert config["num_epochs"] <= 100  # Reasonable upper bound

    def test_configuration_file_loading(self, valid_config_file, default_config):
        """Test loading configuration from file."""
        # Simulate loading config file
        with open(valid_config_file, 'r') as f:
            loaded_config = json.load(f)
        
        fake_news_config = loaded_config.get("fake_news_detection", {})
        
        # Verify loaded configuration matches expected values
        assert fake_news_config["model_name"] == default_config["model_name"]
        assert fake_news_config["confidence_threshold"] == default_config["confidence_threshold"]
        assert fake_news_config["max_length"] == default_config["max_length"]

    def test_configuration_file_not_found(self):
        """Test handling when configuration file doesn't exist."""
        nonexistent_path = "/nonexistent/config.json"
        
        # Should not raise exception but return default config
        default_config = {
            "confidence_threshold": 0.7,
            "max_length": 512,
            "batch_size": 16
        }
        
        # Simulate fallback to default config
        if not os.path.exists(nonexistent_path):
            config = default_config
        
        assert config["confidence_threshold"] == 0.7
        assert config["max_length"] == 512

    def test_invalid_json_configuration(self):
        """Test handling of invalid JSON in configuration file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{ invalid json content }")
            invalid_json_path = f.name
        
        try:
            # Should handle JSON parsing error gracefully
            try:
                with open(invalid_json_path, 'r') as file:
                    json.load(file)
                config_loaded = True
            except json.JSONDecodeError:
                config_loaded = False
                # Fall back to default config
                default_config = {"confidence_threshold": 0.7}
            
            assert not config_loaded
            
        finally:
            os.unlink(invalid_json_path)

    def test_hyperparameter_validation_learning_rate(self):
        """Test learning rate hyperparameter validation."""
        valid_learning_rates = [1e-6, 1e-5, 2e-5, 5e-5, 1e-4, 3e-4]
        invalid_learning_rates = [-0.1, 0, 1.0, 2.0]
        
        for lr in valid_learning_rates:
            assert 0 < lr < 1, f"Learning rate {lr} should be valid"
        
        for lr in invalid_learning_rates:
            assert not (0 < lr < 1), f"Learning rate {lr} should be invalid"

    def test_hyperparameter_validation_batch_size(self):
        """Test batch size hyperparameter validation."""
        valid_batch_sizes = [1, 4, 8, 16, 32, 64, 128]
        invalid_batch_sizes = [0, -1, 256, 512]  # 0, negative, or too large
        
        for batch_size in valid_batch_sizes:
            assert batch_size > 0 and batch_size <= 128, f"Batch size {batch_size} should be valid"
        
        for batch_size in invalid_batch_sizes:
            assert not (batch_size > 0 and batch_size <= 128), f"Batch size {batch_size} should be invalid"

    def test_hyperparameter_validation_sequence_length(self):
        """Test max sequence length hyperparameter validation."""
        valid_lengths = [128, 256, 512, 1024]
        invalid_lengths = [0, -100, 4096, 8192]  # 0, negative, or too large
        
        for length in valid_lengths:
            assert 0 < length <= 2048, f"Sequence length {length} should be valid"
        
        for length in invalid_lengths:
            assert not (0 < length <= 2048), f"Sequence length {length} should be invalid"

    def test_hyperparameter_validation_epochs(self):
        """Test number of epochs hyperparameter validation."""
        valid_epochs = [1, 3, 5, 10, 20]
        invalid_epochs = [0, -1, 1000]  # 0, negative, or too large
        
        for epochs in valid_epochs:
            assert 0 < epochs <= 100, f"Epochs {epochs} should be valid"
        
        for epochs in invalid_epochs:
            assert not (0 < epochs <= 100), f"Epochs {epochs} should be invalid"

    def test_hyperparameter_validation_confidence_threshold(self):
        """Test confidence threshold hyperparameter validation."""
        valid_thresholds = [0.1, 0.3, 0.5, 0.7, 0.9]
        invalid_thresholds = [-0.1, 0.0, 1.0, 1.5]  # Outside [0,1) range
        
        for threshold in valid_thresholds:
            assert 0 < threshold < 1, f"Confidence threshold {threshold} should be valid"
        
        for threshold in invalid_thresholds:
            assert not (0 < threshold < 1), f"Confidence threshold {threshold} should be invalid"

    def test_hyperparameter_validation_weight_decay(self):
        """Test weight decay hyperparameter validation."""
        valid_weight_decays = [0.0, 0.01, 0.05, 0.1]
        invalid_weight_decays = [-0.1, 1.0, 2.0]  # Negative or too large
        
        for weight_decay in valid_weight_decays:
            assert 0 <= weight_decay < 1, f"Weight decay {weight_decay} should be valid"
        
        for weight_decay in invalid_weight_decays:
            assert not (0 <= weight_decay < 1), f"Weight decay {weight_decay} should be invalid"

    def test_hyperparameter_validation_warmup_steps(self):
        """Test warmup steps hyperparameter validation."""
        valid_warmup_steps = [0, 50, 100, 500, 1000]
        invalid_warmup_steps = [-1, -100]  # Negative values
        
        for warmup_steps in valid_warmup_steps:
            assert warmup_steps >= 0, f"Warmup steps {warmup_steps} should be valid"
        
        for warmup_steps in invalid_warmup_steps:
            assert not (warmup_steps >= 0), f"Warmup steps {warmup_steps} should be invalid"

    def test_configuration_override(self, default_config):
        """Test configuration override functionality."""
        base_config = default_config.copy()
        override_config = {
            "learning_rate": 1e-4,
            "batch_size": 32,
            "max_length": 256
        }
        
        # Apply overrides
        merged_config = base_config.copy()
        merged_config.update(override_config)
        
        # Verify overrides were applied
        assert merged_config["learning_rate"] == 1e-4
        assert merged_config["batch_size"] == 32
        assert merged_config["max_length"] == 256
        
        # Verify other values remain unchanged
        assert merged_config["confidence_threshold"] == base_config["confidence_threshold"]
        assert merged_config["num_epochs"] == base_config["num_epochs"]

    def test_configuration_environment_variables(self):
        """Test configuration loading from environment variables."""
        env_vars = {
            "ML_LEARNING_RATE": "1e-4",
            "ML_BATCH_SIZE": "32",
            "ML_MAX_LENGTH": "256"
        }
        
        # Mock environment variables
        with patch.dict(os.environ, env_vars):
            # Simulate loading from environment
            config = {}
            if "ML_LEARNING_RATE" in os.environ:
                config["learning_rate"] = float(os.environ["ML_LEARNING_RATE"])
            if "ML_BATCH_SIZE" in os.environ:
                config["batch_size"] = int(os.environ["ML_BATCH_SIZE"])
            if "ML_MAX_LENGTH" in os.environ:
                config["max_length"] = int(os.environ["ML_MAX_LENGTH"])
            
            # Verify environment variables were loaded
            assert config["learning_rate"] == 1e-4
            assert config["batch_size"] == 32
            assert config["max_length"] == 256

    def test_configuration_validation_schema(self, default_config):
        """Test configuration validation against schema."""
        config = default_config
        
        # Define expected schema
        required_fields = [
            "model_name", "confidence_threshold", "max_length", 
            "batch_size", "learning_rate", "num_epochs"
        ]
        
        # Validate required fields are present
        for field in required_fields:
            assert field in config, f"Required field {field} missing from config"
        
        # Validate data types
        assert isinstance(config["model_name"], str)
        assert isinstance(config["confidence_threshold"], (int, float))
        assert isinstance(config["max_length"], int)
        assert isinstance(config["batch_size"], int)
        assert isinstance(config["learning_rate"], (int, float))
        assert isinstance(config["num_epochs"], int)

    def test_configuration_nested_structure(self):
        """Test nested configuration structure handling."""
        nested_config = {
            "model": {
                "name": "hamzelou/fake-news-bert",
                "parameters": {
                    "max_length": 512,
                    "hidden_size": 768
                }
            },
            "training": {
                "learning_rate": 2e-5,
                "batch_size": 16,
                "optimizer": {
                    "type": "AdamW",
                    "weight_decay": 0.01
                }
            }
        }
        
        # Verify nested structure access
        assert nested_config["model"]["name"] == "hamzelou/fake-news-bert"
        assert nested_config["model"]["parameters"]["max_length"] == 512
        assert nested_config["training"]["optimizer"]["type"] == "AdamW"

    def test_configuration_serialization(self, default_config):
        """Test configuration serialization and deserialization."""
        config = default_config
        
        # Serialize to JSON string
        json_string = json.dumps(config, indent=2)
        
        # Deserialize back to dict
        deserialized_config = json.loads(json_string)
        
        # Verify serialization preserved all data
        assert deserialized_config == config
        
        # Test specific fields
        assert deserialized_config["model_name"] == config["model_name"]
        assert deserialized_config["learning_rate"] == config["learning_rate"]

    def test_configuration_update_validation(self, default_config):
        """Test validation when updating configuration."""
        config = default_config.copy()
        
        # Valid updates
        valid_updates = {
            "learning_rate": 3e-5,
            "batch_size": 32,
            "confidence_threshold": 0.8
        }
        
        # Apply valid updates
        for key, value in valid_updates.items():
            config[key] = value
            # Validate each update
            if key == "learning_rate":
                assert 0 < config[key] < 1
            elif key == "batch_size":
                assert config[key] > 0
            elif key == "confidence_threshold":
                assert 0 <= config[key] <= 1

    def test_configuration_compatibility_check(self):
        """Test configuration compatibility across versions."""
        # Simulate old configuration format
        old_config = {
            "model": "roberta-base",  # Old format
            "threshold": 0.7,         # Old field name
            "seq_len": 512           # Old field name
        }
        
        # Migration to new format
        new_config = {
            "model_name": old_config.get("model", "hamzelou/fake-news-bert"),
            "confidence_threshold": old_config.get("threshold", 0.7),
            "max_length": old_config.get("seq_len", 512)
        }
        
        # Verify migration
        assert new_config["model_name"] == "roberta-base"
        assert new_config["confidence_threshold"] == 0.7
        assert new_config["max_length"] == 512

    def test_configuration_partial_loading(self, default_config):
        """Test loading partial configuration with defaults."""
        partial_config = {
            "learning_rate": 1e-4,
            "batch_size": 32
        }
        
        # Merge with defaults
        full_config = default_config.copy()
        full_config.update(partial_config)
        
        # Verify partial values were updated
        assert full_config["learning_rate"] == 1e-4
        assert full_config["batch_size"] == 32
        
        # Verify defaults were preserved
        assert full_config["confidence_threshold"] == default_config["confidence_threshold"]
        assert full_config["max_length"] == default_config["max_length"]

    def test_configuration_validation_ranges(self):
        """Test configuration validation with specific ranges."""
        # Test learning rate ranges
        assert validate_learning_rate(2e-5) == True
        assert validate_learning_rate(1e-3) == True
        assert validate_learning_rate(-0.1) == False
        assert validate_learning_rate(1.0) == False
        
        # Test batch size ranges
        assert validate_batch_size(16) == True
        assert validate_batch_size(128) == True
        assert validate_batch_size(0) == False
        assert validate_batch_size(256) == False
        
        # Test max length ranges
        assert validate_max_length(512) == True
        assert validate_max_length(1024) == True
        assert validate_max_length(0) == False
        assert validate_max_length(4096) == False

    def test_configuration_gpu_settings(self):
        """Test GPU-specific configuration settings."""
        gpu_config = {
            "use_gpu": True,
            "gpu_id": 0,
            "fp16": True,
            "gradient_accumulation_steps": 4,
            "dataloader_num_workers": 8
        }
        
        # Validate GPU settings
        assert isinstance(gpu_config["use_gpu"], bool)
        assert gpu_config["gpu_id"] >= 0
        assert isinstance(gpu_config["fp16"], bool)
        assert gpu_config["gradient_accumulation_steps"] > 0
        assert gpu_config["dataloader_num_workers"] >= 0

    def test_configuration_reproducibility_settings(self):
        """Test reproducibility configuration settings."""
        reproducibility_config = {
            "seed": 42,
            "deterministic": True,
            "benchmark": False
        }
        
        # Validate reproducibility settings
        assert isinstance(reproducibility_config["seed"], int)
        assert reproducibility_config["seed"] >= 0
        assert isinstance(reproducibility_config["deterministic"], bool)
        assert isinstance(reproducibility_config["benchmark"], bool)


def validate_learning_rate(lr):
    """Validate learning rate parameter."""
    return 0 < lr < 1


def validate_batch_size(batch_size):
    """Validate batch size parameter."""
    return 0 < batch_size <= 128


def validate_max_length(max_length):
    """Validate max sequence length parameter."""
    return 0 < max_length <= 2048


if __name__ == "__main__":
    pytest.main([__file__])
