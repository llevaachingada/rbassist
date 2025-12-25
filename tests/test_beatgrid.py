#!/usr/bin/env python3
"""Comprehensive beatgrid system debugging test."""

import sys
from pathlib import Path
import traceback
import json
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add rbassist to path
sys.path.insert(0, str(Path(__file__).parent))

from rbassist.beatgrid import (
    BeatgridConfig,
    analyze_file,
    _pick_backend,
    LibrosaBackend,
    BeatNetBackend,
)
from rbassist.utils import load_meta, walk_audio


def test_backends():
    """Test backend availability and functionality."""
    print("=" * 60)
    print("TESTING BACKENDS")
    print("=" * 60)

    # Test librosa backend
    print("\n1. Testing LibrosaBackend...")
    try:
        backend = LibrosaBackend()
        print("   ✓ LibrosaBackend instantiated successfully")
    except Exception as e:
        print(f"   ✗ LibrosaBackend failed: {e}")
        traceback.print_exc()

    # Test BeatNet backend
    print("\n2. Testing BeatNetBackend...")
    try:
        backend = BeatNetBackend()
        print("   ✓ BeatNetBackend instantiated successfully")

        # Check for CUDA
        try:
            import torch
            cuda_available = torch.cuda.is_available()
            print(f"   ✓ PyTorch CUDA available: {cuda_available}")
        except ImportError:
            print("   ⚠ PyTorch not installed (BeatNet requires PyTorch)")
    except Exception as e:
        print(f"   ⚠ BeatNetBackend failed: {e}")
        print("   (This is OK if BeatNet optional dependencies not installed)")

    # Test backend selection
    print("\n3. Testing backend selection...")
    configs = [
        BeatgridConfig(backend="beatnet"),
        BeatgridConfig(backend="auto"),
        BeatgridConfig(backend="librosa"),
    ]

    for cfg in configs:
        try:
            backend, warnings = _pick_backend(cfg)
            backend_type = type(backend).__name__
            print(f"   ✓ backend='{cfg.backend}' → {backend_type}")
            if warnings:
                for w in warnings:
                    print(f"     ⚠ {w}")
        except Exception as e:
            print(f"   ✗ backend='{cfg.backend}' failed: {e}")


def test_config():
    """Test configuration options."""
    print("\n" + "=" * 60)
    print("TESTING CONFIGURATION")
    print("=" * 60)

    configs = {
        "Default": BeatgridConfig(),
        "Fixed mode": BeatgridConfig(mode="fixed", backend="librosa"),
        "Dynamic mode": BeatgridConfig(mode="dynamic", drift_pct=2.0, bars_window=8),
        "BeatNet": BeatgridConfig(backend="beatnet", model_id=3),
        "Auto backend": BeatgridConfig(backend="auto"),
    }

    for name, cfg in configs.items():
        print(f"\n{name}:")
        print(f"  mode: {cfg.mode}")
        print(f"  backend: {cfg.backend}")
        print(f"  drift_pct: {cfg.drift_pct}")
        print(f"  bars_window: {cfg.bars_window}")
        print(f"  duration_s: {cfg.duration_s}")
        print(f"  model_id: {cfg.model_id}")
        print(f"  device: {cfg.device}")


def test_analyze_file():
    """Test file analysis with a sample audio file."""
    print("\n" + "=" * 60)
    print("TESTING FILE ANALYSIS")
    print("=" * 60)

    # Try to find a test audio file
    meta = load_meta()
    tracks = meta.get("tracks", {})

    if not tracks:
        print("\n⚠ No tracks found in meta.json. Cannot test file analysis.")
        print("  Add audio files to your music folders first.")
        return

    # Get first track
    test_path = list(tracks.keys())[0]
    print(f"\nTest file: {Path(test_path).name}")
    print(f"Full path: {test_path}")

    # Check if file exists
    if not Path(test_path).exists():
        print(f"✗ File does not exist! Trying to find another...")
        for path in tracks.keys():
            if Path(path).exists():
                test_path = path
                print(f"Found: {Path(test_path).name}")
                break
        else:
            print("✗ No accessible audio files found in meta.json")
            return

    # Test with different configs
    test_configs = [
        ("Fixed + librosa", BeatgridConfig(mode="fixed", backend="librosa", duration_s=30)),
        ("Dynamic + librosa", BeatgridConfig(mode="dynamic", backend="librosa", duration_s=30)),
        ("Fixed + auto", BeatgridConfig(mode="fixed", backend="auto", duration_s=30)),
    ]

    for name, cfg in test_configs:
        print(f"\n{name}:")
        try:
            path, result, error, warnings = analyze_file(test_path, cfg)

            if warnings:
                for w in warnings:
                    print(f"  ⚠ {w}")

            if error:
                print(f"  ✗ Error: {error}")
            elif result:
                print(f"  ✓ Analysis successful")
                print(f"    - BPM estimate: {result.get('bpm_est', 0):.1f}")
                print(f"    - Confidence: {result.get('confidence', 0):.2f}")
                print(f"    - Beats detected: {len(result.get('beats', []))}")
                print(f"    - Downbeats: {len(result.get('downbeats', []))}")
                print(f"    - Tempo segments: {len(result.get('tempos', []))}")
                if result.get('tempos'):
                    for i, seg in enumerate(result['tempos'][:3]):  # Show first 3
                        print(f"      Segment {i+1}: {seg['inizio_sec']:.1f}s @ {seg['bpm']:.1f} BPM")
            else:
                print(f"  ✗ No result returned")
        except Exception as e:
            print(f"  ✗ Exception: {e}")
            traceback.print_exc()


