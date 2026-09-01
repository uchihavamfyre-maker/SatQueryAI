@echo off
setlocal
python scripts\setup_models.py --changeformer
python scripts\setup_models.py --rsvqa
endlocal
