import sys
import os
import json

def main():
    # Read config from stdin
    try:
        config = json.loads(sys.stdin.read())
        GHOST_WHITELIST = set(config.get("ghost_whitelist", []))
    except Exception:
        GHOST_WHITELIST = set()

    warnings_list = []

    try:
        if sys.version_info >= (3, 8):
            from importlib.metadata import distributions
        else:
            import importlib_metadata
            distributions = importlib_metadata.distributions
    except ImportError:
        import pkg_resources  # type: ignore
        distributions = lambda: []

    packages = []
    claimed_top_levels = set()

    # 1. Process regular metadata packages
    try:
        for dist in distributions():
            name = dist.metadata.get("Name", dist.name) if hasattr(dist, 'metadata') else dist.name
            version = dist.version
            
            path = ""
            try:
                if hasattr(dist, 'locate_file'):
                    path = str(dist.locate_file(""))
                elif hasattr(dist, '_path'):
                    path = str(dist._path)
            except Exception as e:
                warnings_list.append(f"Failed to locate path for {name}: {e}")
                
            packages.append({"name": name, "version": version, "path": path})
            
            # Track claimed top-levels
            try:
                # Tier 1: top_level.txt
                top_levels = dist.read_text('top_level.txt')
                if top_levels:
                    for line in top_levels.splitlines():
                        if line.strip():
                            claimed_top_levels.add(line.strip())
                    continue
                    
                # Tier 2: dist.files (RECORD)
                files = getattr(dist, 'files', None)
                if files:
                    for f in files:
                        parts = f.parts
                        if not parts:
                            continue
                        top = parts[0]
                        if top.endswith('.py'):
                            top = top[:-3]
                        elif '.so' in top or '.pyd' in top:
                            top = top.split('.')[0]
                        claimed_top_levels.add(top)
                    continue
                    
            except Exception as e:
                warnings_list.append(f"Failed to read top-level for {name}: {e}")
                
            # Tier 3: Fallback Name
            claimed_top_levels.add(name.lower().replace("-", "_"))

    except Exception as e:
        warnings_list.append(f"importlib.metadata distributions failed: {e}. Falling back to pkg_resources.")
        try:
            import pkg_resources  # type: ignore
            for dist in pkg_resources.working_set:
                packages.append({"name": dist.project_name, "version": dist.version, "path": dist.location})
                # Fallback tracking for pkg_resources
                claimed_top_levels.add(dist.project_name.lower().replace("-", "_"))
                if dist.has_metadata('top_level.txt'):
                    for line in dist.get_metadata('top_level.txt').splitlines():
                        if line.strip():
                            claimed_top_levels.add(line.strip())
        except Exception as e:
            warnings_list.append(f"pkg_resources fallback failed: {e}")

    # 2. Ghost Module Scan
    ghosts = []
    site_dirs = [p for p in sys.path if os.path.isdir(p) and ("site-packages" in p or "dist-packages" in p)]

    for sd in site_dirs:
        try:
            for item in os.listdir(sd):
                if item.startswith(".") or item.endswith(".dist-info") or item.endswith(".egg-info"):
                    continue
                
                top_name = item
                if item.endswith(".py"):
                    top_name = item[:-3]
                elif ".so" in item or ".pyd" in item:
                    top_name = item.split(".")[0]
                elif not os.path.isdir(os.path.join(sd, item)):
                    continue # ignore random files
                    
                if top_name in GHOST_WHITELIST:
                    continue
                    
                # Check if this top-level name is claimed by any known package
                # Ignore cases where the name is trivially the same (case-insensitive)
                if top_name not in claimed_top_levels and top_name.lower() not in claimed_top_levels:
                    ghost_path = os.path.join(sd, item)
                    ghosts.append({"name": top_name, "version": "UNKNOWN", "path": ghost_path})
        except Exception as e:
            warnings_list.append(f"Ghost scan failed on dir {sd}: {e}")

    # 3. Bin Wrappers Scan
    wrappers = []
    if config.get("scan_wrappers"):
        bin_dir = os.path.join(sys.prefix, "bin")
        if os.path.isdir(bin_dir):
            try:
                for item in os.listdir(bin_dir):
                    item_path = os.path.join(bin_dir, item)
                    if os.path.isfile(item_path) and os.access(item_path, os.X_OK) and not os.path.islink(item_path):
                        # Attempt to read shebang
                        try:
                            with open(item_path, 'r') as f:
                                first_line = f.readline().strip()
                                if first_line.startswith("#!"):
                                    shebang = first_line[2:].strip().split()[0]
                                    wrappers.append({
                                        "name": item,
                                        "path": item_path,
                                        "shebang_path": shebang
                                    })
                        except Exception:
                            pass
            except Exception as e:
                warnings_list.append(f"Wrapper scan failed on dir {bin_dir}: {e}")

    result = {
        "prefix": sys.prefix,
        "version_str": f"python{sys.version_info.major}.{sys.version_info.minor}",
        "is_venv": sys.prefix != getattr(sys, "base_prefix", sys.prefix),
        "packages": packages,
        "ghosts": ghosts,
        "wrappers": wrappers,
        "warnings": warnings_list
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