def test_meta_integration():
    """Test meta.json reading and beatgrid data."""
    print("\n" + "=" * 60)
    print("TESTING META.JSON INTEGRATION")
    print("=" * 60)

    try:
        meta = load_meta()
        tracks = meta.get("tracks", {})

        print(f"\nTotal tracks: {len(tracks)}")

        # Count beatgrid status
        has_beatgrid = 0
        has_tempos = 0
        has_bpm_grid_est = 0

        for path, info in tracks.items():
            if info.get("tempos"):
                has_tempos += 1
            if info.get("bpm_grid_est"):
                has_bpm_grid_est += 1
            if info.get("tempos") or info.get("bpm_grid_est"):
                has_beatgrid += 1

        print(f"Tracks with beatgrid data: {has_beatgrid}")
        print(f"  - with 'tempos': {has_tempos}")
        print(f"  - with 'bpm_grid_est': {has_bpm_grid_est}")

        # Show example beatgrid data
        if has_tempos > 0:
            print("\nExample beatgrid track:")
            for path, info in tracks.items():
                if info.get("tempos"):
                    print(f"  Path: {Path(path).name}")
                    print(f"  Artist: {info.get('artist', 'Unknown')}")
                    print(f"  Title: {info.get('title', 'Unknown')}")
                    print(f"  Beatgrid mode: {info.get('beatgrid_mode', 'N/A')}")
                    print(f"  Beatgrid backend: {info.get('beatgrid_backend', 'N/A')}")
                    print(f"  Beatgrid confidence: {info.get('beatgrid_confidence', 0):.2f}")
                    print(f"  BPM (grid): {info.get('bpm_grid_est', 0):.1f}")
                    print(f"  Tempo segments: {len(info.get('tempos', []))}")
                    for i, seg in enumerate(info.get('tempos', [])[:3]):
                        print(f"    Segment {i+1}: {seg.get('inizio_sec', 0):.1f}s @ {seg.get('bpm', 0):.1f} BPM")
                    break

    except Exception as e:
        print(f"\n✗ Error loading meta.json: {e}")
        traceback.print_exc()


def test_ui_state():
    """Test UI state and settings."""
    print("\n" + "=" * 60)
    print("TESTING UI STATE")
    print("=" * 60)

    try:
        settings_path = Path("config/ui_settings.json")
        if settings_path.exists():
            with open(settings_path) as f:
                settings = json.load(f)

            print("\nUI Settings:")
            print(f"  beatgrid_enable: {settings.get('beatgrid_enable', False)}")
            print(f"  beatgrid_overwrite: {settings.get('beatgrid_overwrite', False)}")
            print(f"  music_folders: {settings.get('music_folders', [])}")
        else:
            print("\n⚠ config/ui_settings.json not found")
    except Exception as e:
        print(f"\n✗ Error reading UI settings: {e}")


def test_export():
    """Test XML export capability."""
    print("\n" + "=" * 60)
    print("TESTING EXPORT FUNCTIONALITY")
    print("=" * 60)

    try:
        from rbassist.export_xml import write_rekordbox_xml
        print("\n✓ export_xml module imported successfully")

        # Check if we have beatgrid data to export
        meta = load_meta()
        tracks_with_tempos = sum(1 for t in meta.get("tracks", {}).values() if t.get("tempos"))

        print(f"  Tracks with tempo data: {tracks_with_tempos}")

        if tracks_with_tempos > 0:
            print("  ✓ Ready to export (tracks have tempo data)")
        else:
            print("  ⚠ No tracks have tempo data yet (run beatgrid analysis first)")

    except ImportError as e:
        print(f"\n✗ Cannot import export_xml: {e}")
    except Exception as e:
        print(f"\n✗ Error: {e}")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("BEATGRID SYSTEM DIAGNOSTIC TEST")
    print("=" * 60)

    tests = [
        ("Backend Availability", test_backends),
        ("Configuration Options", test_config),
        ("File Analysis", test_analyze_file),
        ("Meta.json Integration", test_meta_integration),
        ("UI State", test_ui_state),
        ("Export Functionality", test_export),
    ]

    for test_name, test_func in tests:
        try:
            test_func()
        except Exception as e:
            print(f"\n✗ {test_name} crashed: {e}")
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("DIAGNOSTIC TEST COMPLETE")
    print("=" * 60)
    print("\nSummary:")
    print("- Check the output above for any ✗ errors or ⚠ warnings")
    print("- Backend issues: Install BeatNet with 'pip install rbassist[beatgrid]'")
    print("- File issues: Ensure audio files in meta.json are accessible")
    print("- UI issues: Check NiceGUI and file picker compatibility")


if __name__ == "__main__":
    main()
