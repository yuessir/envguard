import os
import json
from envguard.engine import load_rules
from envguard import logger

def resolve_module_name(import_name: str, search_paths: list = None) -> str:
    """
    Resolve the import name to the actual pip package name.
    1. Check static O(1) mappings from rules.json.
    2. Lazy parsing of .dist-info/top_level.txt in the search paths.
    """
    # 1. Static mappings
    rules = load_rules()
    mappings = rules.get("module_mappings", {})
    if import_name in mappings:
        pkg_name = mappings[import_name]
        logger.debug(f"Resolved '{import_name}' to '{pkg_name}' via static mapping")
        return pkg_name
        
    # 2. Dynamic parsing (top_level.txt)
    if search_paths:
        for path in search_paths:
            if not os.path.isdir(path):
                continue
            for item in os.listdir(path):
                if item.endswith(".dist-info"):
                    top_level_path = os.path.join(path, item, "top_level.txt")
                    if os.path.isfile(top_level_path):
                        with open(top_level_path, 'r', encoding='utf-8') as f:
                            lines = [line.strip() for line in f if line.strip()]
                            if import_name in lines:
                                # Extract package name from .dist-info folder name
                                # Format: PackageName-1.0.dist-info
                                pkg_name = item.split("-")[0]
                                logger.debug(f"Resolved '{import_name}' to '{pkg_name}' via dynamic parsing from {top_level_path}")
                                return pkg_name
                                
    # Fallback: assume the package name is the same as the import name
    logger.debug(f"Could not resolve '{import_name}', falling back to import name")
    return import_name
