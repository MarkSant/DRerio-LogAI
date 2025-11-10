# Troubleshooting Guide

This guide provides solutions to common issues encountered when using DRerio LogAI (ZebTrack-AI).

## Table of Contents

1. [Installation Issues](#installation-issues)
2. [Camera and Video Issues](#camera-and-video-issues)
3. [Detection and Tracking Issues](#detection-and-tracking-issues)
4. [Performance Issues](#performance-issues)
5. [GPU and Hardware Issues](#gpu-and-hardware-issues)
6. [Analysis and Results Issues](#analysis-and-results-issues)
7. [Application Errors](#application-errors)
8. [Configuration Issues](#configuration-issues)

---

## Installation Issues

### Poetry installation fails

**Problem**: `poetry install` command fails with dependency errors

**Solutions**:

1. **Ensure Python 3.12+**:
   ```bash
   python --version  # Should show 3.12 or higher
   ```

2. **Update Poetry**:
   ```bash
   poetry self update
   ```

3. **Clear Poetry cache**:
   ```bash
   poetry cache clear pypi --all
   poetry install
   ```

4. **Force reinstall**:
   ```bash
   rm -rf .venv
   poetry install
   ```

5. **Check setuptools version** (must be <81):
   ```bash
   poetry run pip list | grep setuptools
   # Should show setuptools < 81
   ```

### ModuleNotFoundError after installation

**Problem**: `ModuleNotFoundError: No module named 'zebtrack'`

**Solutions**:

1. **Activate Poetry environment**:
   ```bash
   poetry shell
   zebtrack
   ```
   OR use:
   ```bash
   poetry run zebtrack
   ```

2. **Verify installation**:
   ```bash
   poetry show zebtrack
   # Should display package info
   ```

3. **Reinstall in editable mode**:
   ```bash
   poetry install
   ```

### ImportError: DLL load failed (Windows)

**Problem**: `ImportError: DLL load failed while importing _imaging`

**Solutions**:

1. **Install Visual C++ Redistributables**:
   - Download from [Microsoft](https://aka.ms/vs/17/release/vc_redist.x64.exe)
   - Install and restart computer

2. **Reinstall Pillow**:
   ```bash
   poetry run pip uninstall Pillow
   poetry run pip install Pillow
   ```

3. **Check Python architecture**:
   ```bash
   python -c "import struct; print(struct.calcsize('P') * 8)"
   # Should show 64 (not 32)
   ```

---

## Camera and Video Issues

### Camera Not Found

**Problem**: Error message "Camera ID 0 not available" or "Cannot open camera"

**Step-by-Step Solutions**:

#### 1. Verify Camera Connection
- Check USB cable is fully inserted
- Try different USB port (prefer USB 3.0)
- Test camera in other applications (Zoom, Skype)

#### 2. Check Camera Permissions (Windows)
1. Open **Settings** → **Privacy & Security** → **Camera**
2. Enable "Let apps access your camera"
3. Enable "Let desktop apps access your camera"
4. Restart application

#### 3. Check Camera Permissions (Linux)
```bash
# Check if user is in video group
groups $USER

# Add user to video group if needed
sudo usermod -a -G video $USER
# Log out and log back in

# Check camera devices
ls -l /dev/video*
```

#### 4. Try Different Camera ID
1. Open **File** → **Settings**
2. Navigate to **Camera** section
3. Try camera IDs: 0, 1, 2, 3
4. Click **Test Camera** for each ID

#### 5. Check Camera Driver (Windows)
1. Open **Device Manager** (Win+X → Device Manager)
2. Expand **Cameras** or **Imaging devices**
3. Right-click camera → **Update driver**
4. If yellow warning icon: **Uninstall device** → Restart computer

#### 6. Restart Camera Service (Windows)
```powershell
# Run as Administrator
Get-PnpDevice | Where-Object {$_.FriendlyName -like '*camera*'} | Disable-PnpDevice -Confirm:$false
Start-Sleep -Seconds 2
Get-PnpDevice | Where-Object {$_.FriendlyName -like '*camera*'} | Enable-PnpDevice -Confirm:$false
```

### Video file won't load

**Problem**: Error when loading video file

**Solutions**:

1. **Check file format**:
   - Supported: MP4, AVI, MOV, MKV
   - Use VLC or FFmpeg to verify file integrity

2. **Try re-encoding**:
   ```bash
   # Using FFmpeg
   ffmpeg -i input.mp4 -c:v libx264 -preset medium -crf 23 output.mp4
   ```

3. **Check file path**:
   - Avoid special characters in filename
   - Avoid very long paths (>260 chars on Windows)
   - Use absolute paths, not relative

4. **Verify codec**:
   ```bash
   ffmpeg -i video.mp4
   # Look for Video: h264 or Video: hevc
   ```

5. **Copy file locally**:
   - If on network drive, copy to local disk first

### Camera image is black or frozen

**Problem**: Camera opens but shows black screen or frozen image

**Solutions**:

1. **Check camera exposure settings**:
   - May be auto-adjusting to lighting
   - Wait 5-10 seconds for auto-exposure

2. **Improve lighting**:
   - Ensure adequate light in environment
   - Avoid pointing camera at bright light source

3. **Test camera externally**:
   ```python
   import cv2
   cap = cv2.VideoCapture(0)
   ret, frame = cap.read()
   if ret:
       cv2.imshow('Test', frame)
       cv2.waitKey(0)
   cap.release()
   ```

4. **Update camera firmware** (if available from manufacturer)

5. **Try different resolution**:
   - In settings, try lower resolution (720p instead of 1080p)

---

## Detection and Tracking Issues

### Low Detection Accuracy

**Problem**: Many missed detections or false positives

**Immediate Solutions**:

#### For Too Many False Positives (detecting debris, shadows)

1. **Increase confidence threshold**:
   - Current: 0.5 → Try: 0.6 or 0.7
   - In Wizard Step 4 or Settings → Detection

2. **Clean environment**:
   - Remove debris from tank
   - Clean camera lens
   - Use plain background (avoid gravel, plants)

3. **Improve lighting**:
   - Add diffuse lighting (no harsh shadows)
   - Eliminate reflections and glare
   - Use consistent lighting (no flickering)

#### For Too Many Misses (not detecting fish)

1. **Lower confidence threshold**:
   - Current: 0.5 → Try: 0.4 or 0.35
   - Increases sensitivity

2. **Check video quality**:
   - Increase resolution (720p → 1080p)
   - Ensure camera is in focus
   - Verify sufficient contrast (fish vs background)

3. **Try different model**:
   - Switch YOLO ↔ OpenVINO
   - Try different YOLO variant (if custom models available)

#### General Accuracy Improvements

1. **Calibrate camera**:
   - Ensure camera is perpendicular to water surface
   - Minimize lens distortion (use good quality lens)
   - Fix camera position (no movement)

2. **Optimize video settings**:
   - Frame rate: 30 FPS (not too high or low)
   - Bitrate: High (minimize compression)
   - Codec: H.264 (good quality/size balance)

3. **Subject visibility**:
   - Ensure fish is visually distinct from background
   - Adequate size in frame (fish should be >30 pixels)
   - Good contrast (dark fish on light background or vice versa)

4. **Consider custom model**:
   - If using non-standard species, train custom model
   - See `docs/MODEL_TRAINING.md` (coming soon)

### Track IDs keep changing

**Problem**: Subject loses track ID frequently, causing incorrect metrics

**Understanding the Issue**:
Track ID changes (re-identification failures) occur when:
- Subjects occlude each other (multi-subject tracking)
- Subject exits and re-enters frame
- Detection gaps (subject temporarily not detected)
- Similar-looking subjects

**Solutions**:

1. **Improve detection consistency**:
   - Increase confidence threshold (more reliable detections)
   - Improve video quality
   - Ensure continuous detection (no gaps)

2. **For single-subject tracking**:
   - Ensure only one subject in frame
   - Verify not detecting reflections or debris
   - May need to manually filter tracks by duration

3. **For multi-subject tracking**:
   - ID swaps are more common (expected behavior)
   - Use track-by-track analysis (separate metrics per ID)
   - Consider analyzing subjects individually if possible

4. **Post-processing**:
   - Merge short tracks that are likely same subject
   - Filter tracks by minimum duration
   - Use custom scripts for track reconciliation

### No detections in entire video

**Problem**: Analysis completes but 0 detections found

**Solutions**:

1. **Verify model loaded**:
   - Check **Help → System Info** → Model status
   - If error, reinstall model or specify model path

2. **Lower confidence threshold drastically**:
   - Try 0.1 or 0.2 to see if any detections occur

3. **Check frame extraction**:
   - Verify video is actually playing (not corrupted)
   - Check frame count > 0 in video metadata

4. **Test on sample video**:
   - Try analysis on known-good video (e.g., demo video)
   - If works, issue is with your specific video

5. **Check ROI configuration**:
   - If ROI is defined, ensure it covers subject location
   - Try removing ROI constraints

6. **Verify subject is visible**:
   - Manually inspect video frames
   - Ensure subject is not too small (<10 pixels)

---

## Performance Issues

### Slow Performance

**Problem**: Analysis is very slow (<5 FPS)

**Quick Diagnostics**:

Check current performance:
- During analysis, note "Processing Speed" (FPS)
- Compare to expected: GPU 25-60 FPS, CPU 5-15 FPS

**Solutions by Cause**:

#### 1. GPU Not Being Used

**Check GPU status**:
```bash
poetry run python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

**If False**:
- Install CUDA Toolkit: [NVIDIA CUDA Downloads](https://developer.nvidia.com/cuda-downloads)
- Install cuDNN: [NVIDIA cuDNN](https://developer.nvidia.com/cudnn)
- Reinstall PyTorch with CUDA:
  ```bash
  poetry run pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
  ```

**If True but still slow**:
- Check GPU memory usage: `nvidia-smi`
- Close other GPU applications
- Reduce batch size in settings

#### 2. Video Resolution Too High

**Solution**: Reduce resolution
```python
# In config.local.yaml
camera:
  desired_width: 1280   # Down from 1920
  desired_height: 720   # Down from 1080
```

Or pre-process video:
```bash
ffmpeg -i input_4k.mp4 -vf scale=1920:1080 output_1080p.mp4
```

#### 3. Insufficient RAM

**Check RAM usage**:
- Windows: Task Manager → Performance → Memory
- Linux: `htop` or `free -h`

**Solutions**:
- Close other applications (browsers, etc.)
- Increase virtual memory (Windows: System → Advanced → Performance Settings)
- Reduce `performance.max_parallel_videos` in settings
- Process shorter video segments

#### 4. Hard Drive Bottleneck

**Solutions**:
- Use SSD instead of HDD for temporary files
- Set temporary directory to SSD:
  ```bash
  export TMPDIR=/path/to/ssd/tmp  # Linux
  set TMP=D:\tmp  # Windows
  ```
- Disable real-time antivirus scanning on output directory

#### 5. CPU Throttling (Laptops)

**Solutions**:
- Plug in power adapter (don't use battery)
- Check CPU throttling: Windows → Power Options → High Performance
- Ensure adequate cooling (use laptop cooling pad)
- Clean dust from vents

### Application freezes during analysis

**Problem**: Application becomes unresponsive

**Solutions**:

1. **Wait longer**:
   - Large videos may appear frozen but are processing
   - Check CPU/GPU usage to verify activity

2. **Reduce memory usage**:
   - Close browser, other applications
   - Reduce video resolution
   - Enable frame skipping

3. **Update graphics drivers**:
   - NVIDIA: [GeForce Drivers](https://www.nvidia.com/Download/index.aspx)
   - Intel: [Intel Driver Updates](https://www.intel.com/content/www/us/en/support/detect.html)

4. **Disable real-time previews**:
   ```yaml
   # In config.local.yaml
   ui_features:
     enable_preview_updates: false
   ```

5. **Run in terminal mode** (bypass GUI):
   ```bash
   poetry run zebtrack --no-gui --video input.mp4 --output results/
   ```

---

## GPU and Hardware Issues

### GPU Not Detected

**Problem**: System Info shows "GPU: Not Available" despite having NVIDIA GPU

**Step-by-Step Fix**:

#### 1. Verify GPU is Working
```bash
# Windows: Open Device Manager
Win+X → Device Manager → Display adapters
# Should show NVIDIA GPU

# Linux:
lspci | grep -i nvidia
```

#### 2. Check NVIDIA Drivers
```bash
nvidia-smi
# Should display GPU info, driver version, CUDA version
```

**If command not found**:
- Install/update NVIDIA drivers: https://www.nvidia.com/Download/index.aspx
- Restart computer after installation

#### 3. Verify CUDA Installation
```bash
nvcc --version
# Should show CUDA compiler version
```

**If command not found**:
- Install CUDA Toolkit: https://developer.nvidia.com/cuda-downloads
- Add to PATH (installer option or manual)

#### 4. Check PyTorch CUDA Support
```bash
poetry run python -c "import torch; print(torch.version.cuda)"
# Should show CUDA version (e.g., 11.8)
```

**If None**:
- PyTorch is CPU-only version
- Reinstall with CUDA support:
  ```bash
  poetry run pip uninstall torch torchvision
  poetry run pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
  ```

#### 5. Restart Application
```bash
# Fully close application
# Reopen
poetry run zebtrack
# Check Help → System Info
```

### CUDA Out of Memory Error

**Problem**: `RuntimeError: CUDA out of memory`

**Solutions**:

1. **Reduce batch size**:
   ```yaml
   # In config.local.yaml
   performance:
     detection_batch_size: 1  # Down from 4 or 8
   ```

2. **Lower video resolution** (see [Slow Performance](#slow-performance))

3. **Close other GPU applications**:
   ```bash
   # Check GPU memory usage
   nvidia-smi

   # Kill GPU processes if needed
   # (use Task Manager or kill command)
   ```

4. **Enable GPU memory growth** (automatic in TensorFlow, manual in PyTorch):
   ```python
   # Advanced users: modify src/zebtrack/plugins/yolo_plugin.py
   import torch
   torch.cuda.empty_cache()
   ```

5. **Use smaller model**:
   - YOLOv8n (nano) instead of YOLOv8l (large)
   - Configure in Wizard Step 4

### Arduino not responding

**Problem**: Arduino-based triggers not working

**Solutions**:

1. **Verify Arduino connection**:
   - Check USB cable connected
   - LED on Arduino should be on
   - Try different USB port

2. **Check COM port** (Windows):
   - Device Manager → Ports (COM & LPT)
   - Note COM port number (e.g., COM3)
   - Update in config:
     ```yaml
     arduino:
       port: "COM3"  # Adjust to your port
     ```

3. **Check device path** (Linux):
   ```bash
   ls -l /dev/ttyUSB* /dev/ttyACM*
   # Note device (e.g., /dev/ttyUSB0)
   ```
   ```yaml
   arduino:
     port: "/dev/ttyUSB0"
   ```

4. **Verify permissions** (Linux):
   ```bash
   sudo usermod -a -G dialout $USER
   # Log out and log back in
   ```

5. **Test Arduino separately**:
   - Open Arduino IDE
   - Upload simple sketch (Blink)
   - Verify working before using with ZebTrack-AI

6. **Check baud rate**:
   ```yaml
   arduino:
     baud_rate: 9600  # Match Arduino sketch
   ```

---

## Analysis and Results Issues

### Missing output files

**Problem**: Analysis completes but expected files are missing

**Solutions**:

1. **Check output directory**:
   ```bash
   # Look for <video_name>_results/ directory
   ls -la *_results/
   ```

2. **Verify analysis completed successfully**:
   - Check for error messages in final analysis report
   - Look at logs: `logs/zebtrack.log`

3. **Check export settings**:
   - Wizard Step 5: Ensure desired outputs are enabled
   - "Save Annotated Video", "Generate Heatmap", etc.

4. **Disk space**:
   ```bash
   # Check available space
   df -h .  # Linux
   # or check Properties in Windows
   ```

5. **File permissions**:
   ```bash
   # Ensure write permissions in output directory
   chmod -R u+w *_results/  # Linux
   ```

### Parquet file is corrupted

**Problem**: Cannot open Parquet file, "Invalid Parquet file" error

**Solutions**:

1. **Verify file integrity**:
   ```python
   import pandas as pd
   try:
       df = pd.read_parquet("file.parquet")
       print("File is valid")
   except Exception as e:
       print(f"Error: {e}")
   ```

2. **Check file size**:
   ```bash
   ls -lh file.parquet
   # Should be >0 bytes
   ```
   - If 0 bytes: File was not written (analysis may have crashed)

3. **Try recovery**:
   ```python
   import pyarrow.parquet as pq
   table = pq.read_table("file.parquet")
   # If successful, re-export
   table.to_pandas().to_parquet("file_recovered.parquet")
   ```

4. **Fallback to CSV** (if available):
   - Change export format to CSV
   - Re-run analysis

### Heatmap looks wrong

**Problem**: Heatmap doesn't match expected movement patterns

**Causes and Solutions**:

1. **Wrong ROI definition**:
   - Verify ROI covers correct area
   - Check arena boundary is correct

2. **Coordinate system issue**:
   - If using calibration, verify calibration values
   - Check pixel-to-cm conversion is accurate

3. **Track filtering**:
   - Short, erroneous tracks may skew heatmap
   - Filter tracks by minimum duration:
     ```python
     df = df.groupby('track_id').filter(lambda x: len(x) > 100)  # At least 100 frames
     ```

4. **Resolution mismatch**:
   - Heatmap resolution should match video resolution
   - Check settings: `camera.desired_width`, `camera.desired_height`

### Metrics seem incorrect

**Problem**: Calculated metrics (distance, speed, time in ROI) don't match expectations

**Debugging Steps**:

1. **Check calibration**:
   ```python
   import pandas as pd
   df = pd.read_parquet("3_CoordMovimento_video.parquet")

   # If calibrated, x_cm and y_cm columns should exist
   print(df.columns)

   # Check scale
   print(df[['x_cm', 'y_cm']].describe())
   ```

2. **Verify ROI definitions**:
   - Open `1_ArenaROI_video.parquet`
   - Check ROI coordinates match visual expectations

3. **Check for track ID swaps**:
   ```python
   # Count unique track IDs
   num_tracks = df['track_id'].nunique()
   print(f"Number of unique tracks: {num_tracks}")
   # Should match number of subjects (if single subject, should be 1-2)
   ```

4. **Manual validation**:
   - Watch annotated video alongside metrics
   - Verify at least 1-2 ROI transitions manually
   - Check speed calculations seem reasonable

5. **Re-run analysis**:
   - If settings were incorrect, adjust and re-run
   - Save project settings for reproducibility

---

## Application Errors

### "Error loading model"

**Problem**: Application fails to load AI model

**Solutions**:

1. **Check model path**:
   ```yaml
   # In config.local.yaml
   detector:
     model_path: "models/yolov8n.pt"  # Verify path exists
   ```

2. **Download model manually**:
   ```bash
   # YOLOv8
   wget https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt -O models/yolov8n.pt
   ```

3. **Verify model format**:
   - YOLO: `.pt` file (PyTorch)
   - OpenVINO: `.xml` and `.bin` files

4. **Check model compatibility**:
   - Ensure model is for object detection (not classification or segmentation)
   - Verify model input size matches expectations

5. **Try default model**:
   - Remove custom model path from config
   - Application will download default model automatically

### "Permission denied" errors

**Problem**: Cannot save files or access directories

**Solutions**:

#### Windows:
1. Run as Administrator (right-click → Run as Administrator)
2. Check folder permissions (Properties → Security)
3. Disable "Controlled folder access" (Windows Security → Virus & threat protection → Ransomware protection)

#### Linux:
1. Check file ownership:
   ```bash
   ls -la /path/to/file
   ```
2. Fix ownership if needed:
   ```bash
   sudo chown -R $USER:$USER /path/to/directory
   ```
3. Fix permissions:
   ```bash
   chmod -R u+rw /path/to/directory
   ```

### "Configuration file not found"

**Problem**: Application cannot find `config.yaml`

**Solutions**:

1. **Ensure in correct directory**:
   ```bash
   pwd  # Should be ZebTrack-AI root directory
   ls config.yaml  # Should exist
   ```

2. **Create default config**:
   ```bash
   # Config should be created automatically
   # If missing, copy from repository
   cp config.yaml.example config.yaml
   ```

3. **Specify config path**:
   ```bash
   poetry run zebtrack --config /path/to/config.yaml
   ```

### Application won't start (immediate crash)

**Problem**: Application crashes immediately on launch

**Debugging**:

1. **Check Python version**:
   ```bash
   python --version  # Must be 3.12+
   ```

2. **Run with verbose logging**:
   ```bash
   poetry run zebtrack --verbose --debug
   ```

3. **Check logs**:
   ```bash
   cat logs/zebtrack.log
   # Look for last ERROR message
   ```

4. **Test imports**:
   ```bash
   poetry run python -c "import zebtrack; print('Success')"
   ```

5. **Verify dependencies**:
   ```bash
   poetry check  # Verify lock file
   poetry show   # List installed packages
   ```

6. **Clean reinstall**:
   ```bash
   rm -rf .venv
   rm poetry.lock
   poetry install
   ```

---

## Configuration Issues

### Settings are not being saved

**Problem**: Changes in settings dialog don't persist

**Solutions**:

1. **Check for config.local.yaml**:
   ```bash
   ls -la config.local.yaml
   # If exists, settings are saved here
   ```

2. **Verify write permissions**:
   ```bash
   # Should be writable
   ls -la config*.yaml
   ```

3. **Check for syntax errors**:
   ```bash
   # Validate YAML syntax
   poetry run python -c "import yaml; yaml.safe_load(open('config.local.yaml'))"
   ```

4. **Manual edit**:
   - Open `config.local.yaml` in text editor
   - Verify structure matches `config.yaml`
   - Check indentation (use spaces, not tabs)

### Configuration changes have no effect

**Problem**: Modified settings don't change application behavior

**Solutions**:

1. **Ensure editing correct file**:
   - `config.yaml`: Default settings (overridden by local)
   - `config.local.yaml`: Local overrides (takes precedence)

2. **Restart application**:
   - Settings are loaded at startup
   - Fully close and reopen application

3. **Check setting path**:
   ```yaml
   # Correct structure
   camera:
     index: 0

   # Incorrect (no effect)
   camera_index: 0
   ```

4. **Verify no typos**:
   - Pydantic validation will reject unknown settings
   - Check logs for validation errors

5. **Test with minimal config**:
   ```bash
   # Temporarily rename config.local.yaml
   mv config.local.yaml config.local.yaml.bak

   # Restart application (uses defaults)
   poetry run zebtrack

   # If works, issue is in local config
   ```

---

## Getting More Help

### Reporting Bugs

When reporting bugs, include:

1. **System information**:
   - OS and version
   - Python version (`python --version`)
   - GPU model (if applicable)

2. **Application version**:
   ```bash
   poetry run zebtrack --version
   ```

3. **Error logs**:
   ```bash
   cat logs/zebtrack.log  # Last 50 lines
   ```

4. **Steps to reproduce**:
   - Exact sequence of actions
   - Sample video (if possible)
   - Configuration files

5. **Expected vs actual behavior**

### Community Support

- **GitHub Issues**: https://github.com/MarkSant/ZebTrack-AI/issues
- **Discussions**: https://github.com/MarkSant/ZebTrack-AI/discussions
- **Email**: support@zebtrack.ai

### Documentation

- [Getting Started Guide](GETTING_STARTED.md)
- [FAQ](FAQ.md)
- Developer Docs: `docs/`

---

**Last Updated**: November 2025
**Version**: 2.1
