#!/usr/bin/env python3
"""
Configuration loader - supports environment variables and config files.
"""

import os
import yaml
from pathlib import Path
from typing import Optional


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file and environment variables."""
    config = {}
    
    # Load from YAML if exists
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
    
    # Override with environment variables
    config['deepseek'] = config.get('deepseek', {})
    config['deepseek']['api_key'] = os.getenv('DEEPSEEK_API_KEY', config['deepseek'].get('api_key', ''))
    config['deepseek']['base_url'] = os.getenv('DEEPSEEK_BASE_URL', config['deepseek'].get('base_url', 'https://api.deepseek.com'))
    config['deepseek']['model'] = os.getenv('DEEPSEEK_MODEL', config['deepseek'].get('model', 'deepseek-v4-pro'))
    
    config['github'] = config.get('github', {})
    config['github']['token'] = os.getenv('GITHUB_TOKEN', config['github'].get('token', ''))
    
    config['rosclaw'] = config.get('rosclaw', {})
    config['rosclaw']['api_key'] = os.getenv('ROSCALW_API_KEY', config['rosclaw'].get('api_key', ''))
    config['rosclaw']['base_url'] = os.getenv('ROSCALW_BASE_URL', config['rosclaw'].get('base_url', 'https://www.rosclaw.io'))
    
    return config


def get_api_key(service: str) -> str:
    """Get API key for a service."""
    env_var = f"{service.upper()}_API_KEY"
    return os.getenv(env_var, '')


if __name__ == '__main__':
    config = load_config()
    print("Configuration loaded:")
    print(f"  DeepSeek Model: {config['deepseek']['model']}")
    print(f"  GitHub Token: {'*' * 10 if config['github']['token'] else 'NOT SET'}")
    print(f"  Rosclaw URL: {config['rosclaw']['base_url']}")
