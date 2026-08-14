@echo off
cd /d "%~dp0"
echo ============================================================
echo  BookGroove -- local MusicGen setup
echo ============================================================
echo.
echo Step 1: PyTorch with CUDA 12.1 (edit the index URL if your GPU stack differs)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
echo.
echo Step 2: transformers and audio libs
pip install -r requirements-local.txt
echo.
echo Done. Set USE_LOCAL_MODEL=true in .env
echo First run downloads ~3 GB into models\
echo.
pause
