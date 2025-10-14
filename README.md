# CADLite – CAD to GLB Converter and Web/AR Viewer

Convert your **STEP (.stp / .step)** CAD files into **GLB** format for interactive 3D and AR visualization in the browser.  
Built with `pythonocc-core`, `trimesh`, and `<model-viewer>`.

---

## Features

- Converts `.stp` / `.step` CAD files to `.glb` (glTF Binary)
- Processes all STEP files in a folder automatically
- View converted models directly in the browser with rotation and zoom
- AR support on compatible devices (WebXR / Scene Viewer / Quick Look)
- Lightweight, no framework dependencies

---

## Requirements

- Windows, macOS, or Linux
- [Anaconda or Miniconda](https://www.anaconda.com/download)
- Python 3.10 (recommended)

---

## Setup Instructions (Anaconda)

1. **Install Anaconda / Miniconda**

   Download and install Miniconda from:
   [https://docs.conda.io/en/latest/miniconda.html](https://docs.conda.io/en/latest/miniconda.html)

   When prompted during installation:
   - **Do not add Conda to PATH** (keep default)
   - After installation, open **Anaconda Prompt** from the Start Menu

2. **Create and activate the environment**

   ```bash
   conda create -n cad2ar python=3.10
   conda activate cad2ar

3. **Install dependencies**
   conda install -c conda-forge pythonocc-core
   pip install trimesh numpy

4. **How to Run**
   1. **Place your STEP files** (.stp / .step) in the same folder as convert_step_to_glb.py.
   2. **Run the converter:**
      conda activate cad2ar
      python convert_step_to_glb.py
      All STEP files in the directory will be converted into .glb files with matching names.
   3. **Launch a simple local web server:**   
      python -m http.server 8000
   4. **View in your browser:**
      http://localhost:8000/viewer.html
      Use the dropdown to point to a specific .glb file.


